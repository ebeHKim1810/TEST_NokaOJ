import React, { useEffect, useState } from 'react';
import { GraduationCap, Plus, Search, ShieldCheck, UserPlus, Users, X } from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { ClassroomItem } from '../types';

interface AllowedUser {
  id: number;
  username: string;
  full_name: string;
  email: string;
}

interface AllowedClassroom {
  id: number;
  name: string;
  student_count: number;
}

interface AccessData {
  contest_id: number;
  is_restricted: boolean;
  users: AllowedUser[];
  classrooms: AllowedClassroom[];
}

interface Props {
  contestId: number | string;
  onUpdated?: () => void;
}

export const ContestAccessPanel: React.FC<Props> = ({ contestId, onUpdated }) => {
  const { toast } = useApp();
  const [access, setAccess] = useState<AccessData | null>(null);
  const [allClassrooms, setAllClassrooms] = useState<ClassroomItem[]>([]);
  const [userQuery, setUserQuery] = useState('');
  const [userResults, setUserResults] = useState<AllowedUser[]>([]);
  const [manualInput, setManualInput] = useState('');
  const [selectedClassroomId, setSelectedClassroomId] = useState<string>('');
  const [busy, setBusy] = useState(false);

  const loadAccess = () => {
    api
      .getContestAccess(contestId)
      .then(setAccess)
      .catch((e) => toast(e.message, 'error'));
  };

  useEffect(() => {
    loadAccess();
    api
      .listClassrooms()
      .then((r) => setAllClassrooms(r.items || []))
      .catch(() => {});
  }, [contestId]);

  useEffect(() => {
    const t = setTimeout(() => {
      api
        .listUsers(userQuery.trim())
        .then((r) => setUserResults(r.items || []))
        .catch(() => {});
    }, 200);
    return () => clearTimeout(t);
  }, [userQuery]);

  const applyUpdate = (next: AccessData) => {
    setAccess(next);
    onUpdated?.();
  };

  const handleAddUserById = async (uid: number) => {
    setBusy(true);
    try {
      const res = await api.addContestUsers(contestId, { user_ids: [uid] });
      applyUpdate(res);
      toast('Đã thêm học sinh vào kỳ thi.', 'success');
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleAddManualUsers = async (e: React.FormEvent) => {
    e.preventDefault();
    const tokens = manualInput
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (tokens.length === 0) return;
    setBusy(true);
    try {
      const res = await api.addContestUsers(contestId, { usernames: tokens });
      applyUpdate(res);
      setManualInput('');
      if (res.not_found?.length) {
        toast(`Đã thêm ${res.added || 0} tài khoản. Không tìm thấy: ${res.not_found.join(', ')}`, 'warning');
      } else {
        toast(`Đã thêm ${res.added || 0} tài khoản vào kỳ thi.`, 'success');
      }
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleRemoveUser = async (uid: number) => {
    setBusy(true);
    try {
      const res = await api.removeContestUser(contestId, uid);
      applyUpdate(res);
      toast('Đã xóa tài khoản khỏi danh sách được phép.', 'info');
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleAddClassroom = async () => {
    const cid = Number(selectedClassroomId);
    if (!cid) return;
    setBusy(true);
    try {
      const res = await api.addContestClassroom(contestId, cid);
      applyUpdate(res);
      setSelectedClassroomId('');
      toast('Đã thêm lớp học vào kỳ thi.', 'success');
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleRemoveClassroom = async (cid: number) => {
    setBusy(true);
    try {
      const res = await api.removeContestClassroom(contestId, cid);
      applyUpdate(res);
      toast('Đã gỡ lớp học khỏi kỳ thi.', 'info');
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  if (!access) {
    return <div className="p-6 text-center text-sm text-zinc-500">Đang tải danh sách quyền truy cập...</div>;
  }

  const allowedUserIds = new Set(access.users.map((u) => u.id));
  const allowedClassroomIds = new Set(access.classrooms.map((c) => c.id));
  const availableClassrooms = allClassrooms.filter((c) => !allowedClassroomIds.has(c.id));

  return (
    <div className="space-y-4">
      <div className="noka-section p-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-start gap-2.5">
          <ShieldCheck className="h-5 w-5 shrink-0 text-[#2A5C99] dark:text-[#89B4E8] mt-0.5" />
          <div className="text-sm">
            <div className="font-medium">
              Chế độ truy cập:{' '}
              {access.is_restricted ? (
                <span className="text-[#2A5C99] dark:text-[#89B4E8]">Chỉ thí sinh / lớp được chỉ định</span>
              ) : (
                <span className="text-[#1F6F45] dark:text-[#98DFB5]">Mở cho mọi tài khoản</span>
              )}
            </div>
            <p className="text-xs text-zinc-500 mt-0.5">
              {access.is_restricted
                ? 'Chỉ những học sinh được thêm bên dưới hoặc thuộc lớp học được chỉ định mới có thể xem và nộp bài trong kỳ thi này.'
                : 'Khi bạn thêm ít nhất 1 học sinh hoặc 1 lớp học bên dưới, kỳ thi sẽ tự động giới hạn chỉ cho các tài khoản đó.'}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Classrooms section */}
        <div className="noka-section p-4 space-y-3">
          <div className="flex items-center gap-2 font-medium text-sm">
            <GraduationCap className="h-4 w-4 text-[#2A5C99] dark:text-[#89B4E8]" />
            Lớp học được thêm ({access.classrooms.length})
          </div>
          <div className="flex gap-2">
            <select
              value={selectedClassroomId}
              onChange={(e) => setSelectedClassroomId(e.target.value)}
              className="noka-input flex-1"
            >
              <option value="">-- Chọn lớp học để thêm --</option>
              {availableClassrooms.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.student_count} học sinh)
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={!selectedClassroomId || busy}
              onClick={handleAddClassroom}
              className="noka-btn-primary shrink-0"
            >
              <Plus className="h-4 w-4" /> Thêm lớp
            </button>
          </div>
          {access.classrooms.length === 0 ? (
            <div className="rounded border border-dashed border-zinc-200 dark:border-zinc-800 p-4 text-center text-xs text-zinc-500">
              Chưa thêm lớp học nào.
            </div>
          ) : (
            <div className="divide-y divide-zinc-100 dark:divide-zinc-800 rounded border border-zinc-200 dark:border-zinc-800">
              {access.classrooms.map((cl) => (
                <div key={cl.id} className="flex items-center justify-between px-3 py-2 text-sm">
                  <div>
                    <div className="font-medium">{cl.name}</div>
                    <div className="text-xs text-zinc-500">{cl.student_count} học sinh</div>
                  </div>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleRemoveClassroom(cl.id)}
                    className="p-1 text-zinc-400 hover:text-red-600"
                    title="Gỡ lớp học"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Specific students section */}
        <div className="noka-section p-4 space-y-3">
          <div className="flex items-center gap-2 font-medium text-sm">
            <Users className="h-4 w-4 text-[#2A5C99] dark:text-[#89B4E8]" />
            Học sinh được chỉ định ({access.users.length})
          </div>

          <form onSubmit={handleAddManualUsers} className="flex gap-2">
            <input
              value={manualInput}
              onChange={(e) => setManualInput(e.target.value)}
              placeholder="Nhập username hoặc email (ngăn cách dấu phẩy)..."
              className="noka-input flex-1 text-sm"
            />
            <button type="submit" disabled={busy || !manualInput.trim()} className="noka-btn-primary shrink-0">
              <UserPlus className="h-4 w-4" /> Thêm
            </button>
          </form>

          <div>
            <div className="relative mb-1.5">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400" />
              <input
                value={userQuery}
                onChange={(e) => setUserQuery(e.target.value)}
                placeholder="Tìm tài khoản theo tên, username hoặc email để click thêm..."
                className="noka-input pl-8 text-xs"
              />
            </div>
            <div className="max-h-40 overflow-y-auto rounded border border-zinc-200 dark:border-zinc-800 divide-y divide-zinc-100 dark:divide-zinc-800">
              {userResults.length === 0 ? (
                <div className="p-2.5 text-center text-xs text-zinc-500">Không tìm thấy tài khoản.</div>
              ) : (
                userResults.map((u) => {
                  const already = allowedUserIds.has(u.id);
                  return (
                    <button
                      type="button"
                      key={u.id}
                      disabled={busy || already}
                      onClick={() => handleAddUserById(u.id)}
                      className="flex w-full items-center justify-between px-3 py-1.5 text-left text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800 disabled:opacity-50"
                    >
                      <span className="truncate">
                        <span className="font-medium">{u.full_name || u.username}</span>{' '}
                        <span className="font-mono text-zinc-500">@{u.username}</span>
                      </span>
                      <span className="shrink-0 text-[11px] text-[#2A5C99] dark:text-[#89B4E8]">
                        {already ? 'Đã thêm' : '+ Thêm'}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {access.users.length > 0 && (
            <div className="max-h-48 overflow-y-auto divide-y divide-zinc-100 dark:divide-zinc-800 rounded border border-zinc-200 dark:border-zinc-800">
              {access.users.map((u) => (
                <div key={u.id} className="flex items-center justify-between px-3 py-1.5 text-sm">
                  <div className="min-w-0">
                    <span className="font-medium">{u.full_name || u.username}</span>{' '}
                    <span className="font-mono text-xs text-zinc-500">@{u.username}</span>
                  </div>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleRemoveUser(u.id)}
                    className="p-1 text-zinc-400 hover:text-red-600 shrink-0"
                    title="Bỏ khỏi danh sách"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
