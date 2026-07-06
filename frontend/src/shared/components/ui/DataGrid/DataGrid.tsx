import React, { useState } from 'react';
import styles from './DataGrid.module.css';

/**
 * Column definition for a DataGrid.
 *
 * @template T - The row data object type.
 */
export interface DataGridColumn<T = Record<string, unknown>> {
  /** Column header text. */
  header: string;
  /** Key of the row data object to render in this column. */
  field: keyof T;
  /** Optional custom cell renderer. Receives the cell value and full row. */
  render?: (value: T[keyof T], row: T) => React.ReactNode;
  /** Optional fixed column width (e.g. `'120px'`). */
  width?: string;
}

/**
 * Props for the DataGrid component.
 *
 * @template T - The row data object type.
 */
export interface DataGridProps<T = Record<string, unknown>> {
  /** Column definitions controlling headers and cell rendering. */
  columns: DataGridColumn<T>[];
  /** Array of row data objects. */
  data: T[];
  /** When `true`, renders skeleton placeholder rows instead of data rows. */
  loading?: boolean;
  /** Total record count used for the pagination footer label. */
  totalRecords?: number;
  /** Current page number (1-indexed). Defaults to `1`. */
  page?: number;
  /** Number of rows per page. Defaults to `10`. */
  pageSize?: number;
  /** Called when the user navigates to a different page. */
  onPageChange?: (page: number) => void;
  /** Called when the search input value changes. */
  onSearch?: (query: string) => void;
  /** Optional React node rendered in the toolbar's right-hand action slot. */
  toolbarActions?: React.ReactNode;
  /** Optional additional CSS class names applied to the root wrapper. */
  className?: string;
}

/** Number of skeleton rows to display when `loading` is `true`. */
const SKELETON_ROW_COUNT = 5;

/**
 * DataGrid
 *
 * A styled, generic table component with a search toolbar, sticky headers,
 * even-row striping, an optional loading skeleton, and a pagination footer.
 *
 * Row striping: every row at an even zero-based index receives the `rowEven`
 * CSS class, providing alternating background colours.
 *
 * @template T - Inferred from the `data` and `columns` props.
 *
 * @example
 * ```tsx
 * <DataGrid
 *   columns={[
 *     { header: 'Name', field: 'name' },
 *     { header: 'Role', field: 'role' },
 *   ]}
 *   data={users}
 *   totalRecords={users.length}
 * />
 * ```
 */
function DataGrid<T = Record<string, unknown>>({
  columns,
  data,
  loading = false,
  totalRecords,
  page: controlledPage,
  pageSize = 10,
  onPageChange,
  onSearch,
  toolbarActions,
  className,
}: DataGridProps<T>): React.ReactElement {
  const [internalPage, setInternalPage] = useState(1);
  const currentPage = controlledPage ?? internalPage;

  const totalPages =
    totalRecords !== undefined ? Math.max(1, Math.ceil(totalRecords / pageSize)) : 1;

  const handlePageChange = (newPage: number) => {
    setInternalPage(newPage);
    onPageChange?.(newPage);
  };

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    onSearch?.(e.target.value);
  };

  /** Render skeleton placeholder rows while data is loading. */
  const renderSkeletonRows = (): React.ReactNode => {
    return Array.from({ length: SKELETON_ROW_COUNT }).map((_, rowIdx) => (
      <tr key={`skeleton-${rowIdx}`} className={styles.skeletonRow} data-testid="datagrid-skeleton-row">
        {columns.map((col, colIdx) => (
          <td key={`skeleton-${rowIdx}-${colIdx}`}>
            <div className={styles.skeletonCell} />
          </td>
        ))}
      </tr>
    ));
  };

  /** Render actual data rows with even-row striping. */
  const renderDataRows = (): React.ReactNode => {
    if (data.length === 0) {
      return (
        <tr>
          <td colSpan={columns.length} className={styles.empty}>
            No records found.
          </td>
        </tr>
      );
    }

    return data.map((row, rowIdx) => {
      const isEven = rowIdx % 2 === 0;
      const rowClasses = [styles.tr, isEven ? styles.rowEven : '']
        .filter(Boolean)
        .join(' ');

      return (
        <tr key={rowIdx} className={rowClasses} data-testid="datagrid-row">
          {columns.map((col, colIdx) => {
            const cellValue = row[col.field];
            return (
              <td
                key={colIdx}
                className={styles.td}
                style={col.width ? { width: col.width } : undefined}
              >
                {col.render ? col.render(cellValue, row) : String(cellValue ?? '')}
              </td>
            );
          })}
        </tr>
      );
    });
  };

  /** Build an array of page numbers to display in the pagination control. */
  const buildPageNumbers = (): number[] => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const pages: number[] = [1];
    const start = Math.max(2, currentPage - 2);
    const end = Math.min(totalPages - 1, currentPage + 2);
    for (let p = start; p <= end; p++) pages.push(p);
    pages.push(totalPages);
    return [...new Set(pages)];
  };

  return (
    <div
      className={[styles.datagridWrap, className].filter(Boolean).join(' ')}
      data-testid="datagrid"
    >
      {/* ── Toolbar ── */}
      <div className={styles.toolbar} data-testid="datagrid-toolbar">
        <div className={styles.searchWrapper}>
          <span
            className={[styles.searchIcon, 'pi pi-search'].join(' ')}
            aria-hidden="true"
          />
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Search…"
            onChange={handleSearch}
            aria-label="Search records"
            data-testid="datagrid-search"
          />
        </div>
        {toolbarActions && (
          <div
            className={styles.toolbarActions}
            data-testid="datagrid-toolbar-actions"
          >
            {toolbarActions}
          </div>
        )}
      </div>

      {/* ── Table ── */}
      <div className={styles.tableWrapper}>
        <table className={styles.table} role="table">
          <thead className={styles.thead} data-testid="datagrid-thead">
            <tr>
              {columns.map((col, idx) => (
                <th
                  key={idx}
                  className={styles.th}
                  style={col.width ? { width: col.width } : undefined}
                  scope="col"
                  data-testid={`datagrid-th-${String(col.field)}`}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody data-testid="datagrid-tbody">
            {loading ? renderSkeletonRows() : renderDataRows()}
          </tbody>
        </table>
      </div>

      {/* ── Footer / Pagination ── */}
      {totalRecords !== undefined && (
        <div className={styles.footer} data-testid="datagrid-footer">
          <span className={styles.recordCount} data-testid="datagrid-record-count">
            {totalRecords} record{totalRecords !== 1 ? 's' : ''}
          </span>
          {totalPages > 1 && (
            <div
              className={styles.pagination}
              role="navigation"
              aria-label="Pagination"
              data-testid="datagrid-pagination"
            >
              <button
                className={styles.pageBtn}
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage <= 1}
                aria-label="Previous page"
                data-testid="datagrid-page-prev"
              >
                <span className="pi pi-chevron-left" aria-hidden="true" />
              </button>

              {buildPageNumbers().map((pageNum) => (
                <button
                  key={pageNum}
                  className={[
                    styles.pageBtn,
                    pageNum === currentPage ? styles.pageBtnActive : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => handlePageChange(pageNum)}
                  aria-label={`Page ${pageNum}`}
                  aria-current={pageNum === currentPage ? 'page' : undefined}
                  data-testid={`datagrid-page-btn-${pageNum}`}
                >
                  {pageNum}
                </button>
              ))}

              <button
                className={styles.pageBtn}
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage >= totalPages}
                aria-label="Next page"
                data-testid="datagrid-page-next"
              >
                <span className="pi pi-chevron-right" aria-hidden="true" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default DataGrid;
