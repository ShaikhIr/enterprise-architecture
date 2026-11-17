/**
 * Page shell for a master data screen.
 *
 * Holds the chrome the frontend UI standard prescribes — `p-3` page padding,
 * `text-xl` heading, a `surface-card p-3 border-round shadow-1` content card, a
 * Toolbar with New/Refresh, and a striped paginated DataTable — so the six master
 * screens cannot drift apart visually.
 *
 * Columns and dialogs are passed in rather than configured, because a column set
 * is the one thing genuinely specific to each master and driving it from a config
 * object would hide each screen's shape from its own file.
 */

import { Children, Fragment, isValidElement, type ReactNode } from 'react';

import { Button } from 'primereact/button';
import { ConfirmDialog } from 'primereact/confirmdialog';
import { DataTable, type DataTableFilterMeta } from 'primereact/datatable';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';

import type { AuditedRecord } from '../models/common';

/**
 * Flatten fragments out of the column list.
 *
 * DataTable discovers its columns with `React.Children.toArray(children)`, and
 * `toArray` does not unwrap fragments — it yields the fragment itself as one
 * child. Passing `<>...</>` therefore produced a table with rows but no headers
 * and no cells, because DataTable saw a single child that was not a Column.
 *
 * Flattening here keeps the natural `columns={<>...</>}` call style, including
 * `{condition && <Column />}` entries, which `toArray` drops when false.
 */
const flattenColumns = (node: ReactNode): ReactNode[] =>
  Children.toArray(node).flatMap((child) =>
    isValidElement(child) && child.type === Fragment
      ? flattenColumns((child.props as { children?: ReactNode }).children)
      : [child],
  );

export interface MasterCrudPageProps<TEntity extends AuditedRecord> {
  title: string;
  subtitle: string;
  /** Label for the create button, e.g. "New Country". */
  newLabel: string;
  rows: TEntity[];
  loading: boolean;
  refreshing?: boolean;
  onRefresh: () => void;
  onNew: () => void;
  /**
   * Whether the caller holds CREATE on this resource. The New button is omitted
   * entirely when false, rather than shown and rejected with a 403.
   */
  canCreate: boolean;
  /** PrimeReact `<Column>` elements. */
  columns: ReactNode;
  filters?: DataTableFilterMeta;
  onFilterChange?: (filters: DataTableFilterMeta) => void;
  /** Extra controls rendered on the right of the toolbar, e.g. parent filters. */
  toolbarEnd?: ReactNode;
  emptyMessage: string;
  /** The master's form dialog. */
  children?: ReactNode;
  toastRef: React.RefObject<Toast | null>;
}

export const MasterCrudPage = <TEntity extends AuditedRecord>({
  title,
  subtitle,
  newLabel,
  rows,
  loading,
  refreshing,
  onRefresh,
  onNew,
  canCreate,
  columns,
  filters,
  onFilterChange,
  toolbarEnd,
  emptyMessage,
  children,
  toastRef,
}: MasterCrudPageProps<TEntity>) => (
  <div className="p-3">
    <Toast ref={toastRef} />
    <ConfirmDialog />

    <div className="mb-3">
      <h2 className="text-xl font-semibold text-900 m-0">{title}</h2>
      <p className="text-600 mt-1 mb-0">{subtitle}</p>
    </div>

    <div className="surface-card p-3 border-round shadow-1">
      <Toolbar
        className="mb-3"
        start={() => (
          <div className="flex gap-2">
            {canCreate && (
              <Button label={newLabel} icon="pi pi-plus" onClick={onNew} aria-label={newLabel} />
            )}
            <Button
              label="Refresh"
              icon="pi pi-refresh"
              severity="secondary"
              outlined
              loading={refreshing}
              onClick={onRefresh}
              aria-label={`Refresh ${title.toLowerCase()}`}
            />
          </div>
        )}
        end={toolbarEnd ? () => <div className="flex gap-2">{toolbarEnd}</div> : undefined}
      />

      <DataTable
        value={rows}
        loading={loading}
        paginator
        rows={10}
        rowsPerPageOptions={[10, 25, 50, 100]}
        stripedRows
        showGridlines
        emptyMessage={emptyMessage}
        filters={filters}
        filterDisplay={filters ? 'row' : undefined}
        onFilter={(e) => onFilterChange?.(e.filters)}
        tableStyle={{ minWidth: '0' }}
        aria-label={`${title} table`}
      >
        {flattenColumns(columns)}
      </DataTable>
    </div>

    {children}
  </div>
);
