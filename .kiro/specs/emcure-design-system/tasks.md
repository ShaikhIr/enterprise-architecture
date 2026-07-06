# Implementation Plan: Emcure Design System

## Overview

Implement the Emcure Design System across the React frontend by establishing a CSS variable token layer, global base styles, a reusable TypeScript/React component library, a refactored MainLayout, and PrimeReact theme alignment. All components are placed under `src/shared/components/ui/` and consumed via a barrel export.

## Tasks

- [x] 1. Set up CSS token layer and global base styles
  - [x] 1.1 Create `src/assets/styles/tokens.css` with all `:root` CSS custom properties
    - Define all brand/primary color tokens: `--color-primary` (#ed1c24), `--color-primary-hover`, `--color-primary-active`, `--color-primary-50`, `--color-primary-100`, `--color-primary-200`
    - Define the full neutral scale: `--color-neutral-0` through `--color-neutral-900` (10 stops)
    - Define semantic colors: `--color-success` (#17c765), `--color-warning` (#ffa21e), `--color-error` (#ef4444), `--color-info` (#3b82f6)
    - Define typography tokens: `--font-sans`, `--font-mono`
    - Define spacing tokens `--space-1` (4px) through `--space-12` (48px) in 4px increments, skipping 7, 9, 11
    - Define radius tokens: `--radius-sm` (4px), `--radius-md` (8px), `--radius-lg` (12px), `--radius-xl` (16px), `--radius-full` (9999px)
    - Define shadow tokens: `--shadow-sm`, `--shadow-md`, `--shadow-lg`, `--shadow-primary-sm`, `--shadow-primary-md`, `--shadow-dropdown`
    - Define layout tokens: `--topbar-height` (55px), `--sidenav-width` (220px)
    - Define motion tokens: `--duration-fast` (150ms), `--duration-normal` (250ms), `--duration-slow` (400ms), `--ease-out`, `--ease-spring`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [x] 1.2 Create `src/assets/styles/base.css` with global reset, typography, scrollbars, and utility classes
    - Apply `box-sizing: border-box` to `*, *::before, *::after`
    - Apply `margin: 0; padding: 0` reset to all elements
    - Style `body` with `var(--font-sans)`, 14px font-size, `var(--color-neutral-900)` color, `var(--color-neutral-100)` background, and `-webkit-font-smoothing: antialiased`
    - Style anchor elements with `color: var(--color-primary); text-decoration: none`
    - Add custom scrollbar styles using `-webkit-scrollbar` rules (6px, neutral track, primary thumb on hover)
    - Add utility classes: `.text-muted`, `.text-sm`, `.text-xs`, `.fw-600`, `.fw-700`, `.mb-5`, `.btn-group`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_

  - [x] 1.3 Update `index.html` to include Google Fonts `<link>` for Poppins (weights 300–800) and JetBrains Mono (weights 400–500)
    - _Requirements: 2.6_

  - [x] 1.4 Update `src/main.tsx` to import CSS files in the correct cascade order
    - Import PrimeReact theme, components, icons, and PrimeFlex first
    - Then import `tokens.css`, `base.css`, `theme-overrides.css` in that order
    - _Requirements: 1.9, 15.7_

- [x] 2. Implement Button component
  - [x] 2.1 Create `src/shared/components/ui/Button/Button.tsx` and `Button.module.css`
    - Define `ButtonVariant` type and `ButtonProps` interface with JSDoc
    - Implement all 7 variants: `primary`, `secondary`, `ghost`, `danger`, `save`, `delete`, `sm`
    - Apply pill shape (`--radius-full`), `font-size: 13px`, `font-weight: 600` to all variants
    - Implement `primary` gradient background with `--shadow-primary-md`
    - Implement `secondary` white background with red border/text on hover
    - Implement `ghost` transparent with primary text and `--color-primary-50` hover
    - Implement `danger`, `save`, `delete` variants per spec
    - Implement `sm` size modifier: `padding: 5px 14px; font-size: 12px; min-height: 30px`
    - Add disabled state: `opacity: 0.45; cursor: not-allowed; filter: grayscale(0.4)` — no click events
    - Add active press state: `transform: translateY(1px) scale(0.98)`
    - Add hover shine sweep via `::before` pseudo-element sliding `translateX(-100%)` → `translateX(100%)` over `--duration-normal`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13_

  - [x] 2.2 Write property test for Button — Property 1: Disabled button blocks all click events
    - **Property 1: Disabled Button Blocks All Click Events**
    - Use `fc.constantFrom` over all non-`sm` variants; assert `onClick` is never called when `disabled` is `true`
    - **Validates: Requirements 4.11**

  - [x] 2.3 Write unit tests for Button component
    - Test each variant renders with its expected CSS module class
    - Test `sm` size modifier applies correct padding/font-size classes
    - Test disabled state prevents click and applies correct CSS classes
    - Test active and hover class application
    - _Requirements: 4.1–4.13_

- [x] 3. Implement FormControl, FormLabel, and CustomDropdown components
  - [x] 3.1 Create `src/shared/components/ui/FormControl/FormControl.tsx` and `FormControl.module.css`
    - Define `FormControlProps` interface extending native input/textarea/select attributes
    - Support `as` prop switching between `input`, `textarea`, `select`
    - Apply base styles: `width: 100%`, `--font-sans`, `13px`, `--color-neutral-900`, white background, `--color-neutral-300` border, `--radius-md`, `padding: 8px 12px`, `min-height: 38px`, `outline: none`
    - Add hover border color `--color-neutral-400`
    - Add focus border `--color-primary` with `--shadow-primary-sm`
    - Add disabled state: `--color-neutral-100` background, `--color-neutral-500` text
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 3.2 Create `src/shared/components/ui/FormControl/FormLabel.tsx`
    - Define `FormLabelProps` with `htmlFor` and `children`
    - Style: `font-size: 12px; font-weight: 600; color: var(--color-neutral-700); margin-bottom: 6px`
    - _Requirements: 5.6_

  - [x] 3.3 Create `src/shared/components/ui/FormControl/CustomDropdown.tsx`
    - Define `DropdownOption` and `CustomDropdownProps` interfaces with JSDoc
    - Render trigger styled as `.form-control` with a chevron icon
    - On open: apply `--color-primary` border and square bottom corners on trigger; connect visually to panel
    - Render dropdown panel in a portal with `border: 1px solid var(--color-primary); --shadow-dropdown; --radius-md` on bottom corners
    - Add `dropIn` keyframe animation on panel: `opacity 0→1` + `translateY(-4px)→translateY(0)` over `--duration-normal`
    - Add hover state for options: `--color-primary-50` background, `--color-primary` text
    - Add selected state for options: `--color-primary-100` background, `font-weight: 500`
    - _Requirements: 5.7, 5.8, 5.9, 5.10, 5.11, 5.12_

  - [x] 3.4 Write unit tests for FormControl, FormLabel, and CustomDropdown
    - Test FormControl renders each element type (`input`, `textarea`, `select`)
    - Test hover/focus/disabled class toggling on FormControl
    - Test CustomDropdown opens on click; option hover and selected styles applied; panel animation class present
    - _Requirements: 5.1–5.12_

- [x] 4. Implement Card, PageHeader, and SectionTitle components
  - [x] 4.1 Create `src/shared/components/ui/Card/Card.tsx` and `Card.module.css`
    - Define `CardProps`, `CardHeaderProps`, `CardBodyProps` interfaces with JSDoc
    - Implement `Card` root: `background: #fff; --radius-lg; --shadow-sm; 1px solid --color-neutral-200`
    - Implement `CardHeader`: `padding: --space-4 --space-5; border-bottom: 1px solid --color-neutral-200; 14px; font-weight 600; --color-neutral-800`
    - Implement `CardBody`: `padding: --space-5`
    - Render `CardHeader` when `header` prop is provided
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 4.2 Create `src/shared/components/ui/PageHeader/PageHeader.tsx` and `PageHeader.module.css`
    - Define `PageHeaderProps` interface with JSDoc
    - Style `.page-header`: `background: #fff; --radius-lg; --shadow-sm; padding: --space-5; margin-bottom: --space-5; flex; align-items: center; justify-content: space-between; 1px solid --color-neutral-200`
    - Render `title` at `font-size: 20px; font-weight: 700`
    - Render optional `subtitle` at `font-size: 13px; color: --color-neutral-600`
    - Render optional `actions` in right-aligned slot
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 4.3 Create `src/shared/components/ui/SectionTitle/SectionTitle.tsx` and `SectionTitle.module.css`
    - Define `SectionTitleProps` interface with JSDoc
    - Style: `font-size: 11px; font-weight: 700; --color-neutral-500; letter-spacing: 0.12em; uppercase; flex; align-items: center; gap: --space-3; margin-bottom: --space-5`
    - Add `::after` trailing line: `flex: 1; height: 1px; background: --color-neutral-200`
    - _Requirements: 12.1, 12.2, 12.3_

  - [x] 4.4 Write unit tests for Card, PageHeader, and SectionTitle
    - Test Card renders header only when `header` prop is provided; body renders children
    - Test PageHeader title renders; subtitle absent when omitted; actions slot renders
    - Test SectionTitle renders children label; decorative trailing line style is present
    - _Requirements: 6.1–6.4, 7.1–7.4, 12.1–12.3_

- [x] 5. Implement StatusBadge and Alert components
  - [x] 5.1 Create `src/shared/components/ui/StatusBadge/StatusBadge.tsx` and `StatusBadge.module.css`
    - Define `StatusBadgeVariant` type and `StatusBadgeProps` interface with JSDoc
    - Apply base styles to all variants: `--radius-full; 11px; font-weight 600; uppercase; letter-spacing 0.04em; ::before dot`
    - Implement flat variants: `success`, `warning`, `error`, `info`, `draft` with their respective background/text tokens
    - Implement gradient variants: `completed`, `overdue`, `waiting`, `assigned`, `referred` with their CSS `linear-gradient` backgrounds and correct text colors (white vs dark)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12_

  - [x] 5.2 Create `src/shared/components/ui/Alert/Alert.tsx` and `Alert.module.css`
    - Define `AlertVariant` type and `AlertProps` interface with JSDoc
    - Apply base styles: `border-left: 4px solid currentColor; padding: --space-3 --space-4; --radius-md; font-size: 13px`
    - Implement `success` variant: `rgba(23,199,101,.08)` background, `#15803d` text
    - Implement `warning` variant: `rgba(255,162,30,.08)` background, `#b45309` text
    - Implement `error` variant: `rgba(239,68,68,.08)` background, `#b91c1c` text
    - Implement `info` variant: `rgba(59,130,246,.08)` background, `#1d4ed8` text
    - Conditionally render `title`, `message`, and `icon` slots
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [x] 5.3 Write unit tests for StatusBadge and Alert
    - Test each of the 12 StatusBadge variants renders with the expected CSS module class
    - Test Alert: each of 4 variants applies correct class; title/message render conditionally; icon slot renders when provided
    - _Requirements: 8.1–8.12, 9.1–9.7_

- [x] 6. Implement KpiCard and KpiGrid components
  - [x] 6.1 Create `src/shared/components/ui/KpiCard/KpiCard.tsx`, `KpiGrid.tsx`, and `KpiCard.module.css`
    - Define `KpiIconColor`, `KpiCardProps`, `KpiGridProps` interfaces with JSDoc
    - Implement `KpiCard` base: `background: #fff; --radius-lg; --shadow-sm; padding: --space-5; 1px solid transparent; flex; align-items: center; gap: --space-4; min-height: 84px`
    - Add hover lift: `border-color: --color-primary; --shadow-primary-md; transform: translateY(-2px); transition: all --duration-normal --ease-spring`
    - Implement icon box: `46×46px; --radius-md` with 6 color variants (red, green, orange, blue, violet, slate)
    - Render `value` at `font-size: 22px; font-weight: 700; --color-neutral-900`
    - Render `label` at `font-size: 12px; --color-neutral-600; margin-top: 4px`
    - Render optional `delta` chip: positive → green tint with `.deltaPositive` class; negative → red tint with `.deltaNegative` class; zero → neutral grey; both with `--radius-full`
    - Implement `KpiGrid` wrapper: `grid; repeat(auto-fill, minmax(200px, 1fr)); gap: --space-4`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

  - [x] 6.2 Write property test for KpiCard — Property 2: Delta chip color tracks sign
    - **Property 2: KpiCard Delta Chip Color Tracks Sign**
    - Use `fc.integer({ min: 1, max: 100_000 })` for positive delta and `fc.integer({ min: -100_000, max: -1 })` for negative
    - Assert positive delta renders `.deltaPositive` (not `.deltaNegative`); negative delta renders `.deltaNegative` (not `.deltaPositive`)
    - **Validates: Requirements 10.6**

  - [x] 6.3 Write unit tests for KpiCard and KpiGrid
    - Test icon box renders with correct color class for each `iconColor` variant
    - Test `delta` chip absent when prop is undefined; present and correct class when provided
    - Test `KpiGrid` renders children in a grid wrapper
    - _Requirements: 10.1–10.7_

- [x] 7. Implement DataGrid component
  - [x] 7.1 Create `src/shared/components/ui/DataGrid/DataGrid.tsx` and `DataGrid.module.css`
    - Define `DataGridColumn<T>` and `DataGridProps<T>` interfaces with JSDoc; no `any` types
    - Implement outer wrapper `.datagrid-wrap`: `background: #fff; --radius-lg; 1px solid --color-neutral-200; --shadow-sm; overflow: hidden`
    - Implement toolbar: search input (max-width 280px) with left-padded search icon and optional `toolbarActions` slot; separated by `border-bottom`
    - Search input: `--color-primary` border and `--shadow-primary-sm` on focus
    - Implement table with sticky headers: `background: --color-neutral-50; position: sticky; top: 0; font-size: 11px; font-weight: 700; uppercase; letter-spacing: 0.06em; --color-neutral-500`; header hover → `--color-primary`
    - Implement table rows: `font-size: 13px; cell padding: 11px 16px`; hover → `--color-primary-50` background
    - Apply even-row striping: even-indexed rows (`rowEven` class) get `--color-neutral-50` background
    - Implement loading state: render skeleton rows when `loading` is `true`
    - Implement footer: record count left, pagination controls right (`font-size: 12px; --color-neutral-500`)
    - Pagination buttons: `28×28px; --radius-sm`; active button → `--color-primary` background, white text
    - Call `onSearch` handler on search input change; call `onPageChange` on pagination click
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

  - [x] 7.2 Write property test for DataGrid — Property 3: Even-row striping invariant
    - **Property 3: DataGrid Even-Row Striping Invariant**
    - Use `fc.array(fc.record({ id: fc.nat(), name: fc.string() }), { minLength: 1, maxLength: 50 })`
    - Assert every even-indexed `tbody tr` has the `rowEven` class; every odd-indexed row does not
    - **Validates: Requirements 11.5**

  - [x] 7.3 Write unit tests for DataGrid component
    - Test toolbar renders with search input and `toolbarActions` slot
    - Test column headers render with correct sticky/style classes
    - Test pagination footer renders when `totalRecords` is provided
    - Test `onSearch` is called on input change; `onPageChange` called on page button click
    - _Requirements: 11.1–11.8_

- [x] 8. Checkpoint — Core component library complete
  - Ensure all component files and module CSS are present under `src/shared/components/ui/`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Create barrel export and set up test infrastructure
  - [x] 9.1 Create `src/shared/components/ui/index.ts` barrel file exporting all UI components
    - Export `Button`, `FormControl`, `FormLabel`, `CustomDropdown`, `Card`, `CardHeader`, `CardBody`, `PageHeader`, `StatusBadge`, `Alert`, `KpiCard`, `KpiGrid`, `DataGrid`, `SectionTitle`
    - _Requirements: 15.3_

  - [x] 9.2 Set up property-based test file `frontend/tests/unit/ui-properties.test.tsx`
    - Install `fast-check` as a dev dependency if not already present
    - Set up Vitest test file with imports for `fc` (fast-check), Vitest matchers, and `@testing-library/react`
    - _Requirements: 15.4, 15.5_

- [x] 10. Implement MainLayout, Topbar, Sidebar, and FlyoutSubmenu
  - [x] 10.1 Create `src/app/layouts/Topbar.tsx` and contribute to `MainLayout.module.css`
    - Define `TopbarProps` interface with JSDoc
    - Apply fixed positioning: `top: 0; left: 0; right: 0; z-index: 200; height: var(--topbar-height)`
    - Style: `background: #fff; border-bottom: 1px solid --color-neutral-200; box-shadow: 0 2px 10px rgba(33,35,38,.08)`
    - Render brand logo (left): `--color-primary; font-weight: 800; font-size: 20px`
    - Render notification bell button `34×34px` with positioned badge; animate bell with `bellRing` keyframe on hover
    - Render user avatar `32×32px` (right)
    - _Requirements: 3.1, 3.4, 3.5, 3.6, 3.7_

  - [x] 10.2 Create `src/app/layouts/FlyoutSubmenu.tsx`
    - Define `FlyoutSubmenuProps` and `NavItem` interfaces with JSDoc
    - Position using `position: fixed` with coordinates from `anchorRect` (via `getBoundingClientRect()`) + 8px gap to the right of the sidebar
    - Guard against rendering when `anchorRect` has zero dimensions
    - Clamp position within viewport if near bottom edge
    - Animate open: `opacity 0→1` and `translateX(-10px)→translateX(0)` over `--duration-normal --ease-out`
    - Apply `z-index: 9999`; include red gradient left-accent stripe inside the flyout panel
    - _Requirements: 3.13, 3.15, 3.16, 3.17_

  - [x] 10.3 Create `src/app/layouts/Sidebar.tsx`
    - Define `SidebarProps` interface with JSDoc
    - Apply fixed positioning: `top: var(--topbar-height); left: 0; bottom: 0; width: var(--sidenav-width)`
    - Style: `background: #fff; border-right: 1px solid --color-neutral-200`
    - Do NOT apply `overflow: hidden` to the sidebar shell element
    - Add inner scroll wrapper: `overflow-y: auto; overflow-x: visible`
    - Style group labels: `font-size: 10px; font-weight: 700; uppercase; letter-spacing: 0.1em; --color-neutral-500`
    - Style nav links: `font-size: 13px; font-weight: 500; --color-neutral-600` default; hover `--color-primary-50` bg + `--color-primary`; active `--color-primary` bg + white text
    - Integrate `FlyoutSubmenu` for items with `children`; show flyout on mouse enter; apply 150ms hide delay on mouse leave
    - _Requirements: 3.2, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14_

  - [x] 10.4 Refactor `src/app/layouts/MainLayout.tsx` to compose Topbar, Sidebar, and main content area
    - Render `Topbar` as fixed element at top
    - Render `Sidebar` as fixed element below topbar
    - Render main content with `margin-left: var(--sidenav-width)` and `padding: calc(var(--topbar-height) + 24px) 24px 24px`
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 10.5 Write unit tests for MainLayout sub-components
    - Test Topbar renders at correct z-index and height
    - Test Sidebar renders with correct fixed position and no `overflow: hidden` on shell
    - Test FlyoutSubmenu renders with `z-index: 9999` and does not render when `anchorRect` has zero dimensions
    - Test MainLayout content area applies correct margin and padding
    - _Requirements: 3.1–3.17_

- [x] 11. Update PrimeReact theme overrides
  - [x] 11.1 Update `src/assets/styles/theme-overrides.css` to reference design tokens
    - Replace all hardcoded color, spacing, radius, and shadow values with corresponding CSS variable references from `tokens.css`
    - Add missing neutral scale tokens (`--color-neutral-600`, `--color-neutral-700`, `--color-neutral-800`, `--color-neutral-900`) and primary scale tokens (`--color-primary-active`, `--color-primary-200`) pending full migration to `tokens.css` as the single source
    - Update `.p-button` overrides to use `--radius-full` for pill shape
    - Update `.p-datatable` overrides to align with DataGrid requirements: sticky headers, `--color-primary-50` row hover, correct pagination button sizing
    - Retain existing `em-card`, `em-topbar`, and `em-sidebar` class definitions (updated to use tokens) for backward compatibility with existing pages
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

- [x] 12. Final checkpoint — Full integration and compliance verification
  - Verify `src/main.tsx` imports CSS files in the correct cascade order
  - Verify all components are exported from `src/shared/components/ui/index.ts`
  - Verify no component file uses hardcoded color, spacing, radius, shadow, or font values
  - Verify no component uses the `any` TypeScript type
  - Verify all component files use `.module.css` co-location convention
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests (Properties 1, 2, 3) validate universal correctness invariants using `fast-check` with a minimum of 100 runs each
- Unit tests validate specific examples, edge cases, and per-variant rendering
- The `sm` Button variant is a size modifier and may be composed with color variants via CSS class composition
- `CustomDropdown` panel must be rendered in a React portal to avoid ancestor `overflow: hidden` clipping
- Existing pages (`UserListPage`, `LoginPage`, `RolesPage`, `AuditLogsPage`) must remain visually correct throughout — migrate incrementally, not all at once
- All new TypeScript interfaces must use strict mode with no `any` types and include JSDoc comments

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "3.1", "3.2", "4.1", "5.1", "5.2"] },
    { "id": 3, "tasks": ["2.2", "2.3", "3.3", "4.2", "4.3", "6.1"] },
    { "id": 4, "tasks": ["3.4", "4.4", "5.3", "6.2", "6.3", "7.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "9.1", "9.2"] },
    { "id": 6, "tasks": ["10.1", "10.2", "11.1"] },
    { "id": 7, "tasks": ["10.3"] },
    { "id": 8, "tasks": ["10.4"] },
    { "id": 9, "tasks": ["10.5"] }
  ]
}
```
