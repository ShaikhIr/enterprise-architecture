/**
 * Redux store configuration.
 * Federated store supporting lazy-loaded feature slices.
 */

import { configureStore } from '@reduxjs/toolkit';
import type { TypedUseSelectorHook } from 'react-redux';
import { useDispatch, useSelector } from 'react-redux';

import { rbacReducer } from '@core/rbac';

import authReducer from '@features/authentication/store/authSlice';

export const store = configureStore({
  reducer: {
    auth: authReducer,
    rbac: rbacReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: false,
    }),
  devTools: import.meta.env.DEV,
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export const useAppDispatch = () => useDispatch<AppDispatch>();
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;
