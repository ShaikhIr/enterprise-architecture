/**
 * Shared render helper for component/hook tests.
 *
 * Mirrors the real provider stack from `App.tsx` (Redux `Provider` →
 * `QueryClientProvider` → `PrimeReactProvider`), plus a `MemoryRouter` so
 * components that call `useNavigate`/`useLocation`/`<Navigate>` (the route
 * guards, mainly) do not throw for lacking a router context. Wrapping
 * router-agnostic components in it too is harmless — nothing reads the
 * router unless a component actually asks for it.
 *
 * A fresh `QueryClient` per render is deliberate: TanStack Query caches by
 * key, so reusing one client across tests would let an earlier test's cached
 * response leak into a later test that never mocked it.
 */

import type { PropsWithChildren, ReactElement } from 'react';

// Side-effect import, kept first and unused by name: `@app/store` sits at the
// top of a real (if harmless) circular-import cycle with `@core/rbac`'s
// barrel — that barrel's `usePermissions.ts` imports `@app/store` for its
// hooks, and `@app/store` itself imports `rbacReducer` back from the same
// barrel. The real app never notices because `App.tsx` always reaches
// `@app/store` first, before anything needs a fully-built reducer map. This
// module instead imports `rbacReducer` directly from the barrel as its first
// real import, which can resolve the cycle in the opposite order and leaves
// `@app/store`'s own (otherwise-unused-here) singleton assembled with a
// still-undefined `rbacReducer`, logging Redux's "No reducer provided for
// key rbac" warning. Importing `@app/store` first, exactly like `App.tsx`
// does, forces the same safe resolution order.
import '@app/store';

import { combineReducers, configureStore } from '@reduxjs/toolkit';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { RenderOptions } from '@testing-library/react';
import { render, screen, within } from '@testing-library/react';
import type { UserEvent } from '@testing-library/user-event';
import { PrimeReactProvider } from 'primereact/api';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';

import type { AppDispatch, RootState } from '@app/store';

import { rbacReducer } from '@core/rbac';

import authReducer from '@features/authentication/store/authSlice';

/**
 * Same reducer shape as the real store (`src/app/store/index.ts`), combined
 * explicitly rather than handed to `configureStore` as a plain map.
 *
 * `configureStore({ reducer: { auth, rbac } })` infers its `preloadedState`
 * parameter as the *exact* combined state shape (every slice required, no
 * `Partial`), because `@reduxjs/toolkit` 2.x no longer re-exports the
 * `PreloadedState<S>` helper type RTK 1.x used to widen it. Calling
 * `combineReducers()` up front gives a `Reducer<RootState, UnknownAction,
 * Partial<RootState>>`, whose own `PreloadedState` parameter already allows
 * omitting slices — passing that reducer to `configureStore` instead is what
 * lets a test seed only the `rbac` slice, say, and leave `auth` to its
 * default.
 */
const rootReducer = combineReducers({
  auth: authReducer,
  rbac: rbacReducer,
});

export type TestStore = ReturnType<typeof createTestStore>;
type TestPreloadedState = Partial<RootState>;

/**
 * Build a real store from the app's own reducers, optionally seeded with a
 * partial state (e.g. an authenticated user, or a set of RBAC menu keys).
 * A real store rather than a mock: the slices' own reducer logic is what
 * most tests around auth/RBAC actually want exercised.
 */
export const createTestStore = (preloadedState?: TestPreloadedState) =>
  configureStore({
    reducer: rootReducer,
    preloadedState,
    middleware: (getDefaultMiddleware) => getDefaultMiddleware({ serializableCheck: false }),
  });

/** A `QueryClient` tuned for tests: no retries, so a failing query fails fast. */
export const createTestQueryClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  });

interface ProvidersProps extends PropsWithChildren {
  store: TestStore;
  queryClient: QueryClient;
  initialEntries: string[];
}

const Providers = ({ store, queryClient, initialEntries, children }: ProvidersProps) => (
  <Provider store={store}>
    <QueryClientProvider client={queryClient}>
      {/*
        cssTransition: false — PrimeReact overlays (Dropdown, Dialog, ...) animate
        their enter/leave via react-transition-group, which relies on the browser's
        animation/transition-end events to know when to flip a panel from
        `display: none` to visible. jsdom never fires those, so with animations left
        on, an opened Dropdown's panel stays `display: none` forever and every
        option inside it is invisible to Testing Library's role queries. Disabling
        transitions makes PrimeReact apply the open/closed state synchronously.
      */}
      <PrimeReactProvider value={{ cssTransition: false }}>
        <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
      </PrimeReactProvider>
    </QueryClientProvider>
  </Provider>
);

export interface RenderWithProvidersOptions extends Omit<RenderOptions, 'wrapper'> {
  preloadedState?: TestPreloadedState;
  store?: TestStore;
  queryClient?: QueryClient;
  /** Initial router history, e.g. `['/masters/countries']`. Defaults to `['/']`. */
  initialEntries?: string[];
}

/**
 * Render a component wrapped in the app's real providers.
 *
 * Returns the store and query client alongside the usual Testing Library
 * result, so a test can dispatch further actions or inspect cache state
 * without threading them through manually.
 */
export const renderWithProviders = (
  ui: ReactElement,
  {
    preloadedState,
    store = createTestStore(preloadedState),
    queryClient = createTestQueryClient(),
    initialEntries = ['/'],
    ...renderOptions
  }: RenderWithProvidersOptions = {},
) => {
  return {
    store,
    queryClient,
    ...render(ui, {
      wrapper: ({ children }) => (
        <Providers store={store} queryClient={queryClient} initialEntries={initialEntries}>
          {children}
        </Providers>
      ),
      ...renderOptions,
    }),
  };
};

export type { AppDispatch, RootState, TestPreloadedState };

/**
 * Open a PrimeReact `<Dropdown>` and pick an option by its visible label.
 *
 * `getByLabelText(accessibleName)` finds the Dropdown's hidden a11y `<input>`
 * (`aria-label="..."`, `readonly`), which PrimeReact renders with
 * `pointer-events: none` — clicking it directly throws in user-event rather
 * than opening the panel. The actual trigger is a sibling `.p-dropdown-trigger`
 * inside the same `[data-pc-name="dropdown"]` container. Once open, options
 * render as `<li role="option">` inside a `role="listbox"`, each carrying the
 * label as both text and `aria-label` — matching on the accessible name
 * rather than raw text keeps this working if PrimeReact ever wraps the label
 * in extra markup.
 */
export const selectDropdownOption = async (
  user: UserEvent,
  accessibleName: string,
  optionLabel: string,
): Promise<void> => {
  const hiddenInput = screen.getByLabelText(accessibleName);
  const container = hiddenInput.closest('[data-pc-name="dropdown"]');
  if (!container) {
    throw new Error(`selectDropdownOption: no PrimeReact dropdown found for "${accessibleName}"`);
  }
  const trigger = container.querySelector<HTMLElement>('.p-dropdown-trigger');
  if (!trigger) {
    throw new Error(`selectDropdownOption: no trigger found for "${accessibleName}"`);
  }
  await user.click(trigger);

  const listbox = await screen.findByRole('listbox');
  await user.click(within(listbox).getByRole('option', { name: optionLabel }));
};

/**
 * Read the label currently shown on a *closed* PrimeReact `<Dropdown>`.
 *
 * PrimeReact additionally renders a visually-hidden native `<select>` with
 * one `<option>` per choice, for autofill/native-picker fallback — so once a
 * value is selected, `screen.getByText(theLabel)` matches twice (the hidden
 * option and the visible `.p-dropdown-label`) and throws. Scoping to
 * `.p-dropdown-label` reads only what is actually displayed.
 */
export const getDropdownLabel = (accessibleName: string): string => {
  const hiddenInput = screen.getByLabelText(accessibleName);
  const container = hiddenInput.closest('[data-pc-name="dropdown"]');
  if (!container) {
    throw new Error(`getDropdownLabel: no PrimeReact dropdown found for "${accessibleName}"`);
  }
  return container.querySelector('.p-dropdown-label')?.textContent ?? '';
};

/**
 * Find a react-hook-form/zod validation message by its text.
 *
 * Every master form renders its zod error in a `<small class="p-error">`
 * right below the field. A required Dropdown's own placeholder often reads
 * the same as the zod message it is paired with (both come from the same
 * "Select a country" string in the form), so once a Dropdown is genuinely
 * empty, `screen.getByText(...)` matches the placeholder, the validation
 * message, and (once selected) the hidden native `<option>` all at once and
 * throws. Scoping to `.p-error` finds only the validation message.
 */
export const getValidationError = (message: string): HTMLElement =>
  screen.getByText(message, { selector: '.p-error' });

// Re-export Testing Library's API so test files import everything from one
// module, matching the convention of centralising cross-cutting test helpers.
export * from '@testing-library/react';
