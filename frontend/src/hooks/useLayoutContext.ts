import React from 'react';
import { useOutletContext } from 'react-router';
import type { LayoutContext } from '../types';

/**
 * Re-exports the layout outlet context typed for the whole app.
 * Usage: const { userRole, userName } = useLayoutContext();
 */
export function useLayoutContext() {
  return useOutletContext<LayoutContext>();
}
