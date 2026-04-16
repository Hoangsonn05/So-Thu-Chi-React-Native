/**
 * api.ts
 * Centralized API configuration for backend services.
 */

// Thay đổi địa chỉ Ngrok của bạn tại đây trước khi sử dụng tính năng Xuất báo cáo Email
export const BACKEND_URL = 'https://unsystematising-judie-interfoliaceous.ngrok-free.dev';

export const API_ENDPOINTS = {
  EXPORT_EMAIL: `${BACKEND_URL}/api/export-email`,
};
