/**
 * Active/Inactive tag for master records.
 *
 * Masters are retired via `is_active` rather than deleted, so this column is the
 * usual way a row is taken out of use. Severity follows the standard's mapping:
 * active is success, inactive is a warning rather than an error — a deactivated
 * country is intentional, not a fault.
 */

import { Tag } from 'primereact/tag';

interface MasterStatusTagProps {
  isActive: boolean;
}

export const MasterStatusTag = ({ isActive }: MasterStatusTagProps) => (
  <Tag value={isActive ? 'Active' : 'Inactive'} severity={isActive ? 'success' : 'warning'} />
);
