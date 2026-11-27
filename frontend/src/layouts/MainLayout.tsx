import React from 'react';
import { Link, NavLink, Outlet } from 'react-router-dom';
import {
  Code2,
  Moon,
  Sun,
  LogOut,
  Shield,
  Terminal,
  Trophy,
  UserCog,
  Users,
  FileCode,
  Home,
} from 'lucide-react';
import { useApp } from '../stores/AppContext';

export const MainLayout: React.FC = () => {
  const { siteName, allowRegistration, theme, toggleTheme, user, isAdmin, isStaff, logout } = useApp();

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `inline-flex items-center gap-1.5 whitespace-nowrap px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors ${
      isActive
        ? 'bg-[#EBF3FC] text-[#2A5C99] dark:bg-[#89B4E8]/15 dark:text-[#A7C8F0]'
        : 'text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:text-zinc-100 dark:hover:bg-zinc-800/70'
    }`;

  return (
    <div className="min-h-screen flex flex-col bg-white dark:bg-[#0E1013]">
      <header className="sticky top-0 z-30 h-13 border-b border-zinc-200 dark:border-zinc-800 bg-white/95 dark:bg-[#0E1013]/95">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-4 lg:gap-6">
            <Link to="/" className="flex items-center gap-2 whitespace-nowrap font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
              <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[#2A5C99] dark:bg-[#89B4E8] text-white dark:text-[#0E1013]">
                <Terminal className="h-4 w-4" />
              </span>
              <span>{siteName}</span>
            </Link>

            <nav className="hidden md:flex items-center gap-1">
              <NavLink to="/" end className={navClass}>
                <Home className="h-4 w-4" />
                Trang chủ
              </NavLink>
              <NavLink to="/problems" className={navClass}>
                <Code2 className="h-4 w-4" />
                Bài tập
              </NavLink>
              <NavLink to="/submissions" className={navClass}>
                <FileCode className="h-4 w-4" />
                Bài nộp
              </NavLink>
              <NavLink to="/contests" className={navClass}>
                <Trophy className="h-4 w-4" />
                Kỳ thi
              </NavLink>
              <NavLink to="/classrooms" className={navClass}>
                <Users className="h-4 w-4" />
                Lớp học
              </NavLink>
              {isStaff && (
                <NavLink to="/admin" end className={navClass}>
                  <Shield className="h-4 w-4" />
                  Quản trị
                </NavLink>
              )}
              {isAdmin && (
                <NavLink to="/admin/users" className={navClass}>
                  <UserCog className="h-4 w-4" />
                  Quản lý người dùng
                </NavLink>
              )}
            </nav>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={toggleTheme}
              title={theme === 'light' ? 'Chuyển sang Dark Mode' : 'Chuyển sang Light Mode'}
              className="rounded-md border border-zinc-200 dark:border-zinc-800 p-1.5 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            >
              {theme === 'light' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            </button>

            {user ? (
              <div className="flex items-center gap-2 pl-2 border-l border-zinc-200 dark:border-zinc-800">
                <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                  {user.username}
                </span>
                <span className="hidden sm:inline-block rounded bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 text-[11px] font-mono text-zinc-500 dark:text-zinc-400">
                  {user.roles[0]}
                </span>
                <button
                  onClick={logout}
                  title="Đăng xuất"
                  className="rounded-md p-1.5 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Link to="/login" className="noka-btn-secondary">
                  Đăng nhập
                </Link>
                {allowRegistration && (
                  <Link to="/register" className="noka-btn-primary">
                    Đăng ký
                  </Link>
                )}
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
};
