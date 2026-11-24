import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpDown,
  CheckCircle2,
  CircleDot,
  Plus,
  Save,
  Search,
  Settings2,
  Users,
  X,
} from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { DifficultyBadge, VisibilityBadge } from '../components/StatusBadge';
import { ProblemAccessPicker } from '../components/ProblemAccessPicker';
import {
  AllowedUserItem,
  ProblemSummary,
  SubmissionRetentionMode,
  Visibility,
} from '../types';

export const ProblemsetPage: React.FC = () => {
  const { isStaff, toast } = useApp();
  const [items, setItems] = useState<ProblemSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [tags, setTags] = useState<Array<{ id: number; name: string; slug: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [reloadTick, setReloadTick] = useState(0);

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [tag, setTag] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const [solvedStatus, setSolvedStatus] = useState('');
  const [visibility, setVisibility] = useState('');
  const [sortBy, setSortBy] = useState('code');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(1);
  const pageSize = 20;

  // Quick access & retention modal state (Admin/Teacher)
  const [accessModalProblem, setAccessModalProblem] = useState<ProblemSummary | null>(null);
  const [modalVisibility, setModalVisibility] = useState<Visibility>('public');
  const [modalRetention, setModalRetention] = useState<SubmissionRetentionMode>('latest');
  const [modalAllowedUsers, setModalAllowedUsers] = useState<AllowedUserItem[]>([]);
  const [loadingAccess, setLoadingAccess] = useState(false);
  const [savingAccess, setSavingAccess] = useState(false);
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 220);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    api.listTags().then((r) => setTags(r.items || [])).catch(() => {});
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .listProblems({
        search: debouncedSearch,
        tag,
        difficulty,
        solved_status: solvedStatus,
        visibility,
        sort_by: sortBy,
        sort_dir: sortDir,
        page,
        page_size: pageSize,
      })
      .then((res) => {
        if (!active) return;
        setItems(res.items || []);
        setTotal(res.total || 0);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [debouncedSearch, tag, difficulty, solvedStatus, visibility, sortBy, sortDir, page, reloadTick]);

  const toggleSort = (col: string) => {
    if (sortBy === col) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortBy(col);
      setSortDir('asc');
    }
  };

  const openAccessModal = async (p: ProblemSummary, presetVisibility?: Visibility) => {
    setAccessModalProblem(p);
    setModalVisibility(presetVisibility || p.visibility);
    setModalRetention((p.submission_retention_mode as SubmissionRetentionMode) || 'latest');
    setModalAllowedUsers([]);
    setLoadingAccess(true);
    try {
      const res = await api.getProblemAccess(p.id);
      setModalVisibility(presetVisibility || (res.visibility as Visibility) || p.visibility);
      setModalRetention((res.submission_retention_mode as SubmissionRetentionMode) || 'latest');
      setModalAllowedUsers(res.allowed_users || []);
    } catch (err: any) {
      toast(err.message || 'Không tải được cấu hình phân quyền.', 'error');
    } finally {
      setLoadingAccess(false);
    }
  };

  const handleQuickVisibilityChange = async (p: ProblemSummary, nextVis: Visibility) => {
    if (nextVis === p.visibility) return;
    if (nextVis === 'private') {
      openAccessModal(p, 'private');
      return;
    }
    setUpdatingId(p.id);
    try {
      await api.updateProblemAccess(p.id, { visibility: nextVis });
      setItems((prev) =>
        prev.map((item) => (item.id === p.id ? { ...item, visibility: nextVis } : item))
      );
      toast(
        `Đã chuyển ${p.code} sang chế độ ${
          nextVis === 'public' ? 'Public' : nextVis === 'hidden' ? 'Hidden' : nextVis
        }.`,
        'success'
      );
    } catch (err: any) {
      toast(err.message || 'Không thể cập nhật trạng thái hiển thị.', 'error');
    } finally {
      setUpdatingId(null);
    }
  };

  const handleSaveAccessModal = async () => {
    if (!accessModalProblem) return;
    setSavingAccess(true);
    try {
      const payload = {
        visibility: modalVisibility,
        submission_retention_mode: modalRetention,
        allowed_user_ids: modalAllowedUsers.map((u) => u.id),
      };
      const res = await api.updateProblemAccess(accessModalProblem.id, payload);
      setItems((prev) =>
        prev.map((item) =>
          item.id === accessModalProblem.id
            ? {
                ...item,
                visibility: (res.visibility as Visibility) || modalVisibility,
                submission_retention_mode:
                  (res.submission_retention_mode as SubmissionRetentionMode) || modalRetention,
                allowed_user_count: (res.allowed_users || modalAllowedUsers).length,
              }
            : item
        )
      );
      toast(`Đã lưu quyền truy cập & chế độ lưu bài cho ${accessModalProblem.code}.`, 'success');
      setAccessModalProblem(null);
      setReloadTick((t) => t + 1);
    } catch (err: any) {
      toast(err.message || 'Lỗi khi lưu cấu hình phân quyền.', 'error');
    } finally {
      setSavingAccess(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">Problemset</h1>
          <p className="text-xs text-zinc-500">{total} bài tập khả dụng</p>
        </div>
        {isStaff && (
          <Link to="/admin/problems/new" className="noka-btn-primary">
            <Plus className="h-4 w-4" /> Tạo bài tập mới
          </Link>
        )}
      </div>

      {/* Filter Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-2.5">
        <div className="relative lg:col-span-2">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-zinc-400" />
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Tìm theo tên hoặc mã bài..."
            className="noka-input pl-8"
          />
        </div>
        <select
          value={tag}
          onChange={(e) => {
            setTag(e.target.value);
            setPage(1);
          }}
          className="noka-input"
        >
          <option value="">Tất cả chủ đề</option>
          {tags.map((t) => (
            <option key={t.id} value={t.slug}>
              {t.name}
            </option>
          ))}
        </select>
        <select
          value={difficulty}
          onChange={(e) => {
            setDifficulty(e.target.value);
            setPage(1);
          }}
          className="noka-input"
        >
          <option value="">Mọi độ khó</option>
          <option value="easy">Easy</option>
          <option value="medium">Medium</option>
          <option value="hard">Hard</option>
        </select>
        <select
          value={solvedStatus}
          onChange={(e) => {
            setSolvedStatus(e.target.value);
            setPage(1);
          }}
          className="noka-input"
        >
          <option value="">Mọi trạng thái</option>
          <option value="solved">Đã giải</option>
          <option value="unsolved">Chưa giải</option>
        </select>
        <select
          value={visibility}
          onChange={(e) => {
            setVisibility(e.target.value);
            setPage(1);
          }}
          className="noka-input"
        >
          {isStaff ? (
            <>
              <option value="">Mọi hiển thị</option>
              <option value="public">Public (Công khai)</option>
              <option value="private">Private (Chỉ định)</option>
              <option value="hidden">Hidden (Ẩn)</option>
              <option value="classroom">Classroom</option>
            </>
          ) : (
            <>
              <option value="">Tất cả nguồn</option>
              <option value="public">Công khai</option>
              <option value="private">Chỉ định riêng</option>
              <option value="assigned">Được giao</option>
            </>
          )}
        </select>
      </div>

      {/* Problem Table */}
      <div className="noka-section overflow-x-auto">
        {loading ? (
          <div className="p-8 text-center text-sm text-zinc-500">Đang tải danh sách bài tập...</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-sm text-zinc-500">Không tìm thấy bài tập phù hợp bộ lọc.</div>
        ) : (
          <table className="noka-table">
            <thead>
              <tr>
                <th className="w-24 cursor-pointer" onClick={() => toggleSort('code')}>
                  <span className="inline-flex items-center gap-1">ID <ArrowUpDown className="h-3 w-3" /></span>
                </th>
                <th className="cursor-pointer" onClick={() => toggleSort('title')}>
                  <span className="inline-flex items-center gap-1">Tên bài <ArrowUpDown className="h-3 w-3" /></span>
                </th>
                <th>Chủ đề</th>
                <th className="cursor-pointer" onClick={() => toggleSort('difficulty')}>
                  <span className="inline-flex items-center gap-1">Độ khó <ArrowUpDown className="h-3 w-3" /></span>
                </th>
                {isStaff && <th>Hiển thị / Lưu bài</th>}
                <th className="text-right">Điểm</th>
                <th className="text-center">Trạng thái</th>
                <th className="text-right cursor-pointer" onClick={() => toggleSort('ac_rate')}>
                  <span className="inline-flex items-center gap-1 justify-end">AC <ArrowUpDown className="h-3 w-3" /></span>
                </th>
                <th className="text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id}>
                  <td className="font-mono text-xs text-zinc-500">{p.code}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <Link
                        to={`/problems/${p.code}`}
                        onMouseEnter={() => api.prefetchProblem(p.code)}
                        className="font-medium text-zinc-900 dark:text-zinc-100 hover:text-[#2A5C99] dark:hover:text-[#89B4E8]"
                      >
                        {p.title}
                      </Link>
                      {!isStaff && p.visibility === 'private' && (
                        <VisibilityBadge visibility="private" />
                      )}
                    </div>
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {p.tags.slice(0, 3).map((t) => (
                        <span
                          key={t}
                          className="rounded bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 text-[11px] text-zinc-600 dark:text-zinc-400"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <DifficultyBadge difficulty={p.difficulty} />
                  </td>
                  {isStaff && (
                    <td>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <VisibilityBadge
                          visibility={p.visibility}
                          allowedCount={p.allowed_user_count}
                        />
                        <select
                          aria-label={`Đổi hiển thị ${p.code}`}
                          disabled={updatingId === p.id}
                          value={p.visibility}
                          onChange={(e) =>
                            handleQuickVisibilityChange(p, e.target.value as Visibility)
                          }
                          className="rounded border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-1.5 py-0.5 text-[11px] text-zinc-700 dark:text-zinc-300 focus:outline-none focus:border-[#2A5C99]"
                        >
                          <option value="public">Public</option>
                          <option value="private">Private</option>
                          <option value="hidden">Hidden</option>
                          {p.visibility === 'classroom' && (
                            <option value="classroom">Classroom</option>
                          )}
                        </select>
                        <button
                          type="button"
                          onClick={() => openAccessModal(p)}
                          title="Cấu hình danh sách học sinh Private & chế độ lưu bài nộp"
                          className="inline-flex items-center gap-1 rounded border border-zinc-200 dark:border-zinc-700 px-1.5 py-0.5 text-[11px] text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                        >
                          {p.visibility === 'private' ? (
                            <>
                              <Users className="h-3 w-3" /> HS
                            </>
                          ) : (
                            <Settings2 className="h-3 w-3" />
                          )}
                        </button>
                        <span
                          title={
                            p.submission_retention_mode === 'best'
                              ? 'Chính sách lưu bài: giữ lần điểm cao nhất'
                              : 'Chính sách lưu bài: giữ lần nộp mới nhất'
                          }
                          className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                            p.submission_retention_mode === 'best'
                              ? 'bg-[#EBF3FC] text-[#2A5C99] dark:bg-[#89B4E8]/15 dark:text-[#A7C8F0]'
                              : 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400'
                          }`}
                        >
                          {p.submission_retention_mode === 'best' ? 'Lưu: Cao nhất' : 'Lưu: Cuối'}
                        </span>
                      </div>
                    </td>
                  )}
                  <td className="text-right font-mono text-xs">{p.points}</td>
                  <td className="text-center">
                    {p.user_status === 'solved' ? (
                      <CheckCircle2 className="mx-auto h-4 w-4 text-[#1F6F45] dark:text-[#84CBA3]" />
                    ) : p.user_status === 'attempted' ? (
                      <CircleDot className="mx-auto h-4 w-4 text-[#945214] dark:text-[#EDB57E]" />
                    ) : (
                      <span className="text-zinc-300 dark:text-zinc-700">—</span>
                    )}
                  </td>
                  <td className="text-right font-mono text-xs text-zinc-500">
                    {p.ac_count} ({p.ac_rate}%)
                  </td>
                  <td className="text-right space-x-2 whitespace-nowrap">
                    <Link
                      to={`/problems/${p.code}`}
                      onMouseEnter={() => api.prefetchProblem(p.code)}
                      className="text-xs font-medium text-[#2A5C99] dark:text-[#89B4E8] hover:underline"
                    >
                      Giải
                    </Link>
                    {isStaff && (
                      <Link
                        to={`/admin/problems/${p.id}/edit`}
                        className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                      >
                        Sửa
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-zinc-500">
          <span>
            Trang {page} / {totalPages}
          </span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="noka-btn-secondary text-xs">
              Trước
            </button>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="noka-btn-secondary text-xs">
              Sau
            </button>
          </div>
        </div>
      )}

      {/* Quick Visibility, Allowed Users & Retention Modal */}
      {accessModalProblem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4">
          <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-md border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-[#14171D] p-5 shadow-lg space-y-4">
            <div className="flex items-start justify-between gap-3 border-b border-zinc-200 dark:border-zinc-800 pb-3">
              <div>
                <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                  Phân quyền & Lưu bài nộp — {accessModalProblem.code}
                </h2>
                <p className="text-xs text-zinc-500">{accessModalProblem.title}</p>
              </div>
              <button
                type="button"
                onClick={() => setAccessModalProblem(null)}
                className="rounded p-1 text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {loadingAccess ? (
              <div className="py-8 text-center text-xs text-zinc-500">Đang tải cấu hình...</div>
            ) : (
              <>
                <div className="space-y-1.5">
                  <div className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                    Chế độ hiển thị & phân quyền học sinh
                  </div>
                  <ProblemAccessPicker
                    visibility={modalVisibility}
                    allowedUsers={modalAllowedUsers}
                    onVisibilityChange={setModalVisibility}
                    onAllowedUsersChange={setModalAllowedUsers}
                  />
                </div>

                <div className="space-y-1.5 border-t border-zinc-200 dark:border-zinc-800 pt-3">
                  <div className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                    Chế độ lưu bài nộp của học sinh (tối đa 1 bản / học sinh)
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    <button
                      type="button"
                      onClick={() => setModalRetention('latest')}
                      className={`rounded-md border p-2.5 text-left transition-colors ${
                        modalRetention === 'latest'
                          ? 'border-[#2A5C99] bg-[#2A5C99]/[0.07] dark:border-[#89B4E8] dark:bg-[#89B4E8]/15'
                          : 'border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-800/60'
                      }`}
                    >
                      <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                        Lưu lần nộp cuối cùng (Mặc định)
                      </div>
                      <div className="text-[11px] text-zinc-500 mt-0.5">
                        Chỉ giữ bài nộp mới nhất, tự động xóa các bài nộp cũ hơn trên DB & R2.
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={() => setModalRetention('best')}
                      className={`rounded-md border p-2.5 text-left transition-colors ${
                        modalRetention === 'best'
                          ? 'border-[#2A5C99] bg-[#2A5C99]/[0.07] dark:border-[#89B4E8] dark:bg-[#89B4E8]/15'
                          : 'border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-800/60'
                      }`}
                    >
                      <div className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                        Lưu lần có điểm cao nhất
                      </div>
                      <div className="text-[11px] text-zinc-500 mt-0.5">
                        Giữ bản điểm cao nhất (bằng điểm giữ bản mới hơn); bài điểm thấp hơn sẽ tự xóa sau khi hiển thị kết quả.
                      </div>
                    </button>
                  </div>
                </div>
              </>
            )}

            <div className="flex justify-end gap-2 border-t border-zinc-200 dark:border-zinc-800 pt-3">
              <button
                type="button"
                onClick={() => setAccessModalProblem(null)}
                className="noka-btn-secondary text-xs"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={loadingAccess || savingAccess}
                onClick={handleSaveAccessModal}
                className="noka-btn-primary text-xs"
              >
                <Save className="h-3.5 w-3.5" />
                {savingAccess ? 'Đang lưu...' : 'Lưu cấu hình'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
