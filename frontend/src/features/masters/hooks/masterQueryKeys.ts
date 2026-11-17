/**
 * TanStack Query keys for master data.
 *
 * Collected in one module so that a master can declare which sibling caches its
 * edits invalidate without importing that sibling's hooks — which would create
 * import cycles between, say, countries and states.
 */

import type { QueryKey } from '@tanstack/react-query';

export const MASTER_KEYS = {
  countries: ['masters', 'countries'] as QueryKey,
  states: ['masters', 'states'] as QueryKey,
  categoriesOfLaw: ['masters', 'categories-of-law'] as QueryKey,
  legislations: ['masters', 'legislations'] as QueryKey,
  rules: ['masters', 'rules'] as QueryKey,
  taskTypes: ['masters', 'task-types'] as QueryKey,
} as const;
