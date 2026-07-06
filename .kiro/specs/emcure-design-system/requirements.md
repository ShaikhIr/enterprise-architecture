# Requirements Document

## Introduction

This feature implements the Emcure Design System across the React frontend application.
The design system standardises all visual language — tokens, layout, components, motion — through a single CSS variable layer and a library of reusable TypeScript/React components living in `src/shared/`.
The goal is a consistent, accessible, and maintainable UI that requires no external component frameworks (MUI, Ant Design, Chakra) beyond the already-approved PrimeReact library, which is theme-overridden to match the design system.
All design decisions are derived from `Theme_Design_System_Prompt.md`, the single source of truth.

---

## Glossary

- **Design_System**: The Emcure Design System — the complete set of tokens, base styles, and components defined in `Theme_Design_System_Prompt.md`.
- **Token_Layer**: The collection of CSS custom properties (`:root` variables) that encode every color, spacing, radius, shadow, and motion value used in the application.
- **Design_Token**: A single named CSS custom property belonging to the Token_Layer (e.g. `--color-primary`, `--space-4`).
- **Component_Library**: The set of reusable React components produced by this feature, placed under `src/shared/components/ui/`.
- **App**: The React frontend application located under `frontend/src/`.
- **MainLayout**: The root layout component at `src/app/layouts/MainLayout.tsx` that renders the Topbar, Sidebar, and main content area.
- **Topbar**: The fixed horizontal bar rendered at the top of every authenticated page (height `55px`, `z-index: 200`).
- **Sidebar**: The fixed vertical navigation panel (width `220px`) rendered on every authenticated page.
- **Flyout_Submenu**: A viewport-positioned dropdown that expands from a Sidebar navigation item when that item has child routes.
- **Page_Header**: A standardised card-style header placed at the top of every page content area, containing the page title, optional subtitle, and action buttons.
- **KPI_Card**: A metric display card showing an icon, numeric value, label, and optional delta chip.
- **Data_Grid**: The table component with toolbar, sticky column headers, row hover, striped rows, and paginator.
- **Status_Badge**: A pill-shaped label used to communicate record status (e.g. Active, Draft, Overdue).
- **Alert**: An inline notification component with a left colour-accent border, icon, title, and description.
- **Section_Title**: An uppercase all-caps label with a trailing horizontal rule used to group content within a page.
- **Poppins**: The primary sans-serif typeface loaded from Google Fonts.
- **JetBrains_Mono**: The monospace typeface used for code and technical content, loaded from Google Fonts.
- **CSS_Variable**: A CSS custom property prefixed with `--` resolved at runtime by the browser.
- **Hardcoded_Value**: Any color, spacing, radius, shadow, or font value written literally in code rather than referencing a CSS_Variable.

---

## Requirements

### Requirement 1: Design Token Layer

**User Story:** As a frontend developer, I want all visual values centralised as CSS custom properties, so that the entire application can be restyled from a single file without hunting for hardcoded values.

#### Acceptance Criteria

1. THE Design_System SHALL define all brand colors, neutral scale colors, semantic colors, typography families, spacing values, border radii, shadows, layout dimensions, and motion durations as CSS_Variables under `:root` in a dedicated file `src/assets/styles/tokens.css`.
2. THE Design_System SHALL expose the full neutral scale: `--color-neutral-0` through `--color-neutral-900` with values matching the specification exactly.
3. THE Design_System SHALL expose semantic colors `--color-success`, `--color-warning`, `--color-error`, and `--color-info` with values `#17c765`, `#ffa21e`, `#ef4444`, and `#3b82f6` respectively.
4. THE Design_System SHALL expose spacing tokens `--space-1` through `--space-12` in 4-pixel increments as specified.
5. THE Design_System SHALL expose border radius tokens `--radius-sm` (4px), `--radius-md` (8px), `--radius-lg` (12px), `--radius-xl` (16px), and `--radius-full` (9999px).
6. THE Design_System SHALL expose shadow tokens `--shadow-sm`, `--shadow-md`, `--shadow-lg`, `--shadow-primary-sm`, `--shadow-primary-md`, and `--shadow-dropdown` with values matching the specification.
7. THE Design_System SHALL expose layout tokens `--topbar-height` (55px) and `--sidenav-width` (220px).
8. THE Design_System SHALL expose motion tokens `--duration-fast` (150ms), `--duration-normal` (250ms), `--duration-slow` (400ms), `--ease-out`, and `--ease-spring`.
9. WHEN `tokens.css` is imported at the application root, THE App SHALL resolve all CSS_Variables throughout the component tree without additional configuration.
10. IF a component contains a Hardcoded_Value for color, spacing, radius, shadow, or font, THEN THE Design_System SHALL flag it as non-compliant and the value SHALL be replaced with the corresponding CSS_Variable.

---

### Requirement 2: Global Base Styles

**User Story:** As a frontend developer, I want consistent browser-reset and base typography styles applied globally, so that all pages start from the same visual foundation.

#### Acceptance Criteria

1. THE Design_System SHALL apply `box-sizing: border-box` to all elements via the `*, *::before, *::after` selector.
2. THE Design_System SHALL set `margin: 0; padding: 0` on all elements as part of the reset.
3. THE Design_System SHALL set the `body` font-family to `var(--font-sans)`, font-size to `14px`, color to `var(--color-neutral-900)`, background to `var(--color-neutral-100)`, and `-webkit-font-smoothing: antialiased`.
4. THE Design_System SHALL style anchor elements with `color: var(--color-primary)` and `text-decoration: none`.
5. THE Design_System SHALL style custom scrollbars using `-webkit-scrollbar` rules: 6px width/height, `--color-neutral-100` track, `--color-neutral-400` thumb with `--radius-full`, and `--color-primary` thumb on hover.
6. WHEN the Google Fonts stylesheet for Poppins (weights 300–800) and JetBrains_Mono (weights 400–500) is not present in `index.html`, THE App SHALL add the appropriate `<link>` tag to the `<head>` to load those fonts.

---

### Requirement 3: App Layout Structure

**User Story:** As a user, I want a consistent fixed-topbar and fixed-sidebar layout on every authenticated page, so that navigation is always accessible without scrolling.

#### Acceptance Criteria

1. THE MainLayout SHALL render a fixed Topbar at `top: 0; left: 0; right: 0; z-index: 200` with height equal to `var(--topbar-height)`.
2. THE MainLayout SHALL render a fixed Sidebar starting at `top: var(--topbar-height); left: 0; bottom: 0` with width equal to `var(--sidenav-width)`.
3. THE MainLayout SHALL render main content with `margin-left: var(--sidenav-width)` and `padding: calc(var(--topbar-height) + 24px) 24px 24px` so content is never obscured by the Topbar or Sidebar.
4. THE Topbar SHALL have a white background, a `1px solid var(--color-neutral-200)` bottom border, and `box-shadow: 0 2px 10px rgba(33,35,38,.08)`.
5. THE Topbar SHALL display the brand logo on the left with `color: var(--color-primary)`, `font-weight: 800`, and `font-size: 20px`.
6. THE Topbar SHALL display a notification bell button of `34×34px` with a positioned badge, and a user avatar of `32×32px` on the right.
7. WHEN the user hovers over the notification bell, THE Topbar SHALL animate the bell icon using a `bellRing` keyframe wiggle animation.
8. THE Sidebar SHALL have a white background and `border-right: 1px solid var(--color-neutral-200)`.
9. THE Sidebar SHALL NOT apply `overflow: hidden` to its shell element, so that Flyout_Submenus can escape the sidebar boundary.
10. THE Sidebar SHALL use an inner scroll wrapper with `overflow-y: auto; overflow-x: visible` for the navigation list.
11. THE Sidebar SHALL render navigation group labels at `font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: var(--color-neutral-500)`.
12. THE Sidebar SHALL style navigation links at `font-size: 13px; font-weight: 500` with default color `var(--color-neutral-600)`, hover `background: var(--color-primary-50); color: var(--color-primary)`, and active `background: var(--color-primary); color: #fff`.
13. WHEN a Sidebar navigation item has child routes, THE Sidebar SHALL render a Flyout_Submenu positioned using `position: fixed` coordinates calculated via `getBoundingClientRect()` to the right of the Sidebar with an 8px gap.
14. WHEN the mouse leaves a Sidebar navigation item, THE Sidebar SHALL delay hiding the Flyout_Submenu by 150ms so the user can move the pointer to the flyout without it closing.
15. THE Flyout_Submenu SHALL animate open using `opacity` (0 to 1) and `translateX(-10px to 0)` over `var(--duration-normal)` with `var(--ease-out)`.
16. THE Flyout_Submenu SHALL have `z-index: 9999` to appear above all other content.
17. THE Flyout_Submenu SHALL include a red gradient left-accent stripe inside the flyout panel.

---

### Requirement 4: Button Component

**User Story:** As a frontend developer, I want a reusable Button component that covers all design-system variants, so that every button in the application is visually consistent without duplicating styles.

#### Acceptance Criteria

1. THE Component_Library SHALL provide a `Button` component accepting a `variant` prop of `primary | secondary | ghost | danger | save | delete | sm`.
2. THE Button SHALL apply `border-radius: var(--radius-full)` (pill shape) to all variants.
3. THE Button SHALL apply `font-size: 13px; font-weight: 600` to all variants.
4. THE Button SHALL render the `primary` variant with `linear-gradient(135deg, #ff4d54 0%, #ed1c24 45%, #b00e14 100%)` background, white text, and `box-shadow: var(--shadow-primary-md)`.
5. THE Button SHALL render the `secondary` variant with white background, `1px solid var(--color-neutral-300)` border, and dark text; WHEN hovered, THE Button SHALL apply red border and red text.
6. THE Button SHALL render the `ghost` variant with transparent background and `var(--color-primary)` text; WHEN hovered, THE Button SHALL apply `background: var(--color-primary-50)`.
7. THE Button SHALL render the `danger` variant with `var(--color-primary)` background and white text.
8. THE Button SHALL render the `save` variant with a green gradient background and white text.
9. THE Button SHALL render the `delete` variant with a light red background and red text.
10. THE Button SHALL render the `sm` variant with `padding: 5px 14px; font-size: 12px; min-height: 30px`.
11. WHEN the `disabled` attribute is set on the Button, THE Button SHALL apply `opacity: 0.45; cursor: not-allowed; filter: grayscale(0.4)` and SHALL NOT fire click events.
12. WHEN the Button is pressed (active state), THE Button SHALL apply `transform: translateY(1px) scale(0.98)`.
13. WHEN the Button is hovered, THE Button SHALL animate a shine sweep via a `::before` pseudo-element sliding from `-100%` to `100%` over `var(--duration-normal)`.

---

### Requirement 5: Form Controls

**User Story:** As a user, I want all form inputs, textareas, and selects to look and behave consistently, so that filling in forms feels predictable throughout the application.

#### Acceptance Criteria

1. THE Component_Library SHALL provide a `FormControl` component that applies `.form-control` styles to `input`, `textarea`, and `select` elements.
2. THE FormControl SHALL apply `width: 100%; font-family: var(--font-sans); font-size: 13px; color: var(--color-neutral-900); background: #fff; border: 1px solid var(--color-neutral-300); border-radius: var(--radius-md); padding: 8px 12px; min-height: 38px; outline: none`.
3. WHEN the FormControl is hovered, THE FormControl SHALL change its border color to `var(--color-neutral-400)`.
4. WHEN the FormControl receives focus, THE FormControl SHALL change its border color to `var(--color-primary)` and apply `box-shadow: var(--shadow-primary-sm)`.
5. WHEN the FormControl is disabled, THE FormControl SHALL apply `background: var(--color-neutral-100); color: var(--color-neutral-500)`.
6. THE Component_Library SHALL provide a `FormLabel` component styled with `font-size: 12px; font-weight: 600; color: var(--color-neutral-700); margin-bottom: 6px`.
7. THE Component_Library SHALL provide a `CustomDropdown` component styled as a `.form-control` trigger with a chevron icon.
8. WHEN the CustomDropdown is opened, THE CustomDropdown SHALL apply `border-color: var(--color-primary)` and square the bottom border corners to visually connect to the dropdown panel.
9. THE CustomDropdown dropdown panel SHALL have `border: 1px solid var(--color-primary); box-shadow: var(--shadow-dropdown); border-radius: var(--radius-md)` on the bottom corners.
10. WHEN an option in the CustomDropdown is hovered, THE CustomDropdown SHALL apply `background: var(--color-primary-50); color: var(--color-primary)`.
11. WHEN an option in the CustomDropdown is selected, THE CustomDropdown SHALL apply `background: var(--color-primary-100); font-weight: 500`.
12. WHEN the CustomDropdown opens, THE CustomDropdown SHALL animate the dropdown panel using a `dropIn` keyframe: `opacity 0→1` and `translateY(-4px→0)` over `var(--duration-normal)`.

---

### Requirement 6: Card Component

**User Story:** As a frontend developer, I want a reusable Card component with header and body slots, so that content containers are visually consistent across all pages.

#### Acceptance Criteria

1. THE Component_Library SHALL provide a `Card` component with `background: #fff; border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); border: 1px solid var(--color-neutral-200)`.
2. THE Component_Library SHALL provide a `CardHeader` sub-component with `padding: var(--space-4) var(--space-5); border-bottom: 1px solid var(--color-neutral-200); font-size: 14px; font-weight: 600; color: var(--color-neutral-800)`.
3. THE Component_Library SHALL provide a `CardBody` sub-component with `padding: var(--space-5)`.
4. THE Card SHALL accept optional `header` and `children` props to render CardHeader and CardBody respectively.

---

### Requirement 7: Page Header Component

**User Story:** As a frontend developer, I want a standardised Page Header component, so that every page in the application starts with a consistent title, subtitle, and action area.

#### Acceptance Criteria

1. THE Component_Library SHALL provide a `PageHeader` component styled as `.page-header` with `background: #fff; border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); padding: var(--space-5); margin-bottom: var(--space-5); display: flex; align-items: center; justify-content: space-between; border: 1px solid var(--color-neutral-200)`.
2. THE PageHeader SHALL accept a `title` prop rendered at `font-size: 20px; font-weight: 700`.
3. THE PageHeader SHALL accept an optional `subtitle` prop rendered at `font-size: 13px; color: var(--color-neutral-600)`.
4. THE PageHeader SHALL accept an optional `actions` prop rendered as a right-aligned slot for action buttons.
5. WHEN a page is rendered inside MainLayout, THE page SHALL include a PageHeader as the first element in the content area.

---

### Requirement 8: Status Badge Component

**User Story:** As a user, I want colour-coded status badges on records and workflow items, so that I can instantly recognise the status of each item without reading text carefully.

#### Acceptance Criteria

1. THE Component_Library SHALL provide a `StatusBadge` component with `border-radius: var(--radius-full); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em`.
2. THE StatusBadge SHALL include a `::before` pseudo-element dot in `currentColor`.
3. THE StatusBadge SHALL support variant `success` with `background: rgba(23,199,101,.1); color: #17c765`.
4. THE StatusBadge SHALL support variant `warning` with `background: rgba(255,162,30,.1); color: #ffa21e`.
5. THE StatusBadge SHALL support variant `error` with `background: rgba(239,68,68,.12); color: #c81515`.
6. THE StatusBadge SHALL support variant `info` with `background: rgba(105,90,205,.15); color: #6a5acd`.
7. THE StatusBadge SHALL support variant `draft` with `background: #d9f3b1; color: #73a327`.
8. THE StatusBadge SHALL support gradient variant `completed` with `linear-gradient(145deg, #00cc00, #009900)` background and white text.
9. THE StatusBadge SHALL support gradient variant `overdue` with `linear-gradient(145deg, #ff3333, #b30000)` background and white text.
10. THE StatusBadge SHALL support gradient variant `waiting` with `linear-gradient(145deg, #fff176, #fbc02d)` background and dark text.
11. THE StatusBadge SHALL support gradient variant `assigned` with `linear-gradient(145deg, #e0e0e0, #bdbdbd)` background and dark text.
12. THE StatusBadge SHALL support gradient variant `referred` with `linear-gradient(145deg, #ffb347, #ff6600)` background and white text.

---

### Requirement 9: Alert Component

**User Story:** As a user, I want inline notification alerts with clear colour-coded borders and icons, so that system messages are immediately noticeable without relying on toast notifications alone.

#### Acceptance Criteria

1. THE Component_Library SHALL provide an `Alert` component with `border-left: 4px solid currentColor; padding: var(--space-3) var(--space-4); border-radius: var(--radius-md); font-size: 13px`.
2. THE Alert SHALL accept a `variant` prop of `success | warning | error | info`.
3. THE Alert SHALL accept optional `title`, `message`, and `icon` props.
4. THE Alert SHALL render variant `success` with `background: rgba(23,199,101,.08); color: #15803d`.
5. THE Alert SHALL render variant `warning` with `background: rgba(255,162,30,.08); color: #b45309`.
6. THE Alert SHALL render variant `error` with `background: rgba(239,68,68,.08); color: #b91c1c`.
7. THE Alert SHALL render variant `info` with `background: rgba(59,130,246,.08); color: #1d4ed8`.

---

### Requirement 10: KPI Card Component

**User Story:** As a user, I want KPI/metric cards on the dashboard, so that key numbers are displayed prominently with context about trends.

#### Acceptance Criteria

1. THE Component_Library SHALL provide a `KpiCard` component with `background: #fff; border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); padding: var(--space-5); border: 1px solid transparent; display: flex; align-items: center; gap: var(--space-4); min-height: 84px`.
2. WHEN the KpiCard is hovered, THE KpiCard SHALL apply `border-color: var(--color-primary); box-shadow: var(--shadow-primary-md); transform: translateY(-2px); transition: all var(--duration-normal) var(--ease-spring)`.
3. THE KpiCard SHALL render an icon box of `46×46px` with `border-radius: var(--radius-md)` and a colored background chosen from the six design-system icon color variants: red, green, orange, blue, violet, and slate.
4. THE KpiCard SHALL accept a `value` prop rendered at `font-size: 22px; font-weight: 700; color: var(--color-neutral-900)`.
5. THE KpiCard SHALL accept a `label` prop rendered at `font-size: 12px; color: var(--color-neutral-600); margin-top: 4px`.
6. THE KpiCard SHALL accept an optional `delta` prop; WHEN positive, THE KpiCard SHALL render the delta chip with a green tint; WHEN negative, THE KpiCard SHALL render the delta chip with a red tint; both with `border-radius: var(--radius-full)`.
7. WHEN multiple KpiCards are displayed together, THE Component_Library SHALL provide a `KpiGrid` wrapper with `grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-4)`.

---

### Requirement 11: Data Grid Component

**User Story:** As a user, I want a consistent data grid with search, sticky headers, row highlighting, and pagination, so that I can quickly find and interact with tabular data across all management pages.

#### Acceptance Criteria

1. THE Component_Library SHALL provide a `DataGrid` component wrapped in `.datagrid-wrap` with `background: #fff; border-radius: var(--radius-lg); border: 1px solid var(--color-neutral-200); box-shadow: var(--shadow-sm); overflow: hidden`.
2. THE DataGrid SHALL render a toolbar area containing a search input (max-width 280px) and optional filter/action buttons, separated from the table by a `border-bottom`.
3. THE DataGrid toolbar search input SHALL have a left-padded search icon; WHEN focused, THE search input SHALL apply `border-color: var(--color-primary)` and `box-shadow: var(--shadow-primary-sm)`.
4. THE DataGrid SHALL render table column headers with `background: var(--color-neutral-50)`, `position: sticky; top: 0`, `font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--color-neutral-500)`; WHEN a header is hovered, THE DataGrid SHALL change the header color to `var(--color-primary)`.
5. THE DataGrid SHALL render table rows at `font-size: 13px` with cell padding `11px 16px`; WHEN a row is hovered, THE DataGrid SHALL apply `background: var(--color-primary-50)`; even-indexed rows SHALL have `background: var(--color-neutral-50)`.
6. THE DataGrid SHALL render a footer with record count on the left and pagination controls on the right at `font-size: 12px; color: var(--color-neutral-500)`.
7. THE DataGrid pagination buttons SHALL be `28×28px` with `border-radius: var(--radius-sm)`; WHEN a pagination button is active, THE DataGrid SHALL apply `background: var(--color-primary); color: #fff`.
8. THE DataGrid SHALL accept `columns`, `data`, `loading`, `totalRecords`, `page`, `pageSize`, `onPageChange`, and `onSearch` props as a typed interface.

---

### Requirement 12: Section Title Component

**User Story:** As a frontend developer, I want a reusable Section Title component, so that content groups within a page are visually separated with a consistent heading style.

#### Acceptance Criteria

1. THE Component_Library SHALL provide a `SectionTitle` component with `font-size: 11px; font-weight: 700; color: var(--color-neutral-500); letter-spacing: 0.12em; text-transform: uppercase; display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-5)`.
2. THE SectionTitle SHALL render a trailing decorative line via `::after` pseudo-element: `flex: 1; height: 1px; background: var(--color-neutral-200)`.
3. THE SectionTitle SHALL accept a `children` prop for the label text.

---

### Requirement 13: Motion and Animation Standards

**User Story:** As a user, I want all interface transitions and animations to feel smooth and consistent, so that the application has a polished, professional character.

#### Acceptance Criteria

1. THE Design_System SHALL use `var(--duration-fast)` (150ms) and `var(--ease-out)` for micro-interactions such as hover and focus state changes.
2. THE Design_System SHALL use `var(--duration-normal)` (250ms) and `var(--ease-out)` for panel open/close and dropdown transitions.
3. THE Design_System SHALL use `var(--duration-slow)` (400ms) and `var(--ease-spring)` for entrance animations and card lift effects.
4. IF an animation involves a width or height change, THEN THE Design_System SHALL use `transform` and `opacity` instead of animating `width` or `height` directly.
5. THE Flyout_Submenu SHALL animate using `opacity` and `translateX(-10px to 0)` on open.
6. THE Button shine sweep `::before` pseudo-element SHALL animate by sliding from `translateX(-100%)` to `translateX(100%)` on hover over `var(--duration-normal)`.
7. THE Topbar bell icon SHALL animate using the `bellRing` keyframe on hover.

---

### Requirement 14: Utility Classes

**User Story:** As a frontend developer, I want a set of shared utility CSS classes, so that minor formatting adjustments don't require creating new component variants.

#### Acceptance Criteria

1. THE Design_System SHALL define `.text-muted` with `color: var(--color-neutral-500)`.
2. THE Design_System SHALL define `.text-sm` with `font-size: 12px`.
3. THE Design_System SHALL define `.text-xs` with `font-size: 11px`.
4. THE Design_System SHALL define `.fw-600` with `font-weight: 600`.
5. THE Design_System SHALL define `.fw-700` with `font-weight: 700`.
6. THE Design_System SHALL define `.mb-5` with `margin-bottom: var(--space-5)`.
7. THE Design_System SHALL define `.btn-group` with `display: flex; gap: var(--space-2)`.

---

### Requirement 15: Component File Structure and Conventions

**User Story:** As a frontend developer, I want all design-system components placed in a predictable folder structure following project conventions, so that components are discoverable and imports are consistent.

#### Acceptance Criteria

1. THE Component_Library SHALL place all reusable design-system components under `src/shared/components/ui/`.
2. THE Component_Library SHALL place all design-system CSS files under `src/assets/styles/`, with `tokens.css` as the root token file and `base.css` for global base styles and utilities.
3. THE Component_Library SHALL export all components from a single barrel file `src/shared/components/ui/index.ts`.
4. WHEN a component is created, THE Component_Library SHALL use TypeScript strict mode, define all prop types as named interfaces, and include a JSDoc comment describing the component's purpose and usage.
5. THE Component_Library SHALL NOT use the `any` TypeScript type in component props or internal logic.
6. WHEN CSS is co-located with a component, THE Component_Library SHALL use a `.module.css` file with the same name as the component; global/shared styles SHALL remain in `src/assets/styles/`.
7. THE App SHALL import `tokens.css` and `base.css` in `src/main.tsx` before all other stylesheets so that CSS variables are available globally.
8. WHEN a new page component is created, THE page SHALL consume `PageHeader`, `Card`, and other design-system components rather than replicating the styles inline.

---

### Requirement 16: PrimeReact Theme Alignment

**User Story:** As a frontend developer, I want PrimeReact component overrides in `theme-overrides.css` to be updated to reference the canonical design tokens, so that PrimeReact components visually match the Emcure Design System without divergence.

#### Acceptance Criteria

1. THE Design_System SHALL update `src/assets/styles/theme-overrides.css` to reference the full token set from `tokens.css` for all color, spacing, radius, and shadow overrides.
2. THE Design_System SHALL add the missing neutral scale tokens (`--color-neutral-600`, `--color-neutral-700`, `--color-neutral-800`, `--color-neutral-900`) and full primary scale (`--color-primary-active`, `--color-primary-200`) to `theme-overrides.css` until `tokens.css` is the single token source.
3. THE Design_System SHALL update PrimeReact `.p-button` overrides to use `--radius-full` (pill shape) consistent with the design-system Button variants.
4. THE Design_System SHALL ensure PrimeReact `.p-datatable` overrides align with the DataGrid component requirements: sticky headers, `--color-primary-50` row hover, and pagination button sizing.
5. WHEN `theme-overrides.css` is updated, THE Design_System SHALL verify that existing pages (UserListPage, LoginPage, RolesPage, AuditLogsPage) remain visually correct.
