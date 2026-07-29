/**
 * Brand color constants — single source of truth.
 * Previously duplicated in every component file.
 */
export const COLORS = {
  BLUE: '#1F5FA8',
  TEAL: '#1FB7B5',
  RED: '#D93A2F',
  GREEN: '#10B981',
  YELLOW: '#F59E0B',
  PURPLE: '#7C3AED',
  BORDER: '#E5E7EB',
  TEXT: '#1F2937',
  TEXT_SECONDARY: '#6B7280',
  TEXT_MUTED: '#9CA3AF',
  BG: '#F7FAFC',
  BG_LIGHT: '#F9FAFB',
  WHITE: '#FFFFFF',
} as const;

export type AppColor = (typeof COLORS)[keyof typeof COLORS];

/** Convenience aliases used most frequently */
export const BLUE = COLORS.BLUE;
export const TEAL = COLORS.TEAL;
export const RED = COLORS.RED;
export const BORDER = COLORS.BORDER;
export const TEXT = COLORS.TEXT;
export const TEXT_SECONDARY = COLORS.TEXT_SECONDARY;
export const TEXT_MUTED = COLORS.TEXT_MUTED;
export const BG = COLORS.BG;
export const GREEN = COLORS.GREEN;
export const YELLOW = COLORS.YELLOW;

/** Chart palette */
export const PRODUCT_COLORS = [
  COLORS.BLUE,
  COLORS.TEAL,
  '#7C3AED',
  '#059669',
  '#D97706',
  '#D93A2F',
  '#0891B2',
  '#9333EA',
  '#16A34A',
  '#DC2626',
  '#0D9488',
];

export const DIST_COLORS = [
  COLORS.BLUE,
  COLORS.TEAL,
  '#7C3AED',
  '#059669',
  '#D97706',
  '#D93A2F',
  '#0891B2',
];

export const CHART_COLORS = [
  COLORS.BLUE,
  COLORS.TEAL,
  '#60A5FA',
  '#34D399',
  '#A78BFA',
  '#E5E7EB',
];
