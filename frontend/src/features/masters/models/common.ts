/**
 * Shapes shared by every compliance master.
 *
 * The six masters form one hierarchy:
 *
 *     Country ─┬─ State ─── CategoryOfLaw
 *              └─ Legislation ─── Rule
 *
 *     TaskType (independent lookup)
 *
 * A nullable `state_id` on a child means country-wide (central), not "not set".
 */

/** Identity and audit columns every master carries, via the backend AuditMixin. */
export interface AuditedRecord {
  id: string;
  created_by: string;
  created_date: string;
  modified_by: string;
  modified_date: string;
}

/**
 * An audited master that is retired through `is_active`.
 *
 * Separate from AuditedRecord so a future master that retires through a
 * differently-named flag can still use the shared page shell and CRUD
 * controller by constraining to AuditedRecord directly, rather than being
 * forced to shoehorn its flag into `is_active`.
 */
export interface MasterRecord extends AuditedRecord {
  is_active: boolean;
}

/** One page of a master list, normalised away from each endpoint's envelope key. */
export interface MasterPage<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

/** Filters every master list endpoint accepts. */
export interface MasterListParams {
  skip?: number;
  limit?: number;
  search?: string;
  is_active?: boolean;
}

/** A master that can be offered in a parent picker. */
export type LabelledMaster = MasterRecord & { code: string; name: string };
