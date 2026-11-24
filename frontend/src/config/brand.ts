/**
 * Normalize API base URL from VITE_API_BASE_URL so both relative proxy paths
 * ("/api/v1") and full external Backend URLs (e.g. "https://api.example.com"
 * or "https://api.example.com/api/v1/") map accurately to FastAPI's /api/v1 prefix.
 */
export function normalizeApiBaseUrl(raw?: string): string {
  const trimmed = (raw || '').trim().replace(/\/+$/, '');
  if (!trimmed) return '/api/v1';

  if (/^https?:\/\//i.test(trimmed)) {
    try {
      const parsed = new URL(trimmed);
      const cleanPath = parsed.pathname.replace(/\/+$/, '');
      if (!cleanPath || cleanPath === '/api') {
        return `${parsed.origin}/api/v1`;
      }
      return `${parsed.origin}${cleanPath}`;
    } catch {
      return trimmed;
    }
  }

  if (trimmed === '/api' || trimmed === 'api') return '/api/v1';
  return trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
}

/**
 * Centralized Branding Configuration.
 * Change VITE_APP_NAME in .env or update site_name in Admin Settings to rebrand the platform.
 */
export const BRAND_CONFIG = {
  defaultSiteName: import.meta.env.VITE_APP_NAME || 'Noka JUDGE',
  apiBaseUrl: normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL),
};
