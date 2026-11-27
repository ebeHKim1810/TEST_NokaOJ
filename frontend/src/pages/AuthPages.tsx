import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PasswordInput } from '../components/PasswordInput';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';

export const LoginPage: React.FC = () => {
  const { loginWithToken, toast, siteName, allowRegistration } = useApp();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const res = await api.login(username.trim(), password);
      loginWithToken(res.access_token, res.user);
      toast(`Xin chào, ${res.user.username}.`, 'success');
      navigate('/');
    } catch (err: any) {
      setError(err.message || 'Đăng nhập thất bại.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-sm py-12">
      <div className="noka-section p-6 space-y-5">
        <div>
          <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Đăng nhập {siteName}</h1>
          <p className="mt-1 text-xs text-zinc-500">Nhập tên đăng nhập hoặc email của bạn.</p>
        </div>
        {error && (
          <div className="rounded border border-[#E59CB4] bg-[#FDF0F4] dark:bg-[#E59CB4]/10 px-3 py-2 text-xs text-[#9B3558] dark:text-[#F1B4C8]">
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">
              Tên đăng nhập / Email
            </label>
            <input
              type="text"
              required
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="noka-input"
              placeholder="student01"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">
              Mật khẩu
            </label>
            <PasswordInput
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Nhập mật khẩu"
            />
          </div>
          <button type="submit" disabled={submitting} className="noka-btn-primary w-full">
            {submitting ? 'Đang xác thực...' : 'Đăng nhập'}
          </button>
        </form>
        {allowRegistration && (
          <p className="text-center text-xs text-zinc-500">
            Chưa có tài khoản?{' '}
            <Link to="/register" className="text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
              Đăng ký
            </Link>
          </p>
        )}
      </div>
    </div>
  );
};

export const RegisterPage: React.FC = () => {
  const { loginWithToken, toast, siteName, allowRegistration, refreshPublicConfig } = useApp();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: '', email: '', full_name: '', password: '' });
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    refreshPublicConfig();
  }, [refreshPublicConfig]);

  if (!allowRegistration) {
    return (
      <div className="mx-auto max-w-sm py-12">
        <div className="noka-section p-6 space-y-4 text-center">
          <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Đăng ký đang tạm đóng</h1>
          <p className="text-xs text-zinc-500 leading-relaxed">
            Quản trị viên hiện đã tắt chức năng tự tạo tài khoản mới. Vui lòng liên hệ giáo viên hoặc quản trị viên để được cấp tài khoản.
          </p>
          <Link to="/login" className="noka-btn-primary w-full justify-center">
            Quay lại trang đăng nhập
          </Link>
        </div>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (form.password.length < 6) {
      setError('Mật khẩu phải có ít nhất 6 ký tự.');
      return;
    }
    if (form.password !== confirmPassword) {
      setError('Mật khẩu xác nhận không khớp.');
      return;
    }

    setSubmitting(true);
    try {
      const res = await api.register({
        username: form.username.trim(),
        email: form.email.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
      });
      loginWithToken(res.access_token, res.user);
      toast('Tạo tài khoản thành công.', 'success');
      navigate('/');
    } catch (err: any) {
      setError(err.message || 'Đăng ký thất bại.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-sm py-10">
      <div className="noka-section p-6 space-y-5">
        <div>
          <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Đăng ký tài khoản {siteName}</h1>
          <p className="mt-1 text-xs text-zinc-500">Tạo tài khoản học sinh để bắt đầu làm bài.</p>
        </div>
        {error && (
          <div className="rounded border border-[#E59CB4] bg-[#FDF0F4] dark:bg-[#E59CB4]/10 px-3 py-2 text-xs text-[#9B3558] dark:text-[#F1B4C8]">
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">Username</label>
            <input
              required
              minLength={3}
              autoComplete="username"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              className="noka-input"
              placeholder="nguyenvana"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">Họ và tên</label>
            <input
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              className="noka-input"
              placeholder="Nguyễn Văn A"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">Email</label>
            <input
              type="email"
              required
              autoComplete="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="noka-input"
              placeholder="student@example.com"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">Mật khẩu (≥ 6 ký tự)</label>
            <PasswordInput
              required
              minLength={6}
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="Tối thiểu 6 ký tự"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-1">Xác nhận mật khẩu</label>
            <PasswordInput
              required
              minLength={6}
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Nhập lại mật khẩu"
            />
          </div>
          <button type="submit" disabled={submitting} className="noka-btn-primary w-full">
            {submitting ? 'Đang tạo...' : 'Tạo tài khoản'}
          </button>
        </form>
        <p className="text-center text-xs text-zinc-500">
          Đã có tài khoản?{' '}
          <Link to="/login" className="text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
            Đăng nhập
          </Link>
        </p>
      </div>
    </div>
  );
};
