/**
 * Emcure Design System — UI component barrel export.
 *
 * Import all shared UI components from this single entry point:
 * @example
 * import { Button, Card, CardHeader, CardBody, FormControl } from '@/shared/components/ui';
 */

// Button
export { default as Button } from './Button/Button';
export type { ButtonProps, ButtonVariant } from './Button/Button';

// FormControl, FormLabel, CustomDropdown
export { default as FormControl } from './FormControl/FormControl';
export type { FormControlProps } from './FormControl/FormControl';
export { FormLabel } from './FormControl/FormLabel';
export type { FormLabelProps } from './FormControl/FormLabel';
export { CustomDropdown } from './FormControl/CustomDropdown';
export type { CustomDropdownProps, DropdownOption } from './FormControl/CustomDropdown';

// Card, CardHeader, CardBody
export { Card, CardHeader, CardBody } from './Card/Card';
export type { CardProps, CardHeaderProps, CardBodyProps } from './Card/Card';

// PageHeader
export { PageHeader } from './PageHeader/PageHeader';
export type { PageHeaderProps } from './PageHeader/PageHeader';

// StatusBadge
export { default as StatusBadge } from './StatusBadge/StatusBadge';
export type { StatusBadgeProps, StatusBadgeVariant } from './StatusBadge/StatusBadge';

// Alert
export { default as Alert } from './Alert/Alert';
export type { AlertProps, AlertVariant } from './Alert/Alert';

// KpiCard, KpiGrid
export { default as KpiCard } from './KpiCard/KpiCard';
export type { KpiCardProps, KpiIconColor } from './KpiCard/KpiCard';
export { default as KpiGrid } from './KpiCard/KpiGrid';
export type { KpiGridProps } from './KpiCard/KpiGrid';

// SectionTitle
export { SectionTitle } from './SectionTitle/SectionTitle';
export type { SectionTitleProps } from './SectionTitle/SectionTitle';

// DataGrid
export { default as DataGrid } from './DataGrid/DataGrid';
export type { DataGridProps, DataGridColumn } from './DataGrid/DataGrid';
