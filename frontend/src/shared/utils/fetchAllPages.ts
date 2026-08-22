/**
 * Reads every page of a paginated endpoint.
 *
 * Reference data is loaded whole so that cascading pickers can filter locally, but
 * the API caps a page at 500 rows and some of these tables are past that — entity
 * mappings and the user directory both are. Asking for one big page silently returns
 * the first 500, which does not fail, it just omits: a dropdown quietly missing a
 * quarter of its options is worse than an error.
 *
 * `total` from the first response decides how many more pages to ask for, and pages
 * are fetched in order rather than in parallel: this runs once per cache entry, and
 * spraying a dozen concurrent reads to save a few hundred milliseconds is not a
 * trade worth making.
 *
 * `maxPages` is a stop for a server that keeps reporting a total it never satisfies,
 * so a bad response cannot turn into an unbounded loop.
 */

export interface Page<T> {
  items: T[];
  total: number;
}

export const fetchAllPages = async <T>(
  fetchPage: (skip: number, limit: number) => Promise<Page<T>>,
  pageSize = 500,
  maxPages = 20,
): Promise<T[]> => {
  const first = await fetchPage(0, pageSize);
  const rows = [...first.items];

  const pages = Math.min(Math.ceil(first.total / pageSize), maxPages);
  for (let page = 1; page < pages; page += 1) {
    const next = await fetchPage(page * pageSize, pageSize);
    // An empty page means the total was optimistic; stop rather than spin.
    if (next.items.length === 0) break;
    rows.push(...next.items);
  }

  return rows;
};
