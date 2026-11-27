import React, { useEffect, useState } from 'react';
import { Check, Copy, KeyRound, Save, X } from 'lucide-react';
import { api } from '../services/api';
import { Role, User } from '../types';
import { PasswordInput } from './PasswordInput';

interface EditUserModalProps {
  user: User | null;
  isSelf: boolean;
  onClose: () => void;
  onSaved: (updatedUser: User, passwordChanged: boolean) => void;
}

function resolvePrimaryRole(u: User | null): Role {
  if (!u) return 'student';
  if (u.role) return u.role;
  const roles = u.roles || [];
  if (roles.includes('admin')) return 'admin';
  if (roles.includes('teacher')) return 'teacher';
  return 'student';
}

export const EditUserModal: React.FC<EditUserModalProps> = ({
  user,
  isSelf,
  onClose,
  onSaved,
}) => {
  const [fullName, setFullName] = useState('');
  const [username, setUsername] = useState('');
  const [role, setRole] = useState<Role>('student');
  const [isActive, setIsActive] = useState(true);
  const [newPassword, setNewPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [copiedPw, setCopiedPw] = useState(false);

  useEffect(() => {
    if (!user) return;
    setFullName(user.full_name || '');
    setUsername(user.username || '');
    setRole(resolvePrimaryRole(user));
    setIsActive(user.is_active === undefined ? true : Boolean(user.is_active));
    setNewPassword('');
    setError('');
    setCopiedPw(false);
  }, [user]);

  useEffect(() => {
    if (!user) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) {
        onClose();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [user, submitting, onClose]);

  if (!user) return null;

  const handleCopyPassword = async () => {
    if (!newPassword) return;
    try {
      await navigator.clipboard.writeText(newPassword);
      setCopiedPw(true);
      setTimeout(() => setCopiedPw(false), 1800);
    } catch {
      // Clipboard API may be unavailable in non-HTTPS contexts
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const cleanedUsername = username.trim();
    if (cleanedUsername.length < 3 || cleanedUsername.length > 64 || /\s/.test(cleanedUsername)) {
      setError('Tên đăng nhập phải từ 3 đến 64 ký tự và không chứa khoảng trắng.');
      return;
    }

    if (newPassword !== '') {
      if (newPassword.length < 6) {
        setError('Mật khẩu mới phải có ít nhất 6 ký tự.');
        return;
      }
      if (newPassword.trim() === '') {
        setError('Mật khẩu mới không được chỉ chứa khoảng trắng.');
        return;
      }
    }

    const payload: {
      full_name: string;
      username: string;
      new_password?: string;
      roles?: Role[];
      is_active?: boolean;
    } = {
      full_name: fullName.trim(),
      username: cleanedUsername,
    };

    if (newPassword !== '') {
      payload.new_password = newPassword;
    }

    if (!isSelf) {
      payload.roles = [role];
      payload.is_active = isActive;
    }

    setSubmitting(true);
    try {
      const updated = await api.updateUser(user.id, payload);
      onSaved(updated, Boolean(payload.new_password));
    } catch (err: any) {
      setError(err.message || 'Cập nhật tài khoản thất bại.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-md border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-[#14171D] shadow-lg">
        <div className="flex items-start justify-between gap-3 border-b border-zinc-200 dark:border-zinc-800 px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
              Chỉnh sửa tài khoản &amp; Đổi mật khẩu
            </h3>
            <p className="mt-0.5 text-xs text-zinc-500">
              ID #{user.id} · {user.email}
              {isSelf && ' · Tài khoản của bạn'}
            </p>
          </div>
          <button
            type="button"
            disabled={submitting}
            onClick={onClose}
            aria-label="Đóng"
            className="rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="rounded border border-[#E59CB4] bg-[#FDF0F4] dark:bg-[#E59CB4]/10 px-3 py-2 text-xs text-[#9B3558] dark:text-[#F1B4C8]">
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">
              Tên hiển thị
            </label>
            <input
              type="text"
              maxLength={128}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="noka-input"
              placeholder="Nguyễn Văn A"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">
              Tên đăng nhập (username)
            </label>
            <input
              type="text"
              required
              minLength={3}
              maxLength={64}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="noka-input font-mono"
              placeholder="student01"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">
                Vai trò
              </label>
              <select
                value={role}
                disabled={isSelf}
                onChange={(e) => setRole(e.target.value as Role)}
                className="noka-input disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <option value="student">Student (Học sinh)</option>
                <option value="teacher">Teacher (Giáo viên)</option>
                <option value="admin">Admin (Quản trị viên)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">
                Trạng thái tài khoản
              </label>
              <select
                value={isActive ? 'active' : 'locked'}
                disabled={isSelf}
                onChange={(e) => setIsActive(e.target.value === 'active')}
                className="noka-input disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <option value="active">Đang hoạt động</option>
                <option value="locked">Đã khóa (Vô hiệu hóa)</option>
              </select>
            </div>
          </div>

          {isSelf && (
            <p className="text-[11px] text-amber-700 dark:text-amber-400">
              Hệ thống khóa quyền tự hạ vai trò và tự vô hiệu hóa tài khoản Admin đang đăng nhập.
            </p>
          )}

          <div className="rounded-md border border-zinc-200 dark:border-zinc-800 bg-zinc-50/70 dark:bg-[#101318] p-3.5 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <label className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-700 dark:text-zinc-300">
                <KeyRound className="h-3.5 w-3.5 text-[#2A5C99] dark:text-[#89B4E8]" />
                Đặt lại mật khẩu mới (tùy chọn)
              </label>
              {newPassword && (
                <button
                  type="button"
                  onClick={handleCopyPassword}
                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-zinc-600 hover:bg-zinc-200/70 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  title="Sao chép mật khẩu mới"
                >
                  {copiedPw ? (
                    <>
                      <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400" /> Đã chép
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" /> Sao chép
                    </>
                  )}
                </button>
              )}
            </div>
            <PasswordInput
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Để trống nếu giữ nguyên mật khẩu hiện tại"
            />
            <p className="text-[11px] text-zinc-500">
              Tối thiểu 6 ký tự. Bấm biểu tượng con mắt để xem rõ mật khẩu mới trước khi bấm Lưu và gửi lại cho người dùng.
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              disabled={submitting}
              onClick={onClose}
              className="noka-btn-secondary"
            >
              Hủy
            </button>
            <button type="submit" disabled={submitting} className="noka-btn-primary">
              <Save className="h-4 w-4" />
              {submitting ? 'Đang lưu...' : 'Lưu thay đổi'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
