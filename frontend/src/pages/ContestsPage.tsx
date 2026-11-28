import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Copy,
  Eye,
  EyeOff,
  Lock,
  Pencil,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Trophy,
  Unlock,
} from 'lucide-react';
import { api, clearApiCache } from '../services/api';
import { useApp } from '../stores/AppContext';
import { ContestItem } from '../types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ContestProblemPicker, PickedProblem } from '../components/ContestProblemPicker';
import { ContestAccessPanel } from '../components/ContestAccessPanel';
import {
  ContestInitialAccessPicker,
  InitialContestAccess,
} from '../components/ContestInitialAccessPicker';
import { ContestCountdown } from '../components/ContestCountdown';

/** Format a Date or ISO string to local `YYYY-MM-DDTHH:mm` for datetime-local inputs. */
function toDateTimeLocal(input: Date | string): string {
  const d = input instanceof Date ? input : new Date(input);
  if (isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Copy text reliably on both HTTPS/localhost and plain-HTTP LAN addresses. */
async function copyToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // fall through to textarea fallback
    }
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

export const ContestsPage: React.FC = () => {
  const { isStaff, toast } = useApp();
  const [items, setItems] = useState<ContestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    title: '',
    description: '',
    start_time: toDateTimeLocal(new Date()),
    end_time: toDateTimeLocal(new Date(Date.now() + 2 * 3600 * 1000)),
    penalty_minutes: 20,
    freeze_before_end_minutes: 0,
    block_old_code: true,
  });
  const [pickedProblems, setPickedProblems] = useState<PickedProblem[]>([]);
  const [initialAccess, setInitialAccess] = useState<InitialContestAccess>({
    mode: 'public',
    classrooms: [],
    users: [],
  });
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ContestItem | null>(null);

  const load = () => {
    setLoading(true);
    api.listContests().then((r) => setItems(r.items || [])).finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const title = form.title.trim();
    if (title.length < 2) {
      toast('Tên kỳ thi phải có ít nhất 2 ký tự.', 'error');
      return;
    }
    const start = new Date(form.start_time);
    const end = new Date(form.end_time);
    if (isNaN(start.getTime()) || isNaN(end.getTime())) {
      toast('Thời gian bắt đầu/kết thúc không hợp lệ.', 'error');
      return;
    }
    if (end <= start) {
      toast('Thời gian kết thúc phải sau thời gian bắt đầu.', 'error');
      return;
    }
    if (
      initialAccess.mode === 'restricted' &&
      initialAccess.users.length === 0 &&
      initialAccess.classrooms.length === 0
    ) {
      toast('Vui lòng chọn ít nhất 1 học sinh hoặc 1 lớp học, hoặc chọn chế độ Công khai.', 'error');
      return;
    }
    const toInt = (v: number, min: number, max: number, fallback: number) => {
      const n = Math.trunc(Number(v));
      return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
    };
    setSaving(true);
    try {
      const probs = pickedProblems.map((p, idx) => ({
        problem_id: p.id,
        label: String.fromCharCode(65 + idx),
        points: 100,
      }));
      await api.createContest({
        title,
        description: form.description,
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        penalty_minutes: toInt(form.penalty_minutes, 0, 120, 20),
        freeze_before_end_minutes: toInt(form.freeze_before_end_minutes, 0, 300, 0),
        block_old_code: form.block_old_code,
        problems: probs,
        allowed_user_ids: initialAccess.mode === 'restricted' ? initialAccess.users.map((u) => u.id) : [],
        allowed_classroom_ids:
          initialAccess.mode === 'restricted' ? initialAccess.classrooms.map((c) => c.id) : [],
      });
      toast('Đã tạo kỳ thi mới.', 'success');
      setShowCreate(false);
      setPickedProblems([]);
      setInitialAccess({ mode: 'public', classrooms: [], users: [] });
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleCopyLink = async (contestId: number) => {
    const url = `${window.location.origin}/contests/${contestId}`;
    const ok = await copyToClipboard(url);
    toast(ok ? `Đã sao chép link: ${url}` : `Không thể tự sao chép. Link: ${url}`, ok ? 'success' : 'warning');
  };

  const handleToggleHidden = async (c: ContestItem) => {
    try {
      const nextHidden = !c.is_hidden;
      await api.updateContest(c.id, { is_hidden: nextHidden });
      toast(nextHidden ? 'Đã ẩn kỳ thi.' : 'Đã hiện kỳ thi.', 'success');
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.deleteContest(deleteTarget.id);
      toast('Đã xóa kỳ thi.', 'success');
      setDeleteTarget(null);
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Kỳ thi (Contests)</h1>
        {isStaff && (
          <button onClick={() => setShowCreate((v) => !v)} className="noka-btn-primary">
            <Plus className="h-4 w-4" /> Tạo kỳ thi
          </button>
        )}
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="noka-section p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-zinc-500 mb-1">Tên kỳ thi</label>
            <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="noka-input" />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Bắt đầu</label>
            <input type="datetime-local" required value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} className="noka-input" />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Kết thúc</label>
            <input type="datetime-local" required value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} className="noka-input" />
          </div>
          <div className="grid grid-cols-2 gap-2 md:col-span-2">
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Penalty (phút)</label>
              <input type="number" min={0} max={120} value={form.penalty_minutes} onChange={(e) => setForm({ ...form, penalty_minutes: Number(e.target.value) })} className="noka-input" />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Đóng băng BXH (phút cuối)</label>
              <input type="number" min={0} max={300} value={form.freeze_before_end_minutes} onChange={(e) => setForm({ ...form, freeze_before_end_minutes: Number(e.target.value) })} className="noka-input" />
            </div>
          </div>
          <div className="md:col-span-2">
            <label className="inline-flex items-center gap-2 text-xs font-medium text-zinc-700 dark:text-zinc-300 cursor-pointer">
              <input
                type="checkbox"
                checked={form.block_old_code}
                onChange={(e) => setForm({ ...form, block_old_code: e.target.checked })}
                className="rounded border-zinc-300 dark:border-zinc-700"
              />
              Chặn học sinh xem lại code cũ trong lúc đang tham gia kỳ thi
            </label>
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-zinc-500 mb-1">Bài tập (click để chọn, thứ tự A, B, C...)</label>
            <ContestProblemPicker value={pickedProblems} onChange={setPickedProblems} />
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-zinc-500 mb-1">Đối tượng tham gia</label>
            <ContestInitialAccessPicker value={initialAccess} onChange={setInitialAccess} />
          </div>
          <div className="md:col-span-2 flex justify-end gap-2">
            <button type="button" onClick={() => setShowCreate(false)} className="noka-btn-secondary">Hủy</button>
            <button type="submit" disabled={saving} className="noka-btn-primary">{saving ? 'Đang lưu...' : 'Lưu kỳ thi'}</button>
          </div>
        </form>
      )}

      <div className="noka-section overflow-x-auto">
        {loading ? (
          <div className="p-8 text-center text-sm text-zinc-500">Đang tải...</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-sm text-zinc-500">Chưa có kỳ thi nào.</div>
        ) : (
          <table className="noka-table">
            <thead>
              <tr>
                <th>Tên kỳ thi</th>
                <th>Trạng thái</th>
                <th>Thời gian</th>
                <th className="text-right">Thí sinh</th>
                <th className="text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className={c.is_hidden ? 'opacity-65' : ''}>
                  <td className="font-medium">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Link to={`/contests/${c.id}`} className="hover:text-[#2A5C99] dark:hover:text-[#89B4E8]">
                        {c.title}
                      </Link>
                      {c.is_hidden && (
                        <span className="rounded bg-zinc-200 dark:bg-zinc-800 px-1.5 py-0.5 text-[11px] font-normal text-zinc-600 dark:text-zinc-300">
                          Đang ẩn
                        </span>
                      )}
                      {c.is_restricted && (
                        <span className="rounded bg-[#2A5C99]/10 dark:bg-[#89B4E8]/15 px-1.5 py-0.5 text-[11px] font-normal text-[#2A5C99] dark:text-[#89B4E8]">
                          Giới hạn
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className="rounded border border-zinc-200 dark:border-zinc-700 px-2 py-0.5 font-mono text-xs">
                      {c.status}
                    </span>
                  </td>
                  <td className="font-mono text-xs text-zinc-500">
                    {new Date(c.start_time).toLocaleString()} → {new Date(c.end_time).toLocaleString()}
                  </td>
                  <td className="text-right font-mono text-xs">{c.participant_count}</td>
                  <td className="text-right">
                    <div className="inline-flex items-center justify-end gap-2">
                      {isStaff && (
                        <>
                          <button
                            type="button"
                            onClick={() => handleCopyLink(c.id)}
                            className="p-1 text-zinc-500 hover:text-[#2A5C99] dark:hover:text-[#89B4E8]"
                            title="Copy link kỳ thi"
                          >
                            <Copy className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleToggleHidden(c)}
                            className="p-1 text-zinc-500 hover:text-[#2A5C99] dark:hover:text-[#89B4E8]"
                            title={c.is_hidden ? 'Hiện kỳ thi' : 'Ẩn kỳ thi'}
                          >
                            {c.is_hidden ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget(c)}
                            className="p-1 text-zinc-500 hover:text-red-600"
                            title="Xóa kỳ thi"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </>
                      )}
                      <Link to={`/contests/${c.id}`} className="text-xs font-medium text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
                        Chi tiết
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Xóa kỳ thi?"
        description={`Bạn có chắc muốn xóa kỳ thi "${deleteTarget?.title || ''}"? Kỳ thi sẽ không còn hiển thị với học sinh và giáo viên.`}
        confirmLabel="Xóa kỳ thi"
        danger
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
};

export const ContestDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user, isStaff, toast } = useApp();
  const [contest, setContest] = useState<any>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [board, setBoard] = useState<any>(null);
  const [refreshingBoard, setRefreshingBoard] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editForm, setEditForm] = useState({
    title: '',
    start_time: '',
    end_time: '',
    penalty_minutes: 20,
    freeze_before_end_minutes: 0,
    block_old_code: true,
  });
  const [editProblems, setEditProblems] = useState<PickedProblem[]>([]);

  const initialTab = searchParams.get('tab');
  const [tab, setTab] = useState<'problems' | 'scoreboard' | 'access'>(
    initialTab === 'scoreboard' ? 'scoreboard' : initialTab === 'access' ? 'access' : 'problems'
  );

  const loadScoreboard = () => {
    if (!id) return;
    setRefreshingBoard(true);
    api
      .getScoreboard(id)
      .then(setBoard)
      .catch(() => {})
      .finally(() => setRefreshingBoard(false));
  };

  const load = () => {
    if (!id) return;
    setLoadError(null);
    api
      .getContest(id)
      .then(setContest)
      .catch((e) => {
        setContest(null);
        setLoadError(e.message || 'Không thể tải kỳ thi.');
      });
    loadScoreboard();
  };

  useEffect(() => {
    load();
  }, [id]);

  const switchTab = (next: 'problems' | 'scoreboard' | 'access') => {
    setTab(next);
    if (next === 'problems') setSearchParams({}, { replace: true });
    else setSearchParams({ tab: next }, { replace: true });
    if (next === 'scoreboard') loadScoreboard();
  };

  const handleRegister = async () => {
    if (!id) return;
    try {
      await api.registerContest(id);
      toast('Đăng ký tham gia kỳ thi thành công.', 'success');
      load();
    } catch (e: any) {
      toast(e.message, 'error');
    }
  };

  const handleCopyLink = async () => {
    if (!id) return;
    const url = `${window.location.origin}/contests/${id}`;
    const ok = await copyToClipboard(url);
    toast(ok ? `Đã sao chép link: ${url}` : `Không thể tự sao chép. Link: ${url}`, ok ? 'success' : 'warning');
  };

  const handleToggleHidden = async () => {
    if (!id || !contest) return;
    try {
      const nextHidden = !contest.is_hidden;
      await api.updateContest(id, { is_hidden: nextHidden });
      toast(nextHidden ? 'Đã ẩn kỳ thi.' : 'Đã hiện kỳ thi.', 'success');
      load();
    } catch (e: any) {
      toast(e.message, 'error');
    }
  };

  const handleToggleBlockOldCode = async () => {
    if (!id || !contest) return;
    try {
      const nextBlock = !contest.block_old_code;
      await api.updateContest(id, { block_old_code: nextBlock });
      toast(
        nextBlock ? 'Đã bật chặn xem lại code cũ khi đang thi.' : 'Đã tắt chặn xem lại code cũ.',
        'success'
      );
      load();
    } catch (e: any) {
      toast(e.message, 'error');
    }
  };

  const openEdit = () => {
    if (!contest) return;
    if (showEdit) {
      setShowEdit(false);
      return;
    }
    setEditForm({
      title: contest.title || '',
      start_time: toDateTimeLocal(contest.start_time),
      end_time: toDateTimeLocal(contest.end_time),
      penalty_minutes: Number(contest.penalty_minutes ?? 20),
      freeze_before_end_minutes: Number(contest.freeze_before_end_minutes ?? 0),
      block_old_code: Boolean(contest.block_old_code),
    });
    setEditProblems(
      (contest.problems || []).map((p: any) => ({
        id: p.id,
        code: p.code,
        title: p.title,
        difficulty: p.difficulty,
        visibility: p.visibility,
      }))
    );
    setShowEdit(true);
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    const title = editForm.title.trim();
    if (title.length < 2) {
      toast('Tên kỳ thi phải có ít nhất 2 ký tự.', 'error');
      return;
    }
    const start = new Date(editForm.start_time);
    const end = new Date(editForm.end_time);
    if (isNaN(start.getTime()) || isNaN(end.getTime())) {
      toast('Thời gian bắt đầu/kết thúc không hợp lệ.', 'error');
      return;
    }
    if (end <= start) {
      toast('Thời gian kết thúc phải sau thời gian bắt đầu.', 'error');
      return;
    }
    const toInt = (v: number, min: number, max: number, fallback: number) => {
      const n = Math.trunc(Number(v));
      return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
    };
    setSavingEdit(true);
    try {
      const existingPts = new Map<number, number>(
        (contest?.problems || []).map((p: any) => [Number(p.id), Number(p.points || 100)])
      );
      await api.updateContest(id, {
        title,
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        penalty_minutes: toInt(editForm.penalty_minutes, 0, 120, 20),
        freeze_before_end_minutes: toInt(editForm.freeze_before_end_minutes, 0, 300, 0),
        block_old_code: editForm.block_old_code,
        problems: editProblems.map((p, idx) => ({
          problem_id: p.id,
          label: String.fromCharCode(65 + idx),
          points: existingPts.get(p.id) ?? 100,
        })),
      });
      toast('Đã cập nhật kỳ thi.', 'success');
      setShowEdit(false);
      load();
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDelete = async () => {
    if (!id) return;
    try {
      await api.deleteContest(id);
      toast('Đã xóa kỳ thi.', 'success');
      navigate('/contests');
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setConfirmDelete(false);
    }
  };

  if (loadError) {
    return (
      <div className="noka-section p-8 text-center space-y-3">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">{loadError}</p>
        <div className="flex justify-center gap-2">
          {!user && (
            <Link to="/login" className="noka-btn-primary text-xs">
              Đăng nhập
            </Link>
          )}
          <Link to="/contests" className="noka-btn-secondary text-xs">
            Quay lại danh sách kỳ thi
          </Link>
        </div>
      </div>
    );
  }

  if (!contest) return <div className="py-12 text-center text-sm text-zinc-500">Đang tải kỳ thi...</div>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-200 dark:border-zinc-800 pb-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Trophy className="h-4 w-4 text-[#2A5C99] dark:text-[#89B4E8]" />
            <span className="font-mono text-xs text-zinc-500">{contest.status}</span>
            {contest.is_hidden && (
              <span className="rounded bg-zinc-200 dark:bg-zinc-800 px-1.5 py-0.5 text-[11px] text-zinc-600 dark:text-zinc-300">
                Đang ẩn
              </span>
            )}
            {contest.is_restricted && (
              <span className="rounded bg-[#2A5C99]/10 dark:bg-[#89B4E8]/15 px-1.5 py-0.5 text-[11px] text-[#2A5C99] dark:text-[#89B4E8]">
                Giới hạn thí sinh
              </span>
            )}
            {contest.block_old_code && (
              <span className="rounded bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 text-[11px] text-amber-800 dark:text-amber-300">
                Khóa xem code cũ
              </span>
            )}
          </div>
          <h1 className="mt-1 text-xl font-semibold">{contest.title}</h1>
          <p className="mt-1 font-mono text-xs text-zinc-500">
            {new Date(contest.start_time).toLocaleString()} → {new Date(contest.end_time).toLocaleString()}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isStaff && (
            <>
              <button type="button" onClick={openEdit} className="noka-btn-secondary text-xs">
                <Pencil className="h-3.5 w-3.5" /> {showEdit ? 'Đóng sửa' : 'Chỉnh sửa'}
              </button>
              <button
                type="button"
                onClick={handleToggleBlockOldCode}
                className="noka-btn-secondary text-xs"
                title="Bật/tắt chặn học sinh xem lại code cũ trong lúc đang thi"
              >
                {contest.block_old_code ? (
                  <>
                    <Lock className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" /> Khóa code cũ: Bật
                  </>
                ) : (
                  <>
                    <Unlock className="h-3.5 w-3.5" /> Khóa code cũ: Tắt
                  </>
                )}
              </button>
              <button type="button" onClick={handleCopyLink} className="noka-btn-secondary text-xs">
                <Copy className="h-3.5 w-3.5" /> Copy link
              </button>
              <button type="button" onClick={handleToggleHidden} className="noka-btn-secondary text-xs">
                {contest.is_hidden ? (
                  <>
                    <Eye className="h-3.5 w-3.5" /> Hiện
                  </>
                ) : (
                  <>
                    <EyeOff className="h-3.5 w-3.5" /> Ẩn
                  </>
                )}
              </button>
              <button type="button" onClick={() => setConfirmDelete(true)} className="noka-btn-danger text-xs">
                <Trash2 className="h-3.5 w-3.5" /> Xóa
              </button>
            </>
          )}
          {user && !contest.is_registered && (
            <button onClick={handleRegister} className="noka-btn-primary">
              Đăng ký tham gia
            </button>
          )}
        </div>
      </div>

      {isStaff && showEdit && (
        <form onSubmit={handleSaveEdit} className="noka-section p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="md:col-span-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Chỉnh sửa kỳ thi (áp dụng ngay kể cả khi đang diễn ra)</h2>
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-zinc-500 mb-1">Tên kỳ thi</label>
            <input
              required
              value={editForm.title}
              onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
              className="noka-input"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Bắt đầu</label>
            <input
              type="datetime-local"
              required
              value={editForm.start_time}
              onChange={(e) => setEditForm({ ...editForm, start_time: e.target.value })}
              className="noka-input"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1">Kết thúc</label>
            <input
              type="datetime-local"
              required
              value={editForm.end_time}
              onChange={(e) => setEditForm({ ...editForm, end_time: e.target.value })}
              className="noka-input"
            />
          </div>
          <div className="grid grid-cols-2 gap-2 md:col-span-2">
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Penalty (phút)</label>
              <input
                type="number"
                min={0}
                max={120}
                value={editForm.penalty_minutes}
                onChange={(e) => setEditForm({ ...editForm, penalty_minutes: Number(e.target.value) })}
                className="noka-input"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Đóng băng BXH (phút cuối)</label>
              <input
                type="number"
                min={0}
                max={300}
                value={editForm.freeze_before_end_minutes}
                onChange={(e) =>
                  setEditForm({ ...editForm, freeze_before_end_minutes: Number(e.target.value) })
                }
                className="noka-input"
              />
            </div>
          </div>
          <div className="md:col-span-2">
            <label className="inline-flex items-center gap-2 text-xs font-medium text-zinc-700 dark:text-zinc-300 cursor-pointer">
              <input
                type="checkbox"
                checked={editForm.block_old_code}
                onChange={(e) => setEditForm({ ...editForm, block_old_code: e.target.checked })}
                className="rounded border-zinc-300 dark:border-zinc-700"
              />
              Chặn học sinh xem lại code cũ trong lúc đang tham gia kỳ thi
            </label>
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-zinc-500 mb-1">
              Danh sách bài tập (thêm, xóa hoặc đổi thứ tự A, B, C...)
            </label>
            <ContestProblemPicker value={editProblems} onChange={setEditProblems} />
          </div>
          <div className="md:col-span-2 flex justify-end gap-2">
            <button type="button" onClick={() => setShowEdit(false)} className="noka-btn-secondary">
              Hủy
            </button>
            <button type="submit" disabled={savingEdit} className="noka-btn-primary">
              {savingEdit ? 'Đang lưu...' : 'Lưu thay đổi'}
            </button>
          </div>
        </form>
      )}

      {contest.status === 'UPCOMING' && (
        <ContestCountdown
          startTime={contest.start_time}
          serverTime={contest.server_time}
          isRegistered={Boolean(contest.is_registered)}
          isStaff={isStaff}
          isLoggedIn={Boolean(user)}
          onRegister={handleRegister}
          onStarted={() => {
            clearApiCache('/contests/');
            load();
          }}
        />
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex gap-2">
          <button
            onClick={() => switchTab('problems')}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === 'problems' ? 'border-[#2A5C99] dark:border-[#89B4E8] text-zinc-900 dark:text-zinc-100' : 'border-transparent text-zinc-500'
            }`}
          >
            Danh sách bài ({contest.problems?.length || 0})
          </button>
          <button
            onClick={() => switchTab('scoreboard')}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px ${
              tab === 'scoreboard' ? 'border-[#2A5C99] dark:border-[#89B4E8] text-zinc-900 dark:text-zinc-100' : 'border-transparent text-zinc-500'
            }`}
          >
            Bảng xếp hạng {board?.frozen && <Lock className="inline h-3.5 w-3.5 ml-1" />}
          </button>
          {isStaff && (
            <button
              onClick={() => switchTab('access')}
              className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px inline-flex items-center gap-1.5 ${
                tab === 'access' ? 'border-[#2A5C99] dark:border-[#89B4E8] text-zinc-900 dark:text-zinc-100' : 'border-transparent text-zinc-500'
              }`}
            >
              <ShieldCheck className="h-3.5 w-3.5" /> Thí sinh & Lớp học
            </button>
          )}
        </div>
        {tab === 'scoreboard' && (
          <button
            type="button"
            onClick={loadScoreboard}
            disabled={refreshingBoard}
            className="noka-btn-secondary text-xs mb-1.5"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshingBoard ? 'animate-spin' : ''}`} /> Làm mới
          </button>
        )}
      </div>

      {tab === 'problems' ? (
        <div className="noka-section overflow-hidden">
          <table className="noka-table">
            <thead>
              <tr>
                <th className="w-16">Bài</th>
                <th>Tên bài</th>
                <th className="text-right">Điểm</th>
                <th className="text-right">Giới hạn</th>
              </tr>
            </thead>
            <tbody>
              {(contest.problems || []).length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-sm text-zinc-500">
                    {contest.status === 'UPCOMING' && !isStaff
                      ? 'Danh sách bài sẽ hiển thị khi kỳ thi bắt đầu.'
                      : 'Chưa có bài tập nào trong kỳ thi.'}
                  </td>
                </tr>
              ) : (
                (contest.problems || []).map((p: any) => (
                  <tr key={p.id}>
                    <td className="font-mono font-semibold">{p.label}</td>
                    <td>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Link
                          to={`/problems/${p.code}?contest_id=${contest.id}`}
                          onMouseEnter={() => api.prefetchProblem(p.code, contest.id)}
                          className="font-medium hover:text-[#2A5C99] dark:hover:text-[#89B4E8]"
                        >
                          {p.title}
                        </Link>
                        {isStaff && p.visibility === 'hidden' && (
                          <span className="rounded bg-zinc-200 dark:bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-600 dark:text-zinc-300">
                            Ẩn
                          </span>
                        )}
                        {isStaff && p.visibility === 'private' && (
                          <span className="rounded bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:text-amber-300">
                            Chỉ định
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="text-right font-mono text-xs">{p.points}</td>
                    <td className="text-right font-mono text-xs text-zinc-500">
                      {p.time_limit_ms}ms / {p.memory_limit_mb}MB
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : tab === 'access' && isStaff ? (
        <ContestAccessPanel contestId={contest.id} onUpdated={load} />
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-end gap-2 text-xs text-zinc-500">
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-3.5 w-6 rounded-md bg-emerald-100 dark:bg-emerald-900/50 border border-emerald-300 dark:border-emerald-700" />
              First AC (giải đúng đầu tiên)
            </span>
          </div>
          <div className="noka-section overflow-x-auto">
          <table className="noka-table">
            <thead>
              <tr>
                <th className="w-14">#</th>
                <th>Thí sinh</th>
                <th className="text-right">AC</th>
                <th className="text-right">Tổng điểm</th>
                <th className="text-right">Penalty</th>
                {(board?.problems || []).map((p: any) => (
                  <th key={p.problem_id} className="text-center font-mono">
                    <div>{p.label}</div>
                    <div className="text-[10px] font-normal text-zinc-400">({p.points})</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(board?.standings || []).length === 0 ? (
                <tr>
                  <td colSpan={5 + (board?.problems?.length || 0)} className="py-8 text-center text-sm text-zinc-500">
                    Chưa có thí sinh nào tham gia hoặc nộp bài.
                  </td>
                </tr>
              ) : (
                (board?.standings || []).map((row: any) => {
                  const fullName = (row.full_name || '').trim();
                  const displayName = row.display_name || fullName || row.username;
                  return (
                    <tr key={row.user_id}>
                      <td className="font-mono text-xs">{row.rank}</td>
                      <td>
                        <div className="font-medium leading-tight">{displayName}</div>
                        {fullName && fullName !== row.username && (
                          <div className="font-mono text-[11px] text-zinc-400">@{row.username}</div>
                        )}
                      </td>
                      <td className="text-right font-mono font-semibold">{row.solved}</td>
                      <td className="text-right font-mono font-semibold">{row.total_score}</td>
                      <td className="text-right font-mono text-xs text-zinc-500">{row.penalty}</td>
                      {(board?.problems || []).map((p: any) => {
                        const cell = row.problems?.[String(p.problem_id)];
                        if (!cell) {
                          return (
                            <td key={p.problem_id} className="text-center font-mono text-xs text-zinc-300 dark:text-zinc-700">
                              —
                            </td>
                          );
                        }
                        if (cell.solved) {
                          if (cell.is_first_ac) {
                            return (
                              <td key={p.problem_id} className="text-center font-mono text-xs">
                                <div
                                  title="First AC (người giải đúng đầu tiên)"
                                  className="inline-flex flex-col items-center rounded-md bg-emerald-100 dark:bg-emerald-900/50 border border-emerald-300 dark:border-emerald-700/80 px-2.5 py-0.5"
                                >
                                  <span className="font-bold text-emerald-800 dark:text-emerald-200">
                                    {cell.score}
                                  </span>
                                  <span className="text-[10px] text-emerald-700/80 dark:text-emerald-300/80">
                                    {cell.attempts > 0 ? `+${cell.attempts} · ` : ''}
                                    {cell.time_min}m
                                  </span>
                                </div>
                              </td>
                            );
                          }
                          return (
                            <td key={p.problem_id} className="text-center font-mono text-xs">
                              <div className="font-semibold text-[#1F6F45] dark:text-[#98DFB5]">{cell.score}</div>
                              <div className="text-[10px] text-zinc-400">
                                {cell.attempts > 0 ? `+${cell.attempts} · ` : ''}
                                {cell.time_min}m
                              </div>
                            </td>
                          );
                        }
                        if (cell.submitted) {
                          return (
                            <td key={p.problem_id} className="text-center font-mono text-xs">
                              <div
                                className={
                                  cell.score > 0
                                    ? 'font-semibold text-amber-600 dark:text-amber-400'
                                    : 'font-medium text-[#9B3558] dark:text-[#F1B4C8]'
                                }
                              >
                                {cell.score}
                              </div>
                              {cell.attempts > 0 && (
                                <div className="text-[10px] text-zinc-400">-{cell.attempts}</div>
                              )}
                            </td>
                          );
                        }
                        if (cell.pending) {
                          return (
                            <td key={p.problem_id} className="text-center font-mono text-xs text-zinc-400">
                              ...
                            </td>
                          );
                        }
                        return (
                          <td key={p.problem_id} className="text-center font-mono text-xs text-zinc-300 dark:text-zinc-700">
                            —
                          </td>
                        );
                      })}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete}
        title="Xóa kỳ thi?"
        description={`Bạn có chắc muốn xóa kỳ thi "${contest.title}"? Hành động này sẽ ẩn kỳ thi khỏi toàn bộ hệ thống.`}
        confirmLabel="Xóa kỳ thi"
        danger
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
};
