import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Lock, RefreshCw } from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { VerdictBadge } from '../components/StatusBadge';
import { SubmissionSummary } from '../types';

export const SubmissionsPage: React.FC = () => {
  const [items, setItems] = useState<SubmissionSummary[]>([]);
  const [oldCodeBlocked, setOldCodeBlocked] = useState(false);
  const [blockingContests, setBlockingContests] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState('');
  const [problemCode, setProblemCode] = useState('');
  const [language, setLanguage] = useState('');
  const [verdict, setVerdict] = useState('');

  const load = () => {
    setLoading(true);
    api
      .listSubmissions({ username, problem_code: problemCode, language, verdict })
      .then((res) => {
        setItems(res.items || []);
        setOldCodeBlocked(Boolean(res.old_code_blocked));
        setBlockingContests(res.blocking_contests || []);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [username, problemCode, language, verdict]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">Lịch sử nộp bài</h1>
        <button onClick={load} className="noka-btn-secondary text-xs">
          <RefreshCw className="h-3.5 w-3.5" /> Làm mới
        </button>
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
                    <Link to={`/problems/${s.problem_code}`} className="hover:underline">
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
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export const SubmissionDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { isStaff, toast } = useApp();
  const [sub, setSub] = useState<any>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 dark:border-zinc-800 pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-semibold">Submission #{sub.id}</h1>
            <VerdictBadge verdict={sub.verdict} />
          </div>
          <p className="text-xs text-zinc-500 font-mono">
            {sub.username} · {sub.problem_code} ({sub.problem_title}) · {sub.language} · {sub.score}/{sub.max_score} điểm · {sub.execution_time_ms} ms · {sub.memory_kb} KB
          </p>
        </div>
        {isStaff && (
          <button onClick={handleRejudge} className="noka-btn-secondary text-xs">
            <RefreshCw className="h-3.5 w-3.5" /> Chấm lại (Rejudge)
          </button>
        )}
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
    </div>
  );
};
