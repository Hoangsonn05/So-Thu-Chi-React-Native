/**
 * api.ts
 * Centralized API configuration for backend services.
 */

// Centralized API URL from environment variables
export const BACKEND_URL = process.env.EXPO_PUBLIC_API_URL;

export const API_ENDPOINTS = {
  EXPORT_EMAIL: `${BACKEND_URL}/api/export-email`,
};
