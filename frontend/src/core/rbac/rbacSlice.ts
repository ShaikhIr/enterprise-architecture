/**
 * RBAC Redux slice.
 * Manages the user's permissions state fetched from the backend.
 * Loaded after authentication and used throughout the app.
 */

import type { PayloadAction } from '@reduxjs/toolkit';
import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';

import { sessionCache } from '@shared/services/sessionCache';
import { extractApiError } from '@shared/utils/apiError';

import { rbacApi } from './rbacApi';
import type {
  ApiPermissionsResponse,
  FieldPermissionsResponse,
  MenuPermissionsResponse,
  Permission,
  PermissionAction,
} from './types';

interface RbacState {
  /** Menu keys the user can access */
  menuKeys: string[];
  /** All menu permissions for detailed checks */
  menuPermissions: Permission[];
  /** API-scope permission codes, e.g. "countries.create" */
  apiCodes: string[];
  /** API-scope grants as resource → allowed actions, e.g. countries → [READ, CREATE] */
  apiResourceActions: Record<string, PermissionAction[]>;
  /** Field-level permissions by resource */
  fieldPermissions: Record<string, Record<string, PermissionAction[]>>;
  /**
   * How the field-grant fetch for each resource is going.
   *
   * Absence of a resource from `fieldPermissions` used to be the only signal, and it
   * could not tell "still asking" from "asked and failed". A screen that gates on the
   * grant read the second as the first and waited for a fetch that was never coming.
   */
  fieldPermissionStatus: Record<string, 'loading' | 'loaded' | 'error'>;
  /** Whether menu RBAC data has been loaded */
  isLoaded: boolean;
  /**
   * Whether API RBAC data has been loaded. Tracked separately from `isLoaded`
   * because navigation guards depend only on menu permissions and must not be
   * held up waiting for the API set.
   */
  isApiLoaded: boolean;
  isLoading: boolean;
  /** In-flight guard for the API-permission fetch; see the thunk's `condition`. */
  isApiLoading: boolean;
  error: string | null;
}

// Hydrate from the cached snapshot so navigation guards resolve immediately on a
// remount instead of blanking while menu permissions are refetched.
const cachedMenuKeys = sessionCache.getMenuKeys();
const cachedPermissions = sessionCache.getPermissions();
const cachedApiCodes = sessionCache.getApiCodes();
const cachedApiResourceActions = sessionCache.getApiResourceActions();

const initialState: RbacState = {
  menuKeys: cachedMenuKeys,
  menuPermissions: cachedPermissions,
  apiCodes: cachedApiCodes,
  apiResourceActions: cachedApiResourceActions,
  fieldPermissions: {},
  fieldPermissionStatus: {},
  isLoaded: cachedMenuKeys.length > 0,
  isApiLoaded: cachedApiCodes.length > 0,
  isLoading: false,
  isApiLoading: false,
  error: null,
};

/**
 * Fetch menu permissions after login.
 */
export const fetchMenuPermissions = createAsyncThunk(
  'rbac/fetchMenuPermissions',
  async (_, { rejectWithValue }) => {
    try {
      return await rbacApi.getMenuPermissions();
    } catch (error) {
      return rejectWithValue(extractApiError(error, 'Failed to load permissions'));
    }
  },
);

/**
 * Fetch API-scope permissions after login.
 *
 * Separate from the menu fetch so that a slow or failed API-permission load
 * cannot block navigation, which only needs menu keys.
 */
export const fetchApiPermissions = createAsyncThunk(
  'rbac/fetchApiPermissions',
  async (_, { rejectWithValue }) => {
    try {
      return await rbacApi.getApiPermissions();
    } catch (error) {
      return rejectWithValue(extractApiError(error, 'Failed to load API permissions'));
    }
  },
  {
    /**
     * Every gate self-loads, so a screen with several permission checks would
     * otherwise fire one identical request per check. This collapses them to one.
     */
    condition: (_arg, { getState }) => {
      const { rbac } = getState() as { rbac: RbacState };
      return !rbac.isApiLoaded && !rbac.isApiLoading;
    },
  },
);

/**
 * Fetch field-level permissions for a specific resource (lazy-loaded).
 */
export const fetchFieldPermissions = createAsyncThunk(
  'rbac/fetchFieldPermissions',
  async (resource: string, { rejectWithValue }) => {
    try {
      return await rbacApi.getFieldPermissions(resource);
    } catch (error) {
      return rejectWithValue(extractApiError(error, 'Failed to load field permissions'));
    }
  },
);

const rbacSlice = createSlice({
  name: 'rbac',
  initialState,
  reducers: {
    clearRbac: () => {
      sessionCache.clear();
      return {
        ...initialState,
        menuKeys: [],
        menuPermissions: [],
        apiCodes: [],
        apiResourceActions: {},
        isLoaded: false,
        isApiLoaded: false,
        isApiLoading: false,
      };
    },
  },
  extraReducers: (builder) => {
    builder
      // Menu permissions
      .addCase(fetchMenuPermissions.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(
        fetchMenuPermissions.fulfilled,
        (state, action: PayloadAction<MenuPermissionsResponse>) => {
          state.isLoading = false;
          state.isLoaded = true;
          state.menuKeys = action.payload.menu_keys;
          state.menuPermissions = action.payload.permissions;
          sessionCache.setRbac(action.payload.menu_keys, action.payload.permissions);
        },
      )
      .addCase(fetchMenuPermissions.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      })
      // API permissions
      .addCase(fetchApiPermissions.pending, (state) => {
        state.isApiLoading = true;
      })
      .addCase(
        fetchApiPermissions.fulfilled,
        (state, action: PayloadAction<ApiPermissionsResponse>) => {
          state.isApiLoading = false;
          state.isApiLoaded = true;
          state.apiCodes = action.payload.codes;
          state.apiResourceActions = action.payload.resource_actions;
          sessionCache.setApiRbac(action.payload.codes, action.payload.resource_actions);
        },
      )
      .addCase(fetchApiPermissions.rejected, (state, action) => {
        // Leaves `isApiLoaded` false, so gates stay closed rather than guessing.
        state.isApiLoading = false;
        state.error = action.payload as string;
      })
      // Field permissions
      .addCase(fetchFieldPermissions.pending, (state, action) => {
        state.fieldPermissionStatus[action.meta.arg] = 'loading';
      })
      .addCase(
        fetchFieldPermissions.fulfilled,
        (state, action: PayloadAction<FieldPermissionsResponse>) => {
          state.fieldPermissions[action.payload.resource] = action.payload.fields;
          state.fieldPermissionStatus[action.payload.resource] = 'loaded';
        },
      )
      .addCase(fetchFieldPermissions.rejected, (state, action) => {
        // No grants recorded, so every field check stays closed — but the attempt is
        // marked settled, so callers stop waiting and can offer a retry.
        state.fieldPermissionStatus[action.meta.arg] = 'error';
        state.error = action.payload as string;
      });
  },
});

export const { clearRbac } = rbacSlice.actions;
export default rbacSlice.reducer;
