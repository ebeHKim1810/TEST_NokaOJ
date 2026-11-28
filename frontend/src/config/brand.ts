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

const LEGACY_SITE_NAMES = new Set(['noka judge', 'nokaoj', 'test_nokaoj']);

/**
 * Centralized Branding Configuration.
 * Change VITE_APP_NAME in .env or update site_name in Admin Settings to rebrand the platform.
 */
export const BRAND_CONFIG = {
  defaultSiteName: import.meta.env.VITE_APP_NAME || 'HKKD_Judge',
  apiBaseUrl: normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL),
};

export function resolveSiteName(raw?: string): string {
  const trimmed = (raw || '').trim();
  if (!trimmed || LEGACY_SITE_NAMES.has(trimmed.toLowerCase())) {
    return BRAND_CONFIG.defaultSiteName;
  }
  return trimmed;
}
