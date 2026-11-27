import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  KeyRound,
  Plus,
  Save,
  Search,
  Trash2,
  UserCheck,
  UserPlus,
  UserX,
  X,
} from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { EditUserModal } from '../components/EditUserModal';
import { PasswordInput } from '../components/PasswordInput';
import { Role, User } from '../types';

type AdminTab = 'overview' | 'users' | 'settings' | 'audit';

interface AdminDashboardPageProps {
  initialTab?: AdminTab;
}

const ROLE_BADGE_STYLES: Record<string, string> = {
  admin: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300',
  teacher: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
  student: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
};

const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin',
  teacher: 'Teacher',
  student: 'Student',
};

function formatCreatedAt(value?: string): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const AdminDashboardPage: React.FC<AdminDashboardPageProps> = ({
  initialTab = 'overview',
}) => {
  const {
    user: currentUser,
    loadingAuth,
    isAdmin,
    isStaff,
    toast,
    refreshPublicConfig,
    refreshUser,
  } = useApp();
  const navigate = useNavigate();
  const location = useLocation();

  const [tab, setTab] = useState<AdminTab>(initialTab);
  const [stats, setStats] = useState<any>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [userSearch, setUserSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<'all' | Role>('all');
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [logs, setLogs] = useState<any[]>([]);
  const [newUser, setNewUser] = useState({
    username: '',
    email: '',
    full_name: '',
    password: '',
    role: 'student',
  });
  const [busyUserId, setBusyUserId] = useState<number | null>(null);
  const [togglingReg, setTogglingReg] = useState(false);
  const [editTarget, setEditTarget] = useState<User | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);

  useEffect(() => {
    if (location.pathname === '/admin/users') {
      setTab('users');
      return;
    }
    const navStateTab = (location.state as { tab?: AdminTab } | null)?.tab;
    if (navStateTab) {
      setTab(navStateTab);
    } else if (initialTab) {
      setTab(initialTab);
    }
  }, [initialTab, location.pathname, location.state]);

  const load = useCallback(() => {
    if (!isStaff) return;
    api.getAdminStats().then(setStats).catch(() => {});
    setLoadingUsers(true);
    const fetchUsers = isAdmin ? api.listAdminUsers('', 1000) : api.listUsers('', 1000);
    fetchUsers
      .then((r) => setUsers(r.items || []))
      .catch(() => {})
      .finally(() => setLoadingUsers(false));
    if (isAdmin) {
      api.getAdminSettings().then((r) => setSettings(r.settings || {})).catch(() => {});
      api.listAuditLogs().then((r) => setLogs(r.items || [])).catch(() => {});
    }
  }, [isAdmin, isStaff]);

  useEffect(() => {
    load();
  }, [load]);

  const filteredUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase();
    return users.filter((u) => {
      if (roleFilter !== 'all' && !(u.roles || []).includes(roleFilter)) {
        return false;
      }
      if (!q) return true;
      return (
        (u.full_name || '').toLowerCase().includes(q) ||
        (u.username || '').toLowerCase().includes(q) ||
        (u.email || '').toLowerCase().includes(q)
      );
    });
  }, [users, userSearch, roleFilter]);

  const handleSelectTab = (nextTab: AdminTab) => {
    setTab(nextTab);
    if (nextTab === 'users' && isAdmin && location.pathname !== '/admin/users') {
      navigate('/admin/users');
    } else if (nextTab !== 'users' && location.pathname === '/admin/users') {
      navigate('/admin', { state: { tab: nextTab } });
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createUser({
        username: newUser.username.trim(),
        email: newUser.email.trim(),
        full_name: newUser.full_name.trim(),
        password: newUser.password,
        roles: [newUser.role],
      });
      toast(`Đã tạo tài khoản ${newUser.username.trim()}.`, 'success');
      setNewUser({ username: '', email: '', full_name: '', password: '', role: 'student' });
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  const handleToggleUserActive = async (u: User) => {
    setBusyUserId(u.id);
    try {
      const nextActive = !u.is_active;
      await api.updateUser(u.id, { is_active: nextActive });
      toast(
        nextActive ? `Đã kích hoạt lại tài khoản ${u.username}.` : `Đã khóa tài khoản ${u.username}.`,
        'success'
      );
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    } finally {
      setBusyUserId(null);
    }
  };

  const handleUserSaved = async (updatedUser: User, passwordChanged: boolean) => {
    const isSelf = Boolean(currentUser && Number(currentUser.id) === Number(updatedUser.id));
    setEditTarget(null);
    toast(
      passwordChanged
        ? `Đã cập nhật tài khoản ${updatedUser.username} và đặt lại mật khẩu mới.`
        : `Đã cập nhật thông tin tài khoản ${updatedUser.username}.`,
      'success'
    );
    load();
    if (isSelf) {
      await refreshUser();
    }
  };

  const handleConfirmDeleteUser = async () => {
    if (!deleteTarget) return;
    setBusyUserId(deleteTarget.id);
    try {
      await api.deleteUser(deleteTarget.id);
      toast(`Đã xóa tài khoản ${deleteTarget.username}.`, 'success');
      setDeleteTarget(null);
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    } finally {
      setBusyUserId(null);
    }
  };

  const allowRegEnabled = (settings.allow_registration ?? 'true').toLowerCase() === 'true';

  const handleToggleRegistration = async () => {
    setTogglingReg(true);
    const nextVal = allowRegEnabled ? 'false' : 'true';
    try {
      await api.updateAdminSettings({ ...settings, allow_registration: nextVal });
      setSettings((prev) => ({ ...prev, allow_registration: nextVal }));
      await refreshPublicConfig();
      toast(
        nextVal === 'true'
          ? 'Đã bật cho phép người dùng tự đăng ký tài khoản mới.'
          : 'Đã tắt chức năng tự đăng ký tài khoản mới.',
        'success'
      );
    } catch (err: any) {
      toast(err.message, 'error');
    } finally {
      setTogglingReg(false);
    }
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.updateAdminSettings(settings);
      await refreshPublicConfig();
      toast('Đã cập nhật cấu hình hệ thống.', 'success');
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  if (!loadingAuth && !isStaff) {
    return (
      <div className="mx-auto max-w-md py-12">
        <div className="noka-section p-6 text-center space-y-3">
          <h1 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Không có quyền truy cập
          </h1>
          <p className="text-xs text-zinc-500">
            Chỉ Quản trị viên hoặc Giáo viên mới có quyền truy cập trang quản trị hệ thống.
          </p>
          <Link to="/" className="noka-btn-primary inline-flex">
            Quay về Trang chủ
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">
          {tab === 'users' ? 'Quản lý người dùng' : 'Quản trị hệ thống'}
        </h1>
        <Link to="/admin/problems/new" className="noka-btn-primary text-xs">
          <Plus className="h-3.5 w-3.5" /> Tạo bài tập mới
        </Link>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-zinc-200 dark:border-zinc-800">
        {[
          { id: 'overview' as AdminTab, label: 'Tổng quan' },
          { id: 'users' as AdminTab, label: `Quản lý người dùng (${users.length})` },
          ...(isAdmin
            ? [
                { id: 'settings' as AdminTab, label: 'Cấu hình hệ thống' },
                { id: 'audit' as AdminTab, label: 'Audit Logs' },
              ]
            : []),
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => handleSelectTab(t.id)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? 'border-[#2A5C99] text-[#2A5C99] dark:border-[#89B4E8] dark:text-[#89B4E8]'
                : 'border-transparent text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && stats && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {[
            { label: 'Người dùng', value: stats.users_count },
            { label: 'Bài tập', value: stats.problems_count },
            { label: 'Bài nộp', value: stats.submissions_count },
            { label: 'Kỳ thi', value: stats.contests_count },
            { label: 'Lớp học', value: stats.classrooms_count },
          ].map((m) => (
            <div key={m.label} className="noka-section p-4">
              <div className="text-xs text-zinc-500">{m.label}</div>
              <div className="mt-1 font-mono text-2xl font-semibold">{m.value}</div>
            </div>
          ))}
        </div>
      )}

      {tab === 'users' && (
        <div className="space-y-4">
          {isAdmin && (
            <div className="noka-section p-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-medium">
                  <span>Cho phép người dùng tự đăng ký tài khoản mới</span>
                  <span
                    className={`rounded px-2 py-0.5 text-[11px] font-medium ${
                      allowRegEnabled
                        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
                        : 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
                    }`}
                  >
                    {allowRegEnabled ? 'Đang bật' : 'Đang tắt'}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-zinc-500">
                  {allowRegEnabled
                    ? 'Người dùng mới có thể tự tạo tài khoản qua trang Đăng ký.'
                    : 'Đã khóa tự đăng ký để tránh spam; chỉ Admin/Giáo viên mới tạo được tài khoản.'}
                </p>
              </div>
              <button
                type="button"
                disabled={togglingReg}
                onClick={handleToggleRegistration}
                className={allowRegEnabled ? 'noka-btn-secondary text-xs' : 'noka-btn-primary text-xs'}
              >
                {togglingReg
                  ? 'Đang cập nhật...'
                  : allowRegEnabled
                  ? 'Tắt đăng ký công khai'
                  : 'Bật đăng ký công khai'}
              </button>
            </div>
          )}

          <form onSubmit={handleCreateUser} className="noka-section p-4 grid grid-cols-1 sm:grid-cols-6 gap-2.5">
            <input
              required
              minLength={3}
              value={newUser.username}
              onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
              placeholder="Username"
              className="noka-input text-xs"
            />
            <input
              required
              type="email"
              value={newUser.email}
              onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
              placeholder="Email"
              className="noka-input text-xs"
            />
            <input
              value={newUser.full_name}
              onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })}
              placeholder="Tên hiển thị"
              className="noka-input text-xs"
            />
            <PasswordInput
              required
              minLength={6}
              autoComplete="new-password"
              value={newUser.password}
              onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
              placeholder="Mật khẩu (≥ 6 ký tự)"
              className="noka-input text-xs"
            />
            <select
              value={newUser.role}
              onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
              className="noka-input text-xs"
            >
              <option value="student">Student</option>
              {isAdmin && <option value="teacher">Teacher</option>}
              {isAdmin && <option value="admin">Admin</option>}
            </select>
            <button type="submit" className="noka-btn-primary text-xs">
              <UserPlus className="h-3.5 w-3.5" /> Tạo tài khoản
            </button>
          </form>

          {/* Instant search & role filter bar */}
          <div className="noka-section p-3.5 flex flex-wrap items-center justify-between gap-3">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
              <input
                type="text"
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                placeholder="Tìm kiếm tức thì theo tên hiển thị, tên đăng nhập hoặc email..."
                className="noka-input !pl-9 !pr-8 text-xs"
              />
              {userSearch && (
                <button
                  type="button"
                  onClick={() => setUserSearch('')}
                  aria-label="Xóa tìm kiếm"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            <div className="flex items-center gap-2.5">
              <select
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value as 'all' | Role)}
                className="noka-input !w-auto text-xs"
                aria-label="Lọc theo vai trò"
              >
                <option value="all">Tất cả vai trò</option>
                <option value="admin">Admin</option>
                <option value="teacher">Teacher</option>
                <option value="student">Student</option>
              </select>
              <span className="text-xs text-zinc-500 whitespace-nowrap">
                Hiển thị <strong className="text-zinc-800 dark:text-zinc-200">{filteredUsers.length}</strong> / {users.length}
              </span>
            </div>
          </div>

          <div className="noka-section overflow-x-auto">
            <table className="noka-table text-xs">
              <thead>
                <tr>
                  <th>Tên hiển thị</th>
                  <th>Tên đăng nhập</th>
                  <th>Email</th>
                  <th>Vai trò</th>
                  <th>Trạng thái</th>
                  <th>Ngày tạo</th>
                  {isAdmin && <th className="text-right">Thao tác</th>}
                </tr>
              </thead>
              <tbody>
                {loadingUsers && users.length === 0 ? (
                  <tr>
                    <td colSpan={isAdmin ? 7 : 6} className="py-8 text-center text-zinc-500">
                      Đang tải danh sách người dùng...
                    </td>
                  </tr>
                ) : filteredUsers.length === 0 ? (
                  <tr>
                    <td colSpan={isAdmin ? 7 : 6} className="py-8 text-center text-zinc-500">
                      {userSearch.trim()
                        ? `Không tìm thấy tài khoản nào phù hợp với từ khóa "${userSearch.trim()}".`
                        : 'Không có tài khoản nào phù hợp với bộ lọc hiện tại.'}
                    </td>
                  </tr>
                ) : (
                  filteredUsers.map((u) => {
                    const isSelf = Boolean(currentUser && Number(currentUser.id) === Number(u.id));
                    const roles = u.roles && u.roles.length > 0 ? u.roles : [u.role || 'student'];
                    return (
                      <tr key={u.id} className={!u.is_active ? 'opacity-65' : ''}>
                        <td className="font-medium text-zinc-900 dark:text-zinc-100">
                          {u.full_name || '—'}
                        </td>
                        <td className="font-mono font-medium">
                          <span>{u.username}</span>
                          {isSelf && (
                            <span className="ml-1.5 rounded bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 font-sans text-[10px] font-normal text-zinc-500">
                              Bạn
                            </span>
                          )}
                        </td>
                        <td className="text-zinc-500">{u.email}</td>
                        <td>
                          <div className="flex flex-wrap gap-1">
                            {roles.map((r) => (
                              <span
                                key={r}
                                className={`rounded px-2 py-0.5 text-[11px] font-medium ${
                                  ROLE_BADGE_STYLES[r] || ROLE_BADGE_STYLES.student
                                }`}
                              >
                                {ROLE_LABELS[r] || r}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td>
                          {u.is_active ? (
                            <span className="rounded bg-emerald-100 dark:bg-emerald-900/40 px-2 py-0.5 text-[11px] font-medium text-emerald-800 dark:text-emerald-300">
                              Hoạt động
                            </span>
                          ) : (
                            <span className="rounded bg-rose-100 dark:bg-rose-900/40 px-2 py-0.5 text-[11px] font-medium text-rose-800 dark:text-rose-300">
                              Đã khóa
                            </span>
                          )}
                        </td>
                        <td className="font-mono text-zinc-500 whitespace-nowrap">
                          {formatCreatedAt(u.created_at)}
                        </td>
                        {isAdmin && (
                          <td className="text-right">
                            <div className="inline-flex items-center justify-end gap-1.5">
                              <button
                                type="button"
                                disabled={busyUserId === u.id}
                                onClick={() => setEditTarget(u)}
                                className="inline-flex items-center gap-1 rounded border border-[#2A5C99]/30 bg-[#EBF3FC] dark:border-[#89B4E8]/30 dark:bg-[#89B4E8]/15 px-2 py-1 text-[11px] font-medium text-[#2A5C99] dark:text-[#A7C8F0] hover:bg-[#dceafb] dark:hover:bg-[#89B4E8]/25 disabled:opacity-50 whitespace-nowrap"
                                title="Chỉnh sửa thông tin hoặc đặt lại mật khẩu"
                              >
                                <KeyRound className="h-3 w-3" /> Chỉnh sửa / Đổi mật khẩu
                              </button>
                              {!isSelf && (
                                <>
                                  <button
                                    type="button"
                                    disabled={busyUserId === u.id}
                                    onClick={() => handleToggleUserActive(u)}
                                    className="inline-flex items-center gap-1 rounded border border-zinc-200 dark:border-zinc-700 px-2 py-1 text-[11px] font-medium hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50 whitespace-nowrap"
                                    title={u.is_active ? 'Khóa tài khoản' : 'Mở khóa tài khoản'}
                                  >
                                    {u.is_active ? (
                                      <>
                                        <UserX className="h-3 w-3 text-amber-600 dark:text-amber-400" /> Khóa
                                      </>
                                    ) : (
                                      <>
                                        <UserCheck className="h-3 w-3 text-emerald-600 dark:text-emerald-400" /> Mở khóa
                                      </>
                                    )}
                                  </button>
                                  <button
                                    type="button"
                                    disabled={busyUserId === u.id}
                                    onClick={() => setDeleteTarget(u)}
                                    className="inline-flex items-center gap-1 rounded border border-rose-200 dark:border-rose-900/60 px-2 py-1 text-[11px] font-medium text-rose-700 dark:text-rose-300 hover:bg-rose-50 dark:hover:bg-rose-950/40 disabled:opacity-50"
                                    title="Xóa vĩnh viễn tài khoản"
                                  >
                                    <Trash2 className="h-3 w-3" /> Xóa
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        )}
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'settings' && isAdmin && (
        <form onSubmit={handleSaveSettings} className="noka-section p-5 max-w-lg space-y-4">
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">
              Tên hệ thống (Centralized Branding)
            </label>
            <input
              value={settings.site_name || ''}
              onChange={(e) => setSettings({ ...settings, site_name: e.target.value })}
              className="noka-input"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">
              Cho phép tự đăng ký (tránh spam)
            </label>
            <select
              value={settings.allow_registration || 'true'}
              onChange={(e) => setSettings({ ...settings, allow_registration: e.target.value })}
              className="noka-input"
            >
              <option value="true">Cho phép</option>
              <option value="false">Tắt đăng ký công khai</option>
            </select>
          </div>
          <button type="submit" className="noka-btn-primary">
            <Save className="h-4 w-4" /> Lưu cấu hình
          </button>
        </form>
      )}

      {tab === 'audit' && isAdmin && (
        <div className="noka-section overflow-x-auto">
          <table className="noka-table text-xs">
            <thead>
              <tr>
                <th>Thời gian</th>
                <th>User</th>
                <th>Hành động</th>
                <th>Đối tượng</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id}>
                  <td className="font-mono text-zinc-500">{new Date(l.created_at).toLocaleString()}</td>
                  <td className="font-medium">{l.username || 'system'}</td>
                  <td className="font-mono">{l.action}</td>
                  <td className="font-mono text-zinc-500">
                    {l.entity_type} #{l.entity_id}
                  </td>
                  <td className="font-mono text-zinc-500">{l.ip_address}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <EditUserModal
        user={editTarget}
        isSelf={Boolean(editTarget && currentUser && Number(currentUser.id) === Number(editTarget.id))}
        onClose={() => setEditTarget(null)}
        onSaved={handleUserSaved}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Xóa tài khoản?"
        description={`Bạn có chắc muốn xóa vĩnh viễn tài khoản "${deleteTarget?.username || ''}" (${deleteTarget?.full_name || deleteTarget?.email || ''})? Toàn bộ bài nộp và đăng ký lớp học/kỳ thi của tài khoản này cũng sẽ bị xóa.`}
        confirmLabel="Xóa tài khoản"
        danger
        onConfirm={handleConfirmDeleteUser}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
};
