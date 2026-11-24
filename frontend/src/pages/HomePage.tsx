import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Clock, Trophy } from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { DifficultyBadge } from '../components/StatusBadge';
import { ContestItem, ProblemSummary } from '../types';

export const HomePage: React.FC = () => {
  const { user, loadingAuth, siteName } = useApp();
  const [problems, setProblems] = useState<ProblemSummary[]>([]);
  const [contests, setContests] = useState<ContestItem[]>([]);
  const [assignments, setAssignments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (loadingAuth) return;
    let active = true;
    Promise.all([
      api.listProblems({ page: 1, page_size: 10, sort_by: 'code', sort_dir: 'desc' }),
      api.listContests(),
      user ? api.myAssignments().catch(() => ({ items: [] })) : Promise.resolve({ items: [] }),
    ])
      .then(([pRes, cRes, aRes]) => {
        if (!active) return;
        setProblems(pRes.items || []);
        setContests((cRes.items || []).filter((c: ContestItem) => c.status !== 'ENDED').slice(0, 4));
        setAssignments((aRes.items || []).slice(0, 5));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [user, loadingAuth]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-zinc-200 dark:border-zinc-800 pb-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
            {siteName}
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Hệ thống luyện tập lập trình, quản lý lớp học và chấm bài tự động.
          </p>
        </div>

        {user && (
          <div className="flex items-center gap-6 text-sm">
            <div>
              <span className="text-zinc-500 dark:text-zinc-400">Đã giải: </span>
              <span className="font-mono font-semibold text-[#1F6F45] dark:text-[#98DFB5]">
                {user.stats?.solved_count ?? 0}
              </span>
            </div>
            <div>
              <span className="text-zinc-500 dark:text-zinc-400">Lượt nộp: </span>
              <span className="font-mono font-semibold text-zinc-900 dark:text-zinc-100">
                {user.stats?.submission_count ?? 0}
              </span>
            </div>
          </div>
        )}
      </div>

      {contests.length > 0 && (
        <section className="space-y-2.5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5">
              <Trophy className="h-4 w-4" /> Kỳ thi đang diễn ra & sắp tới
            </h2>
            <Link to="/contests" className="text-xs font-medium text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
              Xem tất cả
            </Link>
          </div>
          <div className="noka-section overflow-hidden">
            <table className="noka-table">
              <thead>
                <tr>
                  <th>Tên kỳ thi</th>
                  <th>Trạng thái</th>
                  <th>Bắt đầu</th>
                  <th>Kết thúc</th>
                  <th className="text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {contests.map((c) => (
                  <tr key={c.id}>
                    <td className="font-medium text-zinc-900 dark:text-zinc-100">{c.title}</td>
                    <td>
                      <span
                        className={`inline-block rounded px-2 py-0.5 font-mono text-xs ${
                          c.status === 'RUNNING'
                            ? 'bg-[#EBF7F0] text-[#1F6F45] dark:bg-[#84CBA3]/15 dark:text-[#98DFB5]'
                            : 'bg-[#EBF3FC] text-[#2A5C99] dark:bg-[#89B4E8]/15 dark:text-[#A7C8F0]'
                        }`}
                      >
                        {c.status}
                      </span>
                    </td>
                    <td className="font-mono text-xs text-zinc-500">{new Date(c.start_time).toLocaleString()}</td>
                    <td className="font-mono text-xs text-zinc-500">{new Date(c.end_time).toLocaleString()}</td>
                    <td className="text-right">
                      <Link to={`/contests/${c.id}`} className="text-xs font-medium text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
                        Vào thi
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {assignments.length > 0 && (
        <section className="space-y-2.5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5">
              <Clock className="h-4 w-4" /> Bài tập đang được giao
            </h2>
            <Link to="/classrooms" className="text-xs font-medium text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
              Lớp học của tôi
            </Link>
          </div>
          <div className="noka-section divide-y divide-zinc-100 dark:divide-zinc-800">
            {assignments.map((a) => (
              <div key={a.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-4 py-3">
                <div>
                  <div className="font-medium text-zinc-900 dark:text-zinc-100">
                    {a.title} <span className="text-xs font-normal text-zinc-500">({a.classroom_name})</span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {(a.problems || []).map((p: any) => (
                      <Link
                        key={p.id}
                        to={`/problems/${p.code}`}
                        className="rounded border border-zinc-200 dark:border-zinc-700 px-2 py-0.5 font-mono text-xs hover:border-[#89B4E8]"
                      >
                        {p.code}: {p.title}
                      </Link>
                    ))}
                  </div>
                </div>
                {a.due_at && (
                  <span className="font-mono text-xs text-[#945214] dark:text-[#F3C89A]">
                    Hạn nộp: {new Date(a.due_at).toLocaleString()}
                  </span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="space-y-2.5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
            Bài tập mới nhất
          </h2>
          <Link to="/problems" className="inline-flex items-center gap-1 text-xs font-medium text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
            Mở Problemset <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <div className="noka-section overflow-x-auto">
          {loading ? (
            <div className="p-6 text-center text-sm text-zinc-500">Đang tải dữ liệu...</div>
          ) : problems.length === 0 ? (
            <div className="p-6 text-center text-sm text-zinc-500">Chưa có bài tập công khai nào.</div>
          ) : (
            <table className="noka-table">
              <thead>
                <tr>
                  <th className="w-24">ID</th>
                  <th>Tên bài</th>
                  <th>Độ khó</th>
                  <th className="text-right">Điểm</th>
                  <th className="text-right">AC</th>
                  <th className="w-24 text-center">Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {problems.map((p) => (
                  <tr key={p.id}>
                    <td className="font-mono text-xs text-zinc-500">{p.code}</td>
                    <td>
                      <Link
                        to={`/problems/${p.code}`}
                        onMouseEnter={() => api.prefetchProblem(p.code)}
                        className="font-medium text-zinc-900 dark:text-zinc-100 hover:text-[#2A5C99] dark:hover:text-[#89B4E8]"
                      >
                        {p.title}
                      </Link>
                    </td>
                    <td>
                      <DifficultyBadge difficulty={p.difficulty} />
                    </td>
                    <td className="text-right font-mono text-xs">{p.points}</td>
                    <td className="text-right font-mono text-xs text-zinc-500">{p.ac_count}</td>
                    <td className="text-center">
                      {p.user_status === 'solved' && (
                        <CheckCircle2 className="mx-auto h-4 w-4 text-[#1F6F45] dark:text-[#84CBA3]" />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
};
