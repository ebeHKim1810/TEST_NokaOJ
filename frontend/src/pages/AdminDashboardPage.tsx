import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Save, Trash2, UserCheck, UserPlus, UserX } from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { ConfirmDialog } from '../components/ConfirmDialog';

export const AdminDashboardPage: React.FC = () => {
  const { user: currentUser, isAdmin, toast, refreshPublicConfig } = useApp();
  const [tab, setTab] = useState<'overview' | 'users' | 'settings' | 'audit'>('overview');
  const [stats, setStats] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [logs, setLogs] = useState<any[]>([]);
  const [newUser, setNewUser] = useState({ username: '', email: '', full_name: '', password: '', role: 'student' });
  const [busyUserId, setBusyUserId] = useState<number | null>(null);
  const [togglingReg, setTogglingReg] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<any | null>(null);

  const load = () => {
    api.getAdminStats().then(setStats).catch(() => {});
    api.listUsers().then((r) => setUsers(r.items || [])).catch(() => {});
    if (isAdmin) {
      api.getAdminSettings().then((r) => setSettings(r.settings || {})).catch(() => {});
      api.listAuditLogs().then((r) => setLogs(r.items || [])).catch(() => {});
    }
  };

  useEffect(() => {
    load();
  }, [isAdmin]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createUser({
        username: newUser.username,
        email: newUser.email,
        full_name: newUser.full_name,
        password: newUser.password,
        roles: [newUser.role],
      });
      toast(`Đã tạo tài khoản ${newUser.username}.`, 'success');
      setNewUser({ username: '', email: '', full_name: '', password: '', role: 'student' });
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  const handleToggleUserActive = async (u: any) => {
    setBusyUserId(u.id);
    try {
      const nextActive = !u.is_active;
      await api.updateUser(u.id, { is_active: nextActive });
      toast(
        nextActive ? `Đã kích hoạt lại tài khoản ${u.username}.` : `Đã vô hiệu hóa tài khoản ${u.username}.`,
        'success'
      );
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    } finally {
      setBusyUserId(null);
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

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Quản trị hệ thống</h1>
        <Link to="/admin/problems/new" className="noka-btn-primary text-xs">
          <Plus className="h-3.5 w-3.5" /> Tạo bài tập mới
        </Link>
      </div>

      <div className="flex gap-2 border-b border-zinc-200 dark:border-zinc-800">
        {[
          { id: 'overview', label: 'Tổng quan' },
          { id: 'users', label: `Tài khoản (${users.length})` },
          ...(isAdmin
            ? [
                { id: 'settings', label: 'Cấu hình hệ thống' },
                { id: 'audit', label: 'Audit Logs' },
              ]
            : []),
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id as any)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === t.id ? 'border-[#2A5C99] dark:border-[#89B4E8]' : 'border-transparent text-zinc-500'
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
            <input required value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} placeholder="Username" className="noka-input text-xs" />
            <input required type="email" value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} placeholder="Email" className="noka-input text-xs" />
            <input value={newUser.full_name} onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })} placeholder="Họ tên" className="noka-input text-xs" />
            <input required type="password" minLength={6} value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} placeholder="Mật khẩu" className="noka-input text-xs" />
            <select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })} className="noka-input text-xs">
              <option value="student">Student</option>
              {isAdmin && <option value="teacher">Teacher</option>}
              {isAdmin && <option value="admin">Admin</option>}
            </select>
            <button type="submit" className="noka-btn-primary text-xs">
              <UserPlus className="h-3.5 w-3.5" /> Tạo tài khoản
            </button>
          </form>

          <div className="noka-section overflow-x-auto">
            <table className="noka-table text-xs">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Username</th>
                  <th>Họ tên</th>
                  <th>Email</th>
                  <th>Vai trò</th>
                  <th>Trạng thái</th>
                  {isAdmin && <th className="text-right">Thao tác</th>}
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const isSelf = currentUser && Number(currentUser.id) === Number(u.id);
                  return (
                    <tr key={u.id} className={!u.is_active ? 'opacity-65' : ''}>
                      <td className="font-mono text-zinc-500">{u.id}</td>
                      <td className="font-medium">
                        {u.username}
                        {isSelf && (
                          <span className="ml-1.5 rounded bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 text-[10px] font-normal text-zinc-500">
                            Bạn
                          </span>
                        )}
                      </td>
                      <td>{u.full_name}</td>
                      <td className="text-zinc-500">{u.email}</td>
                      <td className="font-mono">{(u.roles || []).join(', ')}</td>
                      <td>
                        {u.is_active ? (
                          <span className="rounded bg-emerald-100 dark:bg-emerald-900/40 px-2 py-0.5 text-[11px] font-medium text-emerald-800 dark:text-emerald-300">
                            Hoạt động
                          </span>
                        ) : (
                          <span className="rounded bg-rose-100 dark:bg-rose-900/40 px-2 py-0.5 text-[11px] font-medium text-rose-800 dark:text-rose-300">
                            Vô hiệu hóa
                          </span>
                        )}
                      </td>
                      {isAdmin && (
                        <td className="text-right">
                          {!isSelf && (
                            <div className="inline-flex items-center justify-end gap-1.5">
                              <button
                                type="button"
                                disabled={busyUserId === u.id}
                                onClick={() => handleToggleUserActive(u)}
                                className="inline-flex items-center gap-1 rounded border border-zinc-200 dark:border-zinc-700 px-2 py-1 text-[11px] font-medium hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50"
                                title={u.is_active ? 'Vô hiệu hóa tài khoản' : 'Kích hoạt lại tài khoản'}
                              >
                                {u.is_active ? (
                                  <>
                                    <UserX className="h-3 w-3 text-amber-600 dark:text-amber-400" /> Vô hiệu hóa
                                  </>
                                ) : (
                                  <>
                                    <UserCheck className="h-3 w-3 text-emerald-600 dark:text-emerald-400" /> Kích hoạt
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
                            </div>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'settings' && isAdmin && (
        <form onSubmit={handleSaveSettings} className="noka-section p-5 max-w-lg space-y-4">
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Tên hệ thống (Centralized Branding)</label>
            <input
              value={settings.site_name || ''}
              onChange={(e) => setSettings({ ...settings, site_name: e.target.value })}
              className="noka-input"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Cho phép tự đăng ký (tránh spam)</label>
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
