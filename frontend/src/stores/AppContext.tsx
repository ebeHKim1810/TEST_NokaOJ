import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { BRAND_CONFIG } from '../config/brand';
import { api, getStoredToken, setStoredToken } from '../services/api';
import { User } from '../types';

type Theme = 'light' | 'dark';
type ToastType = 'success' | 'error' | 'warning' | 'info';

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

interface AppContextValue {
  siteName: string;
  allowRegistration: boolean;
  refreshPublicConfig: () => Promise<void>;
  theme: Theme;
  toggleTheme: () => void;
  user: User | null;
  loadingAuth: boolean;
  isAdmin: boolean;
  isStaff: boolean;
  loginWithToken: (token: string, user: User) => void;
  logout: () => void;
  refreshUser: () => Promise<void>;
  toast: (message: string, type?: ToastType) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [siteName, setSiteName] = useState(BRAND_CONFIG.defaultSiteName);
  const [allowRegistration, setAllowRegistration] = useState(true);
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('noka_theme');
    return saved === 'dark' ? 'dark' : 'light';
  });
  const [user, setUser] = useState<User | null>(null);
  const [loadingAuth, setLoadingAuth] = useState(true);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') root.classList.add('dark');
    else root.classList.remove('dark');
    localStorage.setItem('noka_theme', theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
  }, []);

  const toast = useCallback((message: string, type: ToastType = 'info') => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const refreshUser = useCallback(async () => {
    const token = getStoredToken();
    if (!token) {
      setUser(null);
      setLoadingAuth(false);
      return;
    }
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      setStoredToken(null);
      setUser(null);
    } finally {
      setLoadingAuth(false);
    }
  }, []);

  const refreshPublicConfig = useCallback(async () => {
    try {
      const cfg = await api.getPublicConfig();
      if (cfg.site_name) {
        setSiteName(cfg.site_name);
        document.title = cfg.site_name;
      }
      if (typeof cfg.allow_registration === 'boolean') {
        setAllowRegistration(cfg.allow_registration);
      }
    } catch {
      // keep existing config
    }
  }, []);

  useEffect(() => {
    refreshPublicConfig();
    refreshUser();
  }, [refreshPublicConfig, refreshUser]);

  const loginWithToken = useCallback((token: string, u: User) => {
    setStoredToken(token);
    setUser(u);
  }, []);

  const logout = useCallback(() => {
    setStoredToken(null);
    setUser(null);
    toast('Đã đăng xuất.', 'info');
  }, [toast]);

  const isAdmin = Boolean(user?.roles?.includes('admin'));
  const isStaff = Boolean(user?.roles?.includes('admin') || user?.roles?.includes('teacher'));

  const toastColors: Record<ToastType, string> = {
    success: 'border-[#84CBA3] bg-[#EBF7F0] text-[#1F6F45] dark:bg-[#14261D] dark:text-[#9FE0BA]',
    error: 'border-[#E59CB4] bg-[#FDF0F4] text-[#9B3558] dark:bg-[#29151C] dark:text-[#F0B4C8]',
    warning: 'border-[#EDB57E] bg-[#FEF4EA] text-[#945214] dark:bg-[#2A1E12] dark:text-[#F4CA9E]',
    info: 'border-[#89B4E8] bg-[#EBF3FC] text-[#2A5C99] dark:bg-[#142030] dark:text-[#A8C9F2]',
  };

  return (
    <AppContext.Provider
      value={{
        siteName,
        allowRegistration,
        refreshPublicConfig,
        theme,
        toggleTheme,
        user,
        loadingAuth,
        isAdmin,
        isStaff,
        loginWithToken,
        logout,
        refreshUser,
        toast,
      }}
    >
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`flex items-center justify-between gap-3 rounded-md border px-3.5 py-2.5 text-sm shadow-sm ${toastColors[t.type]}`}
          >
            <span>{t.message}</span>
            <button
              onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
              className="opacity-70 hover:opacity-100"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </AppContext.Provider>
  );
};

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}
