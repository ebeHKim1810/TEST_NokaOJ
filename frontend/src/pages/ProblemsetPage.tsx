import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, CircleDot, Plus, Search, ArrowUpDown } from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { DifficultyBadge } from '../components/StatusBadge';
import { ProblemSummary } from '../types';

export const ProblemsetPage: React.FC = () => {
  const { isStaff } = useApp();
  const [items, setItems] = useState<ProblemSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [tags, setTags] = useState<Array<{ id: number; name: string; slug: string }>>([]);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState('');
  const [tag, setTag] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const [solvedStatus, setSolvedStatus] = useState('');
  const [visibility, setVisibility] = useState('');
  const [sortBy, setSortBy] = useState('code');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(1);
  const pageSize = 20;

  useEffect(() => {
    api.listTags().then((r) => setTags(r.items || [])).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .listProblems({
        search,
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
        setItems(res.items || []);
        setTotal(res.total || 0);
      })
      .finally(() => setLoading(false));
  }, [search, tag, difficulty, solvedStatus, visibility, sortBy, sortDir, page]);

  const toggleSort = (col: string) => {
    if (sortBy === col) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortBy(col);
      setSortDir('asc');
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
          <option value="">Tất cả nguồn</option>
          <option value="public">Công khai</option>
          <option value="assigned">Được giao</option>
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
                    <Link
                      to={`/problems/${p.code}`}
                      className="font-medium text-zinc-900 dark:text-zinc-100 hover:text-[#2A5C99] dark:hover:text-[#89B4E8]"
                    >
                      {p.title}
                    </Link>
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
                    <Link to={`/problems/${p.code}`} className="text-xs font-medium text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
                      Giải
                    </Link>
                    {isStaff && (
                      <Link to={`/admin/problems/${p.id}/edit`} className="text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
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
    </div>
  );
};
