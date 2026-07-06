/**
 * Unit tests for the DataGrid component — Emcure Design System
 *
 * Requirements covered: 11.1–11.8
 *
 * CSS module class names: Vitest is configured with css.modules.classNameStrategy
 * set to 'non-scoped', which causes CSS Modules to return non-hashed, human-readable
 * class names in the test environment. This allows us to assert on class names by
 * their source keys (e.g. 'th', 'rowEven', 'pageBtnActive', 'toolbar').
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/react';
import React from 'react';
import DataGrid, { type DataGridColumn } from '../../src/shared/components/ui/DataGrid/DataGrid';

// ---------------------------------------------------------------------------
// Shared test fixtures
// ---------------------------------------------------------------------------

interface TestRow {
  id: number;
  name: string;
  email: string;
}

const columns: DataGridColumn<TestRow>[] = [
  { header: 'ID', field: 'id' },
  { header: 'Name', field: 'name' },
  { header: 'Email', field: 'email' },
];

const sampleData: TestRow[] = [
  { id: 1, name: 'Alice', email: 'alice@example.com' },
  { id: 2, name: 'Bob', email: 'bob@example.com' },
  { id: 3, name: 'Carol', email: 'carol@example.com' },
];

// ---------------------------------------------------------------------------
// 1. Toolbar — search input and toolbarActions slot
// ---------------------------------------------------------------------------

describe('DataGrid — toolbar (Requirement 11.2)', () => {
  it('renders the toolbar element', () => {
    render(<DataGrid columns={columns} data={sampleData} />);
    expect(screen.getByTestId('datagrid-toolbar')).toBeTruthy();
  });

  it('renders a search input inside the toolbar', () => {
    render(<DataGrid columns={columns} data={sampleData} />);
    const searchInput = screen.getByTestId('datagrid-search');
    expect(searchInput).toBeTruthy();
    expect(searchInput.tagName.toLowerCase()).toBe('input');
  });

  it('search input is accessible via its aria-label', () => {
    render(<DataGrid columns={columns} data={sampleData} />);
    expect(screen.getByRole('textbox', { name: /search/i })).toBeTruthy();
  });

  it('toolbar has "toolbar" CSS module class', () => {
    const { container } = render(<DataGrid columns={columns} data={sampleData} />);
    const toolbar = container.querySelector('[data-testid="datagrid-toolbar"]');
    expect(toolbar).toBeTruthy();
    expect(toolbar!.className).toContain('toolbar');
  });

  it('does NOT render the toolbarActions slot when prop is not provided', () => {
    render(<DataGrid columns={columns} data={sampleData} />);
    expect(screen.queryByTestId('datagrid-toolbar-actions')).toBeNull();
  });

  it('renders the toolbarActions slot when prop is provided', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        toolbarActions={<button data-testid="export-btn">Export</button>}
      />
    );
    expect(screen.getByTestId('datagrid-toolbar-actions')).toBeTruthy();
    expect(screen.getByTestId('export-btn')).toBeTruthy();
  });

  it('renders multiple nodes inside the toolbarActions slot', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        toolbarActions={
          <>
            <button data-testid="filter-btn">Filter</button>
            <button data-testid="export-btn">Export</button>
          </>
        }
      />
    );
    expect(screen.getByTestId('filter-btn')).toBeTruthy();
    expect(screen.getByTestId('export-btn')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// 2. Column headers — sticky / style classes (Requirement 11.4)
// ---------------------------------------------------------------------------

describe('DataGrid — column headers (Requirement 11.4)', () => {
  it('renders one <th> per column definition', () => {
    const { container } = render(<DataGrid columns={columns} data={sampleData} />);
    const ths = container.querySelectorAll('thead th');
    expect(ths.length).toBe(columns.length);
  });

  it('renders the header text for each column', () => {
    render(<DataGrid columns={columns} data={sampleData} />);
    expect(screen.getByText('ID')).toBeTruthy();
    expect(screen.getByText('Name')).toBeTruthy();
    expect(screen.getByText('Email')).toBeTruthy();
  });

  it('applies the "th" CSS module class to each header cell', () => {
    const { container } = render(<DataGrid columns={columns} data={sampleData} />);
    const ths = container.querySelectorAll('thead th');
    ths.forEach((th) => {
      expect(th.className).toContain('th');
    });
  });

  it('applies the "thead" CSS module class to the <thead> element (sticky headers)', () => {
    const { container } = render(<DataGrid columns={columns} data={sampleData} />);
    const thead = container.querySelector('thead');
    expect(thead).toBeTruthy();
    expect(thead!.className).toContain('thead');
  });

  it('applies column width style when "width" is specified', () => {
    const colsWithWidth: DataGridColumn<TestRow>[] = [
      { header: 'ID', field: 'id', width: '80px' },
      { header: 'Name', field: 'name' },
    ];
    const { container } = render(<DataGrid columns={colsWithWidth} data={sampleData} />);
    const ths = container.querySelectorAll('thead th');
    expect((ths[0] as HTMLElement).style.width).toBe('80px');
    expect((ths[1] as HTMLElement).style.width).toBe('');
  });

  it('renders each header with a data-testid matching its field', () => {
    render(<DataGrid columns={columns} data={sampleData} />);
    expect(screen.getByTestId('datagrid-th-id')).toBeTruthy();
    expect(screen.getByTestId('datagrid-th-name')).toBeTruthy();
    expect(screen.getByTestId('datagrid-th-email')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// 3. Table body — row data and even-row striping (Requirement 11.5)
// ---------------------------------------------------------------------------

describe('DataGrid — table body (Requirement 11.5)', () => {
  it('renders one <tr> per data row', () => {
    const { container } = render(<DataGrid columns={columns} data={sampleData} />);
    const rows = container.querySelectorAll('tbody tr[data-testid="datagrid-row"]');
    expect(rows.length).toBe(sampleData.length);
  });

  it('renders cell values from the row data', () => {
    render(<DataGrid columns={columns} data={sampleData} />);
    expect(screen.getByText('Alice')).toBeTruthy();
    expect(screen.getByText('bob@example.com')).toBeTruthy();
  });

  it('applies custom render function when provided', () => {
    const colsWithRender: DataGridColumn<TestRow>[] = [
      { header: 'ID', field: 'id' },
      {
        header: 'Name',
        field: 'name',
        render: (value) => <strong data-testid="custom-cell">{String(value)}</strong>,
      },
    ];
    render(<DataGrid columns={colsWithRender} data={[sampleData[0]]} />);
    expect(screen.getByTestId('custom-cell')).toBeTruthy();
  });

  it('applies "rowEven" class to even-indexed rows (0-based)', () => {
    const { container } = render(<DataGrid columns={columns} data={sampleData} />);
    const rows = container.querySelectorAll('tbody tr[data-testid="datagrid-row"]');
    // Row 0 (even index) → rowEven
    expect(rows[0].className).toContain('rowEven');
    // Row 1 (odd index) → no rowEven
    expect(rows[1].className).not.toContain('rowEven');
    // Row 2 (even index) → rowEven
    expect(rows[2].className).toContain('rowEven');
  });

  it('does NOT render data rows when data is empty', () => {
    const { container } = render(<DataGrid columns={columns} data={[]} />);
    const rows = container.querySelectorAll('tbody tr[data-testid="datagrid-row"]');
    expect(rows.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// 4. Loading state — skeleton rows (Requirement 11.1)
// ---------------------------------------------------------------------------

describe('DataGrid — loading state', () => {
  it('renders 5 skeleton rows when loading=true', () => {
    render(<DataGrid columns={columns} data={[]} loading={true} />);
    const skeletonRows = screen.getAllByTestId('datagrid-skeleton-row');
    expect(skeletonRows.length).toBe(5);
  });

  it('does NOT render skeleton rows when loading=false', () => {
    render(<DataGrid columns={columns} data={sampleData} loading={false} />);
    expect(screen.queryByTestId('datagrid-skeleton-row')).toBeNull();
  });

  it('does NOT render data rows when loading=true', () => {
    render(<DataGrid columns={columns} data={sampleData} loading={true} />);
    expect(screen.queryByTestId('datagrid-row')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 5. Footer — only renders when totalRecords is provided (Requirements 11.6, 11.7)
// ---------------------------------------------------------------------------

describe('DataGrid — footer (Requirements 11.6, 11.7)', () => {
  it('does NOT render the footer when totalRecords is not provided', () => {
    render(<DataGrid columns={columns} data={sampleData} />);
    expect(screen.queryByTestId('datagrid-footer')).toBeNull();
  });

  it('renders the footer when totalRecords is provided', () => {
    render(<DataGrid columns={columns} data={sampleData} totalRecords={30} />);
    expect(screen.getByTestId('datagrid-footer')).toBeTruthy();
  });

  it('displays the total record count in the footer', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={1}
        pageSize={10}
      />
    );
    const count = screen.getByTestId('datagrid-record-count');
    expect(count.textContent).toContain('30');
  });

  it('renders "1 record" (singular) when totalRecords is 1', () => {
    render(
      <DataGrid
        columns={columns}
        data={[sampleData[0]]}
        totalRecords={1}
        page={1}
        pageSize={10}
      />
    );
    expect(screen.getByTestId('datagrid-record-count').textContent).toContain('1 record');
  });

  it('renders "N records" (plural) when totalRecords is more than 1', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={1}
        pageSize={10}
      />
    );
    expect(screen.getByTestId('datagrid-record-count').textContent).toContain('30 records');
  });

  it('renders pagination controls when there are multiple pages', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={1}
        pageSize={10}
      />
    );
    expect(screen.getByTestId('datagrid-pagination')).toBeTruthy();
  });

  it('does NOT render pagination when all records fit on one page', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={3}
        page={1}
        pageSize={10}
      />
    );
    // Footer should exist but no pagination nav
    expect(screen.getByTestId('datagrid-footer')).toBeTruthy();
    expect(screen.queryByTestId('datagrid-pagination')).toBeNull();
  });

  it('renders Previous and Next navigation buttons', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={2}
        pageSize={10}
      />
    );
    expect(screen.getByLabelText('Previous page')).toBeTruthy();
    expect(screen.getByLabelText('Next page')).toBeTruthy();
  });

  it('disables the Previous button on the first page', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={1}
        pageSize={10}
      />
    );
    expect(screen.getByLabelText('Previous page')).toBeDisabled();
  });

  it('disables the Next button on the last page', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={3}
        pageSize={10}
      />
    );
    expect(screen.getByLabelText('Next page')).toBeDisabled();
  });

  it('applies "pageBtnActive" class to the current page button', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={2}
        pageSize={10}
      />
    );
    const activeBtn = screen.getByTestId('datagrid-page-btn-2');
    expect(activeBtn.className).toContain('pageBtnActive');
  });

  it('does NOT apply "pageBtnActive" class to non-current page buttons', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={2}
        pageSize={10}
      />
    );
    const btn1 = screen.getByTestId('datagrid-page-btn-1');
    expect(btn1.className).not.toContain('pageBtnActive');
  });

  it('pagination buttons are 28×28px via "pageBtn" CSS class', () => {
    const { container } = render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={1}
        pageSize={10}
      />
    );
    const pageBtns = container.querySelectorAll('[data-testid^="datagrid-page-btn"]');
    pageBtns.forEach((btn) => {
      expect(btn.className).toContain('pageBtn');
    });
  });
});

// ---------------------------------------------------------------------------
// 6. onSearch handler (Requirement 11.8)
// ---------------------------------------------------------------------------

describe('DataGrid — onSearch callback (Requirement 11.8)', () => {
  it('calls onSearch when the search input value changes', () => {
    const onSearch = vi.fn();
    render(<DataGrid columns={columns} data={sampleData} onSearch={onSearch} />);

    const searchInput = screen.getByTestId('datagrid-search');
    fireEvent.change(searchInput, { target: { value: 'Alice' } });

    expect(onSearch).toHaveBeenCalledTimes(1);
    expect(onSearch).toHaveBeenCalledWith('Alice');
  });

  it('calls onSearch on each keystroke with the current value', () => {
    const onSearch = vi.fn();
    render(<DataGrid columns={columns} data={sampleData} onSearch={onSearch} />);

    const searchInput = screen.getByTestId('datagrid-search');
    fireEvent.change(searchInput, { target: { value: 'A' } });
    fireEvent.change(searchInput, { target: { value: 'Al' } });
    fireEvent.change(searchInput, { target: { value: 'Ali' } });

    expect(onSearch).toHaveBeenCalledTimes(3);
    expect(onSearch).toHaveBeenNthCalledWith(1, 'A');
    expect(onSearch).toHaveBeenNthCalledWith(2, 'Al');
    expect(onSearch).toHaveBeenNthCalledWith(3, 'Ali');
  });

  it('does not throw when onSearch is not provided and input changes', () => {
    render(<DataGrid columns={columns} data={sampleData} />);
    const searchInput = screen.getByTestId('datagrid-search');
    expect(() => {
      fireEvent.change(searchInput, { target: { value: 'test' } });
    }).not.toThrow();
  });

  it('calls onSearch with empty string when input is cleared', () => {
    const onSearch = vi.fn();
    render(<DataGrid columns={columns} data={sampleData} onSearch={onSearch} />);

    const searchInput = screen.getByTestId('datagrid-search');
    fireEvent.change(searchInput, { target: { value: 'Alice' } });
    fireEvent.change(searchInput, { target: { value: '' } });

    expect(onSearch).toHaveBeenLastCalledWith('');
  });
});

// ---------------------------------------------------------------------------
// 7. onPageChange handler (Requirement 11.8)
// ---------------------------------------------------------------------------

describe('DataGrid — onPageChange callback (Requirement 11.8)', () => {
  it('calls onPageChange with the correct page number when a numbered page button is clicked', () => {
    const onPageChange = vi.fn();
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={1}
        pageSize={10}
        onPageChange={onPageChange}
      />
    );

    fireEvent.click(screen.getByTestId('datagrid-page-btn-2'));
    expect(onPageChange).toHaveBeenCalledTimes(1);
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it('calls onPageChange with page-1 when the Previous button is clicked', () => {
    const onPageChange = vi.fn();
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={2}
        pageSize={10}
        onPageChange={onPageChange}
      />
    );

    fireEvent.click(screen.getByLabelText('Previous page'));
    expect(onPageChange).toHaveBeenCalledWith(1);
  });

  it('calls onPageChange with page+1 when the Next button is clicked', () => {
    const onPageChange = vi.fn();
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={2}
        pageSize={10}
        onPageChange={onPageChange}
      />
    );

    fireEvent.click(screen.getByLabelText('Next page'));
    expect(onPageChange).toHaveBeenCalledWith(3);
  });

  it('does not throw when onPageChange is not provided and a page button is clicked', () => {
    render(
      <DataGrid
        columns={columns}
        data={sampleData}
        totalRecords={30}
        page={1}
        pageSize={10}
      />
    );
    expect(() => {
      fireEvent.click(screen.getByTestId('datagrid-page-btn-2'));
    }).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// 8. DataGrid wrapper element structure (Requirement 11.1)
// ---------------------------------------------------------------------------

describe('DataGrid — outer wrapper (Requirement 11.1)', () => {
  it('renders the outermost wrapper with data-testid "datagrid"', () => {
    render(<DataGrid columns={columns} data={sampleData} />);
    expect(screen.getByTestId('datagrid')).toBeTruthy();
  });

  it('applies "datagridWrap" CSS module class to the outer wrapper', () => {
    const { container } = render(<DataGrid columns={columns} data={sampleData} />);
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.className).toContain('datagridWrap');
  });

  it('merges a custom className onto the outer wrapper', () => {
    const { container } = render(
      <DataGrid columns={columns} data={sampleData} className="custom-grid" />
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.className).toContain('custom-grid');
    expect(wrapper.className).toContain('datagridWrap');
  });
});
