/**
 * Centralized Branding Configuration.
 * Change VITE_APP_NAME in .env or update site_name in Admin Settings to rebrand the platform.
 */
export const BRAND_CONFIG = {
  defaultSiteName: import.meta.env.VITE_APP_NAME || 'Noka JUDGE',
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || '/api/v1',
};
