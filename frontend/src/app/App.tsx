/**
 * Root Application component.
 * Wraps the app with all necessary providers.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PrimeReactProvider } from 'primereact/api';
import { Provider } from 'react-redux';

import { AppRouter } from '@app/router/AppRouter';
import { store } from '@app/store';

import { readCspNonce } from '@shared/utils/cspNonce';

// Read once: it is fixed for the life of the page, and PrimeReact keeps its own copy.
const cspNonce = readCspNonce();

// TanStack Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export const App = () => {
  return (
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        {/* The nonce lets PrimeReact's runtime <style> elements through the CSP. */}
        <PrimeReactProvider value={{ nonce: cspNonce }}>
          <AppRouter />
        </PrimeReactProvider>
      </QueryClientProvider>
    </Provider>
  );
};
