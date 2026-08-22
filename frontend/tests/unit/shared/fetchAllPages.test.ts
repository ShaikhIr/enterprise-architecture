import { describe, expect, it, vi } from 'vitest';

import { fetchAllPages, type Page } from '@shared/utils/fetchAllPages';

describe('fetchAllPages', () => {
  it('returns everything from a single page when total fits in one request', async () => {
    const fetchPage = vi.fn(
      async (): Promise<Page<{ id: number }>> => ({
        items: [{ id: 1 }, { id: 2 }],
        total: 2,
      }),
    );

    const rows = await fetchAllPages(fetchPage, 500);

    expect(rows).toEqual([{ id: 1 }, { id: 2 }]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(fetchPage).toHaveBeenCalledWith(0, 500);
  });

  it('walks every page in order until it has collected the full total', async () => {
    const fetchPage = vi.fn(async (skip: number): Promise<Page<{ id: number }>> => {
      if (skip === 0) return { items: [{ id: 1 }, { id: 2 }], total: 5 };
      if (skip === 2) return { items: [{ id: 3 }, { id: 4 }], total: 5 };
      return { items: [{ id: 5 }], total: 5 };
    });

    const rows = await fetchAllPages(fetchPage, 2);

    expect(rows.map((r) => r.id)).toEqual([1, 2, 3, 4, 5]);
    expect(fetchPage).toHaveBeenCalledTimes(3);
    expect(fetchPage).toHaveBeenNthCalledWith(1, 0, 2);
    expect(fetchPage).toHaveBeenNthCalledWith(2, 2, 2);
    expect(fetchPage).toHaveBeenNthCalledWith(3, 4, 2);
  });

  it('stops early when a page comes back empty, even if total says more remain', async () => {
    const fetchPage = vi.fn(async (skip: number): Promise<Page<{ id: number }>> => {
      if (skip === 0) return { items: [{ id: 1 }], total: 100 };
      return { items: [], total: 100 };
    });

    const rows = await fetchAllPages(fetchPage, 1);

    expect(rows).toEqual([{ id: 1 }]);
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });

  it('never asks for more pages than maxPages, regardless of total', async () => {
    const fetchPage = vi.fn(
      async (): Promise<Page<{ id: number }>> => ({
        items: [{ id: 1 }],
        total: 1_000_000,
      }),
    );

    await fetchAllPages(fetchPage, 1, 3);

    expect(fetchPage).toHaveBeenCalledTimes(3);
  });

  it('returns an empty array when the first page is already empty', async () => {
    const fetchPage = vi.fn(async (): Promise<Page<{ id: number }>> => ({ items: [], total: 0 }));

    const rows = await fetchAllPages(fetchPage, 500);

    expect(rows).toEqual([]);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });
});
