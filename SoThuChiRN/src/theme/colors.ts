/**
 * Spatial UI Design Tokens - Compact Scaling Edition
 */

export const Colors = {
  // Core backgrounds (Spatial Dark Mode)
  spatialBg: '#0A0A0A',         // Matches Colors.bg
  spatialTextPrimary: '#FFFFFF',
  spatialTextSecondary: '#A0A0A0',
  spatialSparkleSilver: '#718096',

  // Glass & Input tokens for Spatial screens
  spatialGlassCardBg: 'rgba(255, 255, 255, 0.05)',
  spatialGlassBorder: 'rgba(255, 255, 255, 0.1)',
  inputBackground: 'rgba(255, 255, 255, 0.03)',
  placeholder: '#555555',
 

  // --- NEW: Bento Glassmorphism Dark Mode ---
  bg: '#0A0A0A',                // Deep Dark
  bgSecondary: '#121212',       // Dark Charcoal
  textPrimary: '#FFFFFF',
  textSecondary: '#A0A0A0',
  textTertiary: '#718096',

  // Glass tokens
  glassBg: 'rgba(255, 255, 255, 0.05)',
  glassBgLight: 'rgba(255, 255, 255, 0.12)',
  glassBorder: 'rgba(255, 255, 255, 0.08)',
  glassBorderStrong: 'rgba(255, 255, 255, 0.15)',

  // Brand & Bento Accents
  primaryGreen: '#1DB954',
  accentIncome: '#00E676',      // Mint Green
  accentExpense: '#FF5252',     // Coral Red
  accentBlue: '#00B0FF',

  // Legacy & Functional
  white: '#FFFFFF',
  black: '#000000',
  error: '#E53E3E',
  warning: '#DD6B20',
  success: '#38A169',
  info: '#3182CE',

  // Shadows
  shadowSoft: 'rgba(0, 0, 0, 0.4)',
} as const;

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 10,       // Compact gap
  lg: 12,       // Standard padding
  xl: 16,       // Container margin/padding
  xxl: 24,
  xxxl: 32,
} as const;

export const BorderRadius = {
  sm: 8,
  md: 12,       // Adjusted for smaller components
  lg: 15,       // Main corner radius
  xl: 18,
  xxl: 22,
  pill: 25,
  full: 9999,
} as const;

export const FontSize = {
  xs: 10,
  sm: 12,       // Labels
  md: 13,
  lg: 14,       // Standard Body
  xl: 16,       // Subheaders
  xxl: 18,      // Headers
  xxxl: 20,     // Max Title
  display: 24,  // Special amounts (with flexible scaling)
} as const;
