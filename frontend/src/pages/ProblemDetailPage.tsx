import React, { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import {
  Play,
  Send,
  Clock,
  Cpu,
  Award,
  Settings,
  ArrowLeft,
  Trophy,
  BookOpen,
  Code2,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { DifficultyBadge, VerdictBadge } from '../components/StatusBadge';
import { MarkdownLatex } from '../components/MarkdownLatex';
import { LanguageId, ProblemDetail } from '../types';

const DEFAULT_TEMPLATES: Record<LanguageId, string> = {
  cpp17: `#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n\n    return 0;\n}\n`,
  cpp20: `#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n\n    return 0;\n}\n`,
  python3: `import sys\n\ndef solve():\n    data = sys.stdin.read().split()\n    if not data:\n        return\n\nif __name__ == '__main__':\n    solve()\n`,
};

export const ProblemDetailPage: React.FC = () => {
  const { codeOrId } = useParams<{ codeOrId: string }>();
  const [searchParams] = useSearchParams();
  const rawContestId = searchParams.get('contest_id');
  const contestId = rawContestId && /^\d+$/.test(rawContestId) ? Number(rawContestId) : undefined;
  const { theme, user, isStaff, toast } = useApp();

  const [problem, setProblem] = useState<ProblemDetail | null>(null);
  const [contestInfo, setContestInfo] = useState<{ id: number; title: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [language, setLanguage] = useState<LanguageId>('cpp17');
  const [code, setCode] = useState(DEFAULT_TEMPLATES.cpp17);

  const [running, setRunning] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sampleResult, setSampleResult] = useState<any>(null);
  const [latestSub, setLatestSub] = useState<any>(null);
  const [codeCollapsed, setCodeCollapsed] = useState(false);
  const [mobileTab, setMobileTab] = useState<'statement' | 'code'>('statement');

  const getDraftKey = (probCode: string, lang: LanguageId) =>
    contestId ? `noka_draft_c${contestId}_${probCode}_${lang}` : `noka_draft_${probCode}_${lang}`;

  useEffect(() => {
    if (!codeOrId) return;
    setLoading(true);
    setLatestSub(null);
    setSampleResult(null);
    api
      .getProblem(codeOrId, contestId)
      .then((p: ProblemDetail) => {
        setProblem(p);
        // Never load old practice drafts when participating in a contest that blocks old code
        if (!contestId && p.block_old_code) {
          setCode(DEFAULT_TEMPLATES[language]);
        } else {
          const saved = localStorage.getItem(getDraftKey(p.code, language));
          setCode(saved !== null ? saved : DEFAULT_TEMPLATES[language]);
        }
      })
      .catch((err) => toast(err.message, 'error'))
      .finally(() => setLoading(false));
  }, [codeOrId, contestId]);

  useEffect(() => {
    if (!contestId) {
      setContestInfo(null);
      return;
    }
    api
      .getContest(contestId)
      .then((c) => setContestInfo({ id: c.id, title: c.title }))
      .catch(() => setContestInfo(null));
  }, [contestId]);

  const handleLanguageChange = (newLang: LanguageId) => {
    setLanguage(newLang);
    if (problem) {
      if (!contestId && problem.block_old_code) {
        setCode(DEFAULT_TEMPLATES[newLang]);
      } else {
        const saved = localStorage.getItem(getDraftKey(problem.code, newLang));
        setCode(saved !== null ? saved : DEFAULT_TEMPLATES[newLang]);
      }
    }
  };

  const handleCodeChange = (val: string | undefined) => {
    const next = val ?? '';
    setCode(next);
    if (problem) {
      if (contestId || !problem.block_old_code) {
        localStorage.setItem(getDraftKey(problem.code, language), next);
      }
    }
  };

  const handleRunSample = async () => {
    if (!problem || !user) {
      toast('Vui lòng đăng nhập để chạy thử code.', 'warning');
      return;
    }
    setRunning(true);
    setSampleResult(null);
    try {
      const res = await api.runSample({
        problem_id: problem.id,
        language,
        source_code: code,
      });
      setSampleResult(res);
    } catch (err: any) {
      toast(err.message, 'error');
    } finally {
      setRunning(false);
    }
  };

  const handleSubmit = async () => {
    if (!problem || !user) {
      toast('Vui lòng đăng nhập để nộp bài.', 'warning');
      return;
    }
    setSubmitting(true);
    try {
      const sub = await api.submitCode({
        problem_id: problem.id,
        language,
        source_code: code,
        ...(contestId ? { contest_id: contestId } : {}),
      });
      setLatestSub(sub);
      toast(`Đã nộp bài #${sub.id}. Đang chấm...`, 'info');
      // Poll until completed
      let current = sub;
      for (let i = 0; i < 20 && current.status !== 'COMPLETED'; i++) {
        await new Promise((r) => setTimeout(r, 800));
        current = await api.getSubmission(sub.id);
        setLatestSub(current);
      }
      if (current.verdict === 'AC') toast(`Accepted! (${current.score}/${current.max_score})`, 'success');
      else if (current.status === 'COMPLETED') toast(`Kết quả: ${current.verdict}`, 'warning');
    } catch (err: any) {
      toast(err.message, 'error');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="py-12 text-center text-sm text-zinc-500">Đang tải đề bài...</div>;
  if (!problem) return <div className="py-12 text-center text-sm text-zinc-500">Không tìm thấy bài tập.</div>;

  return (
    <div className="space-y-4">
      {contestId && (
        <div className="noka-section px-4 py-2.5 flex flex-wrap items-center justify-between gap-2 text-sm bg-[#2A5C99]/5 dark:bg-[#89B4E8]/10 border-[#2A5C99]/20 dark:border-[#89B4E8]/20">
          <div className="flex items-center gap-2 font-medium">
            <Trophy className="h-4 w-4 text-[#2A5C99] dark:text-[#89B4E8]" />
            <span>Đang làm bài trong kỳ thi: {contestInfo?.title || `#${contestId}`}</span>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <Link to={`/contests/${contestId}`} className="inline-flex items-center gap-1 text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
              <ArrowLeft className="h-3.5 w-3.5" /> Quay lại kỳ thi
            </Link>
            <Link to={`/contests/${contestId}?tab=scoreboard`} className="font-medium text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
              Xem bảng điểm
            </Link>
          </div>
        </div>
      )}
      {!contestId && problem.block_old_code && (
        <div className="rounded-md border border-amber-300 dark:border-amber-800/70 bg-amber-50 dark:bg-amber-950/30 px-3.5 py-2 text-xs text-amber-900 dark:text-amber-200">
          Bạn đang tham gia kỳ thi có khóa xem lại code cũ — bản nháp và bài nộp cũ không được hiển thị.
        </div>
      )}
      {/* Mobile Tab Switcher (Đề bài / Code) */}
      <div className="flex lg:hidden rounded-md border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-[#15181E] p-1 gap-1">
        <button
          type="button"
          onClick={() => setMobileTab('statement')}
          className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
            mobileTab === 'statement'
              ? 'bg-white dark:bg-[#1E222B] text-[#2A5C99] dark:text-[#89B4E8] shadow-sm'
              : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'
          }`}
        >
          <BookOpen className="h-3.5 w-3.5" /> Đề bài
        </button>
        <button
          type="button"
          onClick={() => setMobileTab('code')}
          className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
            mobileTab === 'code'
              ? 'bg-white dark:bg-[#1E222B] text-[#2A5C99] dark:text-[#89B4E8] shadow-sm'
              : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'
          }`}
        >
          <Code2 className="h-3.5 w-3.5" /> Khung Code
        </button>
      </div>

      <div className="flex flex-col lg:flex-row gap-5 items-start">
      {/* Left: Statement (expands to 100% width when Code panel is collapsed on desktop) */}
      <div
        className={`${mobileTab === 'code' ? 'hidden lg:block' : 'block'} w-full ${
          codeCollapsed ? 'lg:flex-1' : 'lg:w-1/2'
        } min-w-0 space-y-5`}
      >
        <div className="border-b border-zinc-200 dark:border-zinc-800 pb-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-zinc-500">{problem.code}</span>
                <DifficultyBadge difficulty={problem.difficulty} />
              </div>
              <h1 className="mt-1 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                {problem.title}
              </h1>
            </div>
            {isStaff && (
              <Link to={`/admin/problems/${problem.id}/edit`} className="noka-btn-secondary text-xs">
                <Settings className="h-3.5 w-3.5" /> Quản lý
              </Link>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-4 text-xs font-mono text-zinc-500 dark:text-zinc-400">
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" /> {problem.time_limit_ms} ms
            </span>
            <span className="inline-flex items-center gap-1">
              <Cpu className="h-3.5 w-3.5" /> {problem.memory_limit_mb} MB
            </span>
            <span className="inline-flex items-center gap-1">
              <Award className="h-3.5 w-3.5" /> {problem.points} điểm
            </span>
          </div>

          {problem.tags.length > 0 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {problem.tags.map((t) => (
                <span
                  key={t}
                  className="rounded bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-600 dark:text-zinc-400"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>

        <section className="space-y-4">
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-2">Đề bài</h2>
            <MarkdownLatex content={problem.statement_md} />
          </div>

          {problem.input_description && (
            <div>
              <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-1.5">Dữ liệu vào (Input)</h2>
              <MarkdownLatex content={problem.input_description} />
            </div>
          )}

          {problem.output_description && (
            <div>
              <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-1.5">Dữ liệu ra (Output)</h2>
              <MarkdownLatex content={problem.output_description} />
            </div>
          )}

          {problem.constraints_md && (
            <div>
              <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-1.5">Ràng buộc (Constraints)</h2>
              <MarkdownLatex content={problem.constraints_md} />
            </div>
          )}

          {(problem.sample_input || problem.sample_output) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-1">Sample Input</div>
                <pre className="rounded-md border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-[#14171D] p-3 text-xs overflow-x-auto">
                  {problem.sample_input}
                </pre>
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-1">Sample Output</div>
                <pre className="rounded-md border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-[#14171D] p-3 text-xs overflow-x-auto">
                  {problem.sample_output}
                </pre>
              </div>
            </div>
          )}

          {problem.explanation && problem.explanation.trim().length > 0 && (
            <div className="rounded-md border border-zinc-200 dark:border-zinc-800 bg-zinc-50/70 dark:bg-[#14171D] p-4 space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[#2A5C99] dark:text-[#89B4E8]">
                Giải thích
              </h2>
              <MarkdownLatex content={problem.explanation} />
            </div>
          )}
        </section>

        {problem.recent_submissions && problem.recent_submissions.length > 0 && (
          <section className="pt-3 border-t border-zinc-200 dark:border-zinc-800">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-2">
              Bài nộp gần đây của bạn
            </h2>
            <div className="noka-section overflow-hidden">
              <table className="noka-table text-xs">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Ngôn ngữ</th>
                    <th>Kết quả</th>
                    <th className="text-right">Thời gian</th>
                  </tr>
                </thead>
                <tbody>
                  {problem.recent_submissions.map((s) => (
                    <tr key={s.id}>
                      <td className="font-mono">
                        <Link to={`/submissions/${s.id}`} className="text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
                          #{s.id}
                        </Link>
                      </td>
                      <td className="font-mono">{s.language}</td>
                      <td>
                        <VerdictBadge verdict={s.verdict} />
                      </td>
                      <td className="text-right font-mono">{s.execution_time_ms} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>

      {/* Right: Monaco Editor & Judge Output (kept mounted in DOM when collapsed so code & undo history are preserved) */}
      <div
        className={`${mobileTab === 'statement' ? 'hidden' : 'block'} ${
          codeCollapsed ? 'lg:hidden' : 'lg:block'
        } w-full lg:w-1/2 min-w-0 space-y-3 lg:sticky lg:top-20`}
      >
        <div className="noka-section overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/70 dark:bg-[#15181E] px-3 py-2">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setCodeCollapsed(true)}
                title="Thu gọn khung code để mở rộng đề bài"
                className="hidden lg:inline-flex items-center gap-1 rounded border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-2 py-1 text-xs text-zinc-600 dark:text-zinc-300 hover:border-[#2A5C99] hover:text-[#2A5C99] dark:hover:border-[#89B4E8] dark:hover:text-[#89B4E8] transition-colors"
              >
                <ChevronsRight className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">Thu gọn</span>
              </button>
              <select
                value={language}
                onChange={(e) => handleLanguageChange(e.target.value as LanguageId)}
                className="noka-input w-auto py-1 text-xs font-mono"
              >
                <option value="cpp17">C++17 (GCC)</option>
                <option value="cpp20">C++20 (GCC)</option>
                <option value="python3">Python 3</option>
              </select>
              <span className="hidden sm:inline text-[11px] text-zinc-400">Tự động lưu nháp</span>
            </div>

            <div className="flex items-center gap-2">
              <button onClick={handleRunSample} disabled={running || submitting} className="noka-btn-secondary text-xs">
                <Play className="h-3.5 w-3.5" /> {running ? 'Đang chạy...' : 'Chạy thử'}
              </button>
              <button onClick={handleSubmit} disabled={submitting || running} className="noka-btn-primary text-xs">
                <Send className="h-3.5 w-3.5" /> {submitting ? 'Đang nộp...' : 'Nộp bài'}
              </button>
            </div>
          </div>

          <Editor
            height="460px"
            language={language === 'python3' ? 'python' : 'cpp'}
            theme={theme === 'dark' ? 'vs-dark' : 'light'}
            value={code}
            onChange={handleCodeChange}
            options={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: 13,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              tabSize: 4,
              padding: { top: 12 },
            }}
          />
        </div>

        {sampleResult && (
          <div className="noka-section p-3.5 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-zinc-700 dark:text-zinc-300">Kết quả chạy thử Sample</span>
              <div className="flex items-center gap-2 font-mono">
                <VerdictBadge verdict={sampleResult.verdict} />
                <span>{sampleResult.execution_time_ms} ms</span>
              </div>
            </div>
            {sampleResult.compile_output && (
              <pre className="rounded bg-[#FDF0F4] dark:bg-[#29151C] p-2.5 text-[#9B3558] dark:text-[#F1B4C8] overflow-x-auto">
                {sampleResult.compile_output}
              </pre>
            )}
            {sampleResult.stdout && (
              <div>
                <div className="text-zinc-500 mb-1">Output của bạn:</div>
                <pre className="rounded bg-zinc-50 dark:bg-[#14171D] border border-zinc-200 dark:border-zinc-800 p-2 overflow-x-auto">
                  {sampleResult.stdout}
                </pre>
              </div>
            )}
            {sampleResult.checker_message && (
              <div className="text-zinc-500">{sampleResult.checker_message}</div>
            )}
          </div>
        )}

        {latestSub && (
          <div className="noka-section p-3.5 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-zinc-500">Submission #{latestSub.id}</span>
                <VerdictBadge verdict={latestSub.verdict} />
                <span className="font-mono">
                  {latestSub.score}/{latestSub.max_score} điểm · {latestSub.execution_time_ms} ms
                </span>
              </div>
              {latestSub.discarded_by_retention ? (
                latestSub.kept_submission_id && (
                  <Link
                    to={`/submissions/${latestSub.kept_submission_id}`}
                    className="font-medium text-[#2A5C99] dark:text-[#89B4E8] hover:underline"
                  >
                    Xem bài điểm cao nhất (#{latestSub.kept_submission_id})
                  </Link>
                )
              ) : (
                <Link to={`/submissions/${latestSub.id}`} className="font-medium text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
                  Xem chi tiết
                </Link>
              )}
            </div>
            {latestSub.compile_output && (
              <pre className="rounded bg-[#FDF0F4] dark:bg-[#29151C] p-2.5 text-[#9B3558] dark:text-[#F1B4C8] overflow-x-auto whitespace-pre-wrap">
                {latestSub.compile_output}
              </pre>
            )}
            {latestSub.discarded_by_retention && (
              <div className="rounded border border-amber-300/70 dark:border-amber-800/70 bg-amber-50 dark:bg-amber-950/30 px-2.5 py-1.5 text-[11px] text-amber-900 dark:text-amber-200">
                Chế độ <strong>Lưu lần điểm cao nhất</strong>: Hệ thống giữ lại bài nộp #{latestSub.kept_submission_id} ({latestSub.kept_score} điểm — {latestSub.kept_verdict}) và tự động xóa lần nộp điểm thấp hơn này để tiết kiệm dung lượng.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Collapsed Code Editor Rail on Desktop */}
      {codeCollapsed && (
        <button
          type="button"
          onClick={() => setCodeCollapsed(false)}
          title="Mở lại khung soạn thảo code"
          className="hidden lg:flex flex-col items-center gap-3 sticky top-20 w-10 shrink-0 rounded-md border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-[#15181E] py-3.5 px-1.5 text-zinc-600 dark:text-zinc-300 hover:border-[#2A5C99] hover:text-[#2A5C99] dark:hover:border-[#89B4E8] dark:hover:text-[#89B4E8] transition-colors shadow-sm"
        >
          <ChevronsLeft className="h-4 w-4 shrink-0 text-[#2A5C99] dark:text-[#89B4E8]" />
          <span className="text-xs font-medium tracking-wide [writing-mode:vertical-rl] rotate-180 select-none">
            Mở khung code
          </span>
        </button>
      )}
      </div>
    </div>
  );
};
