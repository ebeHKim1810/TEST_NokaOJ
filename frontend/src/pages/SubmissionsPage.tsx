import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, Lock, RefreshCw, Trash2, X } from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { VerdictBadge } from '../components/StatusBadge';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ProblemSummary, SubmissionSummary } from '../types';

export const SubmissionsPage: React.FC = () => {
  const { user, isStaff, toast } = useApp();
  const [items, setItems] = useState<SubmissionSummary[]>([]);
  const [oldCodeBlocked, setOldCodeBlocked] = useState(false);
  const [blockingContests, setBlockingContests] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState('');
  const [debouncedUsername, setDebouncedUsername] = useState('');
  const [problemCode, setProblemCode] = useState('');
  const [debouncedProblemCode, setDebouncedProblemCode] = useState('');
  const [language, setLanguage] = useState('');
  const [verdict, setVerdict] = useState('');

  // Single deletion confirm dialog state
  const [deleteTarget, setDeleteTarget] = useState<SubmissionSummary | null>(null);
  const [deletingSingle, setDeletingSingle] = useState(false);

  // Admin/Teacher Bulk Delete modal state
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkMode, setBulkMode] = useState<'filtered' | 'all'>('filtered');
  const [bulkProblemCode, setBulkProblemCode] = useState('');
  const [bulkUsername, setBulkUsername] = useState('');
  const [bulkConfirmText, setBulkConfirmText] = useState('');
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [problemOptions, setProblemOptions] = useState<ProblemSummary[]>([]);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedUsername(username);
      setDebouncedProblemCode(problemCode);
    }, 200);
    return () => clearTimeout(t);
  }, [username, problemCode]);

  const load = () => {
    setLoading(true);
    api
      .listSubmissions({
        username: debouncedUsername,
        problem_code: debouncedProblemCode,
        language,
        verdict,
      })
      .then((res) => {
        setItems(res.items || []);
        setOldCodeBlocked(Boolean(res.old_code_blocked));
        setBlockingContests(res.blocking_contests || []);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [debouncedUsername, debouncedProblemCode, language, verdict]);

  const canDeleteRow = (s: SubmissionSummary) =>
    Boolean(isStaff || (user && Number(user.id) === Number(s.user_id)));

  const handleConfirmSingleDelete = async () => {
    if (!deleteTarget) return;
    setDeletingSingle(true);
    try {
      await api.deleteSubmission(deleteTarget.id);
      setItems((prev) => prev.filter((item) => item.id !== deleteTarget.id));
      toast(`Đã xóa vĩnh viễn bài nộp #${deleteTarget.id} khỏi PostgreSQL & Cloudflare R2.`, 'success');
      setDeleteTarget(null);
    } catch (err: any) {
      toast(err.message || 'Không thể xóa bài nộp.', 'error');
    } finally {
      setDeletingSingle(false);
    }
  };

  const openBulkModal = () => {
    setBulkMode(problemCode.trim() || username.trim() ? 'filtered' : 'filtered');
    setBulkProblemCode(problemCode.trim());
    setBulkUsername(username.trim());
    setBulkConfirmText('');
    setBulkOpen(true);
    if (problemOptions.length === 0) {
      api
        .listProblems({ page_size: 100 })
        .then((res) => setProblemOptions(res.items || []))
        .catch(() => {});
    }
  };

  const handleBulkDelete = async () => {
    if (bulkMode === 'filtered' && !bulkProblemCode.trim() && !bulkUsername.trim()) {
      toast('Vui lòng chọn ít nhất một bài tập hoặc nhập username cần xóa.', 'error');
      return;
    }
    if (bulkMode === 'all' && bulkConfirmText.trim().toUpperCase() !== 'XOA TAT CA') {
      toast('Vui lòng nhập chính xác "XOA TAT CA" để xác nhận xóa toàn bộ lịch sử.', 'error');
      return;
    }
    setBulkDeleting(true);
    try {
      const res = await api.bulkDeleteSubmissions(
        bulkMode === 'all'
          ? { delete_all: true }
          : {
              problem_code: bulkProblemCode.trim() || undefined,
              username: bulkUsername.trim() || undefined,
            }
      );
      toast(
        `Đã xóa vĩnh viễn ${res.deleted_count} bài nộp khỏi Neon PostgreSQL và Cloudflare R2.`,
        'success'
      );
      setBulkOpen(false);
      load();
    } catch (err: any) {
      toast(err.message || 'Lỗi khi xóa lịch sử nộp bài.', 'error');
    } finally {
      setBulkDeleting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">Lịch sử nộp bài</h1>
        <div className="flex items-center gap-2">
          {isStaff && (
            <button onClick={openBulkModal} className="noka-btn-danger text-xs">
              <Trash2 className="h-3.5 w-3.5" /> Xóa lịch sử nộp bài
            </button>
          )}
          <button onClick={load} className="noka-btn-secondary text-xs">
            <RefreshCw className="h-3.5 w-3.5" /> Làm mới
          </button>
        </div>
      </div>

      {oldCodeBlocked && (
        <div className="rounded-md border border-amber-300 dark:border-amber-800/70 bg-amber-50 dark:bg-amber-950/30 px-3.5 py-2.5 text-xs text-amber-900 dark:text-amber-200 flex items-center gap-2">
          <Lock className="h-4 w-4 shrink-0" />
          <span>
            Chức năng khóa xem lại code cũ đang bật trong kỳ thi
            {blockingContests.length > 0 ? ` (${blockingContests.join(', ')})` : ''}. Bạn chỉ có thể xem bài nộp thuộc kỳ thi hiện tại; toàn bộ bài nộp cũ đã được ẩn và khóa.
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2.5">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Lọc theo username..."
          className="noka-input"
        />
        <input
          value={problemCode}
          onChange={(e) => setProblemCode(e.target.value)}
          placeholder="Lọc theo mã bài (VD: NK0001)..."
          className="noka-input"
        />
        <select value={language} onChange={(e) => setLanguage(e.target.value)} className="noka-input">
          <option value="">Tất cả ngôn ngữ</option>
          <option value="cpp17">C++17</option>
          <option value="cpp20">C++20</option>
          <option value="python3">Python 3</option>
        </select>
        <select value={verdict} onChange={(e) => setVerdict(e.target.value)} className="noka-input">
          <option value="">Tất cả verdict</option>
          {['AC', 'WA', 'TLE', 'MLE', 'RE', 'CE', 'OLE', 'PENDING'].map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </div>

      <div className="noka-section overflow-x-auto">
        {loading ? (
          <div className="p-8 text-center text-sm text-zinc-500">Đang tải...</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-sm text-zinc-500">Chưa có bài nộp nào.</div>
        ) : (
          <table className="noka-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Người nộp</th>
                <th>Bài tập</th>
                <th>Ngôn ngữ</th>
                <th>Kết quả</th>
                <th className="text-right">Điểm</th>
                <th className="text-right">Thời gian</th>
                <th className="text-right">Bộ nhớ</th>
                <th className="text-right">Thời điểm</th>
                {user && <th className="w-12 text-right">Xóa</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id}>
                  <td className="font-mono text-xs">
                    {s.code_blocked ? (
                      <span
                        className="inline-flex items-center gap-1 text-zinc-400"
                        title="Không thể xem lại code cũ trong lúc đang tham gia kỳ thi"
                      >
                        <Lock className="h-3 w-3" /> #{s.id}
                      </span>
                    ) : (
                      <Link to={`/submissions/${s.id}`} className="text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
                        #{s.id}
                      </Link>
                    )}
                  </td>
                  <td className="font-medium">{s.username}</td>
                  <td>
                    <Link
                      to={
                        s.contest_id
                          ? `/problems/${s.problem_code}?contest_id=${s.contest_id}`
                          : `/problems/${s.problem_code}`
                      }
                      className="hover:underline"
                    >
                      <span className="font-mono text-xs text-zinc-500 mr-1.5">{s.problem_code}</span>
                      {s.problem_title}
                    </Link>
                  </td>
                  <td className="font-mono text-xs">{s.language}</td>
                  <td>
                    <VerdictBadge verdict={s.verdict} />
                  </td>
                  <td className="text-right font-mono text-xs">
                    {s.score}/{s.max_score}
                  </td>
                  <td className="text-right font-mono text-xs">{s.execution_time_ms} ms</td>
                  <td className="text-right font-mono text-xs">{s.memory_kb} KB</td>
                  <td className="text-right font-mono text-xs text-zinc-500">
                    {new Date(s.created_at).toLocaleString()}
                  </td>
                  {user && (
                    <td className="text-right">
                      {canDeleteRow(s) && (
                        <button
                          type="button"
                          onClick={() => setDeleteTarget(s)}
                          title="Xóa vĩnh viễn bài nộp này"
                          className="inline-flex items-center justify-center rounded p-1 text-zinc-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/40 dark:hover:text-rose-400"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Single Submission Delete Confirmation */}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={`Xóa vĩnh viễn bài nộp #${deleteTarget?.id ?? ''}?`}
        description={
          deleteTarget
            ? `Bài nộp #${deleteTarget.id} của ${deleteTarget.username} cho bài ${deleteTarget.problem_code} sẽ bị xóa vĩnh viễn khỏi Neon PostgreSQL và file mã nguồn trên Cloudflare R2. Hành động này không thể hoàn tác.`
            : ''
        }
        confirmLabel={deletingSingle ? 'Đang xóa...' : 'Xóa vĩnh viễn'}
        danger
        onConfirm={handleConfirmSingleDelete}
        onCancel={() => !deletingSingle && setDeleteTarget(null)}
      />

      {/* Admin / Teacher Bulk Delete Modal */}
      {bulkOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
          <div className="w-full max-w-lg rounded-md border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-[#14171D] p-5 shadow-lg space-y-4">
            <div className="flex items-start justify-between gap-3 border-b border-zinc-200 dark:border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-rose-600 dark:text-rose-400 shrink-0" />
                <div>
                  <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                    Xóa lịch sử nộp bài
                  </h2>
                  <p className="text-xs text-zinc-500">
                    Xóa vĩnh viễn cả dữ liệu trên Neon PostgreSQL và mã nguồn trên Cloudflare R2.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => !bulkDeleting && setBulkOpen(false)}
                className="rounded p-1 text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setBulkMode('filtered')}
                className={`rounded-md border px-3 py-2 text-left text-xs font-medium transition-colors ${
                  bulkMode === 'filtered'
                    ? 'border-[#2A5C99] bg-[#2A5C99]/[0.07] text-[#2A5C99] dark:border-[#89B4E8] dark:bg-[#89B4E8]/15 dark:text-[#A7C8F0]'
                    : 'border-zinc-200 dark:border-zinc-800 text-zinc-600 dark:text-zinc-400'
                }`}
              >
                Xóa theo bài tập / học sinh
              </button>
              <button
                type="button"
                onClick={() => setBulkMode('all')}
                className={`rounded-md border px-3 py-2 text-left text-xs font-medium transition-colors ${
                  bulkMode === 'all'
                    ? 'border-rose-500 bg-rose-50 text-rose-700 dark:border-rose-700 dark:bg-rose-950/40 dark:text-rose-300'
                    : 'border-zinc-200 dark:border-zinc-800 text-zinc-600 dark:text-zinc-400'
                }`}
              >
                Xóa toàn bộ lịch sử
              </button>
            </div>

            {bulkMode === 'filtered' ? (
              <div className="space-y-3">
                <div>
                  <label className="noka-label">Chọn bài tập (hoặc để trống nếu lọc theo học sinh)</label>
                  <select
                    value={bulkProblemCode}
                    onChange={(e) => setBulkProblemCode(e.target.value)}
                    className="noka-input"
                  >
                    <option value="">-- Không lọc theo bài tập --</option>
                    {problemOptions.map((p) => (
                      <option key={p.id} value={p.code}>
                        {p.code} — {p.title}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="noka-label">Hoặc nhập mã bài cụ thể</label>
                  <input
                    value={bulkProblemCode}
                    onChange={(e) => setBulkProblemCode(e.target.value)}
                    placeholder="VD: NK0001"
                    className="noka-input font-mono text-xs"
                  />
                </div>
                <div>
                  <label className="noka-label">Username học sinh (tùy chọn)</label>
                  <input
                    value={bulkUsername}
                    onChange={(e) => setBulkUsername(e.target.value)}
                    placeholder="VD: hs01 (để trống để xóa tất cả học sinh của bài đã chọn)"
                    className="noka-input text-xs"
                  />
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="rounded-md border border-rose-300 dark:border-rose-800/70 bg-rose-50 dark:bg-rose-950/30 p-3 text-xs text-rose-800 dark:text-rose-200">
                  Cảnh báo: Thao tác này sẽ xóa <strong>toàn bộ</strong> lịch sử nộp bài của mọi học sinh trên toàn hệ thống (không thể khôi phục) để giải phóng dung lượng PostgreSQL & R2.
                </div>
                <div>
                  <label className="noka-label">
                    Nhập <span className="font-mono font-bold text-rose-600 dark:text-rose-400">XOA TAT CA</span> để xác nhận
                  </label>
                  <input
                    value={bulkConfirmText}
                    onChange={(e) => setBulkConfirmText(e.target.value)}
                    placeholder="XOA TAT CA"
                    className="noka-input font-mono text-xs"
                  />
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 border-t border-zinc-200 dark:border-zinc-800 pt-3">
              <button
                type="button"
                disabled={bulkDeleting}
                onClick={() => setBulkOpen(false)}
                className="noka-btn-secondary text-xs"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={bulkDeleting}
                onClick={handleBulkDelete}
                className="noka-btn-danger text-xs"
              >
                <Trash2 className="h-3.5 w-3.5" />
                {bulkDeleting ? 'Đang xóa...' : 'Xác nhận xóa vĩnh viễn'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export const SubmissionDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, isStaff, toast } = useApp();
  const [sub, setSub] = useState<any>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = () => {
    if (!id) return;
    setLoading(true);
    setErrorMsg(null);
    api
      .getSubmission(id)
      .then(setSub)
      .catch((err) => {
        setSub(null);
        setErrorMsg(err.message || 'Không có quyền hoặc không tìm thấy bài nộp.');
        toast(err.message, 'error');
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [id]);

  const handleRejudge = async () => {
    if (!sub) return;
    try {
      await api.rejudgeSubmission(sub.id);
      toast('Đã đưa bài nộp vào hàng đợi chấm lại.', 'info');
      setTimeout(load, 900);
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  const handleDelete = async () => {
    if (!sub) return;
    setDeleting(true);
    try {
      await api.deleteSubmission(sub.id);
      toast(`Đã xóa vĩnh viễn bài nộp #${sub.id}.`, 'success');
      navigate('/submissions');
    } catch (err: any) {
      toast(err.message || 'Không thể xóa bài nộp.', 'error');
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  if (loading) return <div className="py-12 text-center text-sm text-zinc-500">Đang tải...</div>;
  if (!sub) {
    return (
      <div className="noka-section p-8 text-center space-y-2">
        <Lock className="mx-auto h-6 w-6 text-zinc-400" />
        <div className="text-sm text-zinc-600 dark:text-zinc-300">
          {errorMsg || 'Không có quyền hoặc không tìm thấy bài nộp.'}
        </div>
      </div>
    );
  }

  const canDelete = Boolean(isStaff || (user && Number(user.id) === Number(sub.user_id)));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 dark:border-zinc-800 pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-semibold">Submission #{sub.id}</h1>
            <VerdictBadge verdict={sub.verdict} />
          </div>
          <p className="text-xs text-zinc-500 font-mono">
            {sub.username} ·{' '}
            <Link
              to={
                sub.contest_id
                  ? `/problems/${sub.problem_code}?contest_id=${sub.contest_id}`
                  : `/problems/${sub.problem_code}`
              }
              className="text-[#2A5C99] dark:text-[#89B4E8] hover:underline"
            >
              {sub.problem_code} ({sub.problem_title})
            </Link>{' '}
            · {sub.language} · {sub.score}/{sub.max_score} điểm · {sub.execution_time_ms} ms · {sub.memory_kb} KB
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isStaff && !sub.discarded_by_retention && (
            <button onClick={handleRejudge} className="noka-btn-secondary text-xs">
              <RefreshCw className="h-3.5 w-3.5" /> Chấm lại (Rejudge)
            </button>
          )}
          {canDelete && !sub.discarded_by_retention && (
            <button onClick={() => setConfirmDelete(true)} className="noka-btn-danger text-xs">
              <Trash2 className="h-3.5 w-3.5" /> Xóa bài nộp
            </button>
          )}
        </div>
      </div>

      {sub.compile_output && (
        <div className="noka-section p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[#9B3558] dark:text-[#F1B4C8] mb-2">
            Thông báo biên dịch (Compiler Output)
          </h2>
          <pre className="text-xs overflow-x-auto whitespace-pre-wrap text-zinc-700 dark:text-zinc-300">
            {sub.compile_output}
          </pre>
        </div>
      )}

      {sub.results && sub.results.length > 0 && (
        <div className="noka-section overflow-x-auto">
          <table className="noka-table text-xs">
            <thead>
              <tr>
                <th>Testcase</th>
                <th>Kết quả</th>
                <th className="text-right">Thời gian</th>
                <th className="text-right">Bộ nhớ</th>
                <th>Ghi chú</th>
              </tr>
            </thead>
            <tbody>
              {sub.results.map((r: any, idx: number) => (
                <tr key={r.id || idx}>
                  <td className="font-mono">{r.testcase_name || `Test #${idx + 1}`}</td>
                  <td>
                    <VerdictBadge verdict={r.verdict} />
                  </td>
                  <td className="text-right font-mono">{r.execution_time_ms} ms</td>
                  <td className="text-right font-mono">{r.memory_kb} KB</td>
                  <td className="text-zinc-500">{r.checker_message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="noka-section overflow-hidden">
        <div className="border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/70 dark:bg-[#15181E] px-3.5 py-2 text-xs font-semibold text-zinc-500">
          Mã nguồn ({sub.language})
        </div>
        <pre className="p-4 text-xs overflow-x-auto bg-white dark:bg-[#12151B]">
          <code>{sub.source_code}</code>
        </pre>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title={`Xóa vĩnh viễn bài nộp #${sub.id}?`}
        description="Bài nộp và file mã nguồn lưu trên Cloudflare R2 sẽ bị xóa hoàn toàn và không thể khôi phục."
        confirmLabel={deleting ? 'Đang xóa...' : 'Xóa vĩnh viễn'}
        danger
        onConfirm={handleDelete}
        onCancel={() => !deleting && setConfirmDelete(false)}
      />
    </div>
  );
};
