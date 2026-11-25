import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Save, Upload, Download, Trash2, Plus, Sparkles, Code2, Shield, HardDrive } from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ProblemAccessPicker } from '../components/ProblemAccessPicker';
import { ProblemAutoImportBox } from '../components/ProblemAutoImportBox';
import { RichMarkdownField } from '../components/RichMarkdownToolbar';
import { TestcaseGeneratorPanel } from '../features/testcase-generator/TestcaseGeneratorPanel';
import {
  AllowedUserItem,
  AutoImportProblemResult,
  ProblemSample,
  SubmissionRetentionMode,
  TestcaseGroup,
  TestcaseItem,
  Visibility,
} from '../types';

const CHECKER_TEMPLATES: Record<'python3' | 'cpp17' | 'cpp20', string> = {
  python3: `import sys

# Output cua thi sinh duoc truyen truc tiep vao stdin
student_output = sys.stdin.read().strip()

# (Tuy chon) Neu can doc them Input cua testcase:
# with open(sys.argv[1], "r", encoding="utf-8") as f:
#     test_input = f.read().strip()

# Kiem tra dieu kien hop le -> in "OK" neu dung, in "NO" neu sai
if student_output:
    print("OK")
else:
    print("NO")
`,
  cpp17: `#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
    // Output cua thi sinh duoc truyen truc tiep vao cin (stdin)
    // (Tuy chon) Doc Input cua testcase tu file argv[1]:
    // ifstream fin(argv[1]);

    string out;
    if (getline(cin, out) && !out.empty()) {
        cout << "OK\\n";
    } else {
        cout << "NO\\n";
    }
    return 0;
}
`,
  cpp20: `#include <bits/stdc++.h>
using namespace std;

int main(int argc, char* argv[]) {
    // Output cua thi sinh duoc truyen truc tiep vao cin (stdin)
    // (Tuy chon) Doc Input cua testcase tu file argv[1]:
    // ifstream fin(argv[1]);

    string out;
    if (getline(cin, out) && !out.empty()) {
        cout << "OK\\n";
    } else {
        cout << "NO\\n";
    }
    return 0;
}
`,
};

export const AdminProblemManagerPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const isNew = !id || id === 'new';
  const navigate = useNavigate();
  const { toast } = useApp();

  const [tab, setTab] = useState<'info' | 'testcases' | 'generator'>('info');
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    code: '',
    title: '',
    statement_md: '',
    input_description: '',
    output_description: '',
    constraints_md: '',
    sample_input: '',
    sample_output: '',
    explanation: '',
    time_limit_ms: 1000,
    memory_limit_mb: 256,
    points: 100,
    difficulty: 'easy',
    visibility: 'public' as Visibility,
    submission_retention_mode: 'latest' as SubmissionRetentionMode,
    checker_type: 'standard',
    checker_language: 'python3' as 'python3' | 'cpp17' | 'cpp20',
    checker_source: '',
    tags: '',
  });
  const [allowedUsers, setAllowedUsers] = useState<AllowedUserItem[]>([]);
  const [samples, setSamples] = useState<ProblemSample[]>([{ input: '', output: '', explanation: '' }]);
  const [confirmDeleteProblem, setConfirmDeleteProblem] = useState(false);
  const [deletingProblem, setDeletingProblem] = useState(false);

  // Testcase states
  const [testcases, setTestcases] = useState<TestcaseItem[]>([]);
  const [groups, setGroups] = useState<TestcaseGroup[]>([]);
  const [newTc, setNewTc] = useState({ name: '', input_data: '', expected_output: '', is_sample: false });
  const [zipWarnings, setZipWarnings] = useState<string[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<TestcaseItem | null>(null);

  const loadTestcases = (pid: number) => {
    api
      .listTestcases(pid)
      .then((res) => {
        setTestcases(res.items || []);
        setGroups(res.groups || []);
      })
      .catch((e) => toast(e.message, 'error'));
  };

  useEffect(() => {
    if (!isNew && id) {
      api.getProblem(id).then((p) => {
        setForm({
          code: p.code || '',
          title: p.title || '',
          statement_md: p.statement_md || '',
          input_description: p.input_description || '',
          output_description: p.output_description || '',
          constraints_md: p.constraints_md || '',
          sample_input: p.sample_input || '',
          sample_output: p.sample_output || '',
          explanation: p.explanation || '',
          time_limit_ms: p.time_limit_ms || 1000,
          memory_limit_mb: p.memory_limit_mb || 256,
          points: p.points || 100,
          difficulty: p.difficulty || 'easy',
          visibility: (p.visibility || 'public') as Visibility,
          submission_retention_mode: (p.submission_retention_mode || 'latest') as SubmissionRetentionMode,
          checker_type: p.checker_type || 'standard',
          checker_language: (p.checker_language || 'python3') as 'python3' | 'cpp17' | 'cpp20',
          checker_source: p.checker_source || '',
          tags: (p.tags || []).join(', '),
        });
        const loadedSamples: ProblemSample[] =
          Array.isArray(p.samples) && p.samples.length > 0
            ? p.samples.map((s: any) => ({
                input: String(s?.input ?? ''),
                output: String(s?.output ?? ''),
                explanation: String(s?.explanation ?? ''),
              }))
            : p.sample_input || p.sample_output || p.explanation
            ? [
                {
                  input: String(p.sample_input || ''),
                  output: String(p.sample_output || ''),
                  explanation: String(p.explanation || ''),
                },
              ]
            : [{ input: '', output: '', explanation: '' }];
        setSamples(loadedSamples);
        setAllowedUsers(p.allowed_users || []);
        loadTestcases(p.id);
      });
    }
  }, [id, isNew]);

  const updateSample = (idx: number, field: keyof ProblemSample, value: string) => {
    setSamples((prev) => prev.map((s, i) => (i === idx ? { ...s, [field]: value } : s)));
  };

  const addSample = () => {
    setSamples((prev) => [...prev, { input: '', output: '', explanation: '' }]);
  };

  const removeSample = (idx: number) => {
    setSamples((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== idx) : prev));
  };

  const handleDeleteProblem = async () => {
    if (isNew || !id) return;
    setDeletingProblem(true);
    try {
      const res = await api.deleteProblem(Number(id));
      toast(
        `Đã xóa vĩnh viễn bài tập ${res.code || form.code} (${res.deleted_testcases ?? 0} testcase, ${res.deleted_submissions ?? 0} bài nộp, ${res.deleted_storage_files ?? 0} file R2).`,
        'success'
      );
      setConfirmDeleteProblem(false);
      navigate('/problems');
    } catch (err: any) {
      toast(err.message || 'Không thể xóa bài tập.', 'error');
    } finally {
      setDeletingProblem(false);
    }
  };

  const handleAutoImported = (data: AutoImportProblemResult) => {
    setForm((prev) => ({
      ...prev,
      title: data.title?.trim() ? data.title : prev.title,
      statement_md: data.description?.trim() ? data.description : prev.statement_md,
      input_description: data.input_description?.trim() ? data.input_description : prev.input_description,
      output_description: data.output_description?.trim() ? data.output_description : prev.output_description,
      constraints_md: data.constraints?.trim() ? data.constraints : prev.constraints_md,
      sample_input: data.sample_input?.trim() ? data.sample_input : prev.sample_input,
      sample_output: data.sample_output?.trim() ? data.sample_output : prev.sample_output,
      explanation: data.explanation?.trim() ? data.explanation : prev.explanation,
      time_limit_ms:
        typeof data.time_limit_ms === 'number' && data.time_limit_ms >= 100
          ? data.time_limit_ms
          : prev.time_limit_ms,
      memory_limit_mb:
        typeof data.memory_limit_mb === 'number' && data.memory_limit_mb >= 16
          ? data.memory_limit_mb
          : prev.memory_limit_mb,
    }));

    if (Array.isArray(data.samples) && data.samples.length > 0) {
      setSamples(
        data.samples.map((s) => ({
          input: String(s?.input ?? ''),
          output: String(s?.output ?? ''),
          explanation: String(s?.explanation ?? ''),
        }))
      );
    } else if (data.sample_input?.trim() || data.sample_output?.trim() || data.explanation?.trim()) {
      setSamples([
        {
          input: data.sample_input || '',
          output: data.sample_output || '',
          explanation: data.explanation || '',
        },
      ]);
    }
  };

  const handleSaveProblem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.checker_type === 'custom' && !form.checker_source.trim()) {
      toast('Vui lòng dán mã nguồn trình chấm cho chế độ Chấp nhận bất kỳ đáp án hợp lệ.', 'error');
      return;
    }
    setSaving(true);
    try {
      const cleanedSamples = samples.filter(
        (s) => s.input.trim() || s.output.trim() || s.explanation.trim()
      );
      const firstSample = cleanedSamples[0] || { input: '', output: '', explanation: '' };
      const payload = {
        ...form,
        samples: cleanedSamples,
        sample_input: firstSample.input,
        sample_output: firstSample.output,
        explanation: firstSample.explanation,
        time_limit_ms: Number(form.time_limit_ms),
        memory_limit_mb: Number(form.memory_limit_mb),
        points: Number(form.points),
        allowed_user_ids: allowedUsers.map((u) => u.id),
        checker_source: form.checker_type === 'custom' ? form.checker_source : undefined,
        tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
      };
      if (isNew) {
        const created = await api.createProblem(payload);
        toast(`Đã tạo bài tập ${created.code}.`, 'success');
        navigate(`/admin/problems/${created.id}/edit`);
      } else {
        await api.updateProblem(Number(id), payload);
        toast('Đã lưu thông tin bài tập.', 'success');
      }
    } catch (err: any) {
      toast(err.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleAddTestcase = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isNew || !id) return;
    try {
      await api.createTestcase(Number(id), {
        name: newTc.name.trim() || `${String(testcases.length + 1).padStart(2, '0')}`,
        input_data: newTc.input_data,
        expected_output: newTc.expected_output,
        is_sample: newTc.is_sample,
        is_hidden: !newTc.is_sample,
      });
      setNewTc({ name: '', input_data: '', expected_output: '', is_sample: false });
      toast('Đã thêm testcase.', 'success');
      loadTestcases(Number(id));
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  const handleUploadZip = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || isNew || !id) return;
    setZipWarnings([]);
    try {
      const res = await api.uploadTestcasesZip(Number(id), file);
      toast(`Đã nhập ${res.imported_count} testcase từ ZIP.`, 'success');
      if (res.warnings?.length) setZipWarnings(res.warnings);
      loadTestcases(Number(id));
    } catch (err: any) {
      toast(err.message, 'error');
    }
    e.target.value = '';
  };

  const handleSaveAllTestcases = async () => {
    if (isNew || !id) return;
    try {
      await api.saveAllTestcases(
        Number(id),
        testcases.map((tc, idx) => ({
          id: tc.id,
          name: tc.name,
          group_id: tc.group_id,
          is_sample: tc.is_sample,
          is_hidden: tc.is_hidden,
          order_index: idx + 1,
        }))
      );
      toast('Đã lưu toàn bộ cấu hình testcase.', 'success');
      loadTestcases(Number(id));
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  const confirmDeleteTc = async () => {
    if (!deleteTarget || !id) return;
    try {
      await api.deleteTestcase(deleteTarget.id);
      toast(`Đã xóa testcase ${deleteTarget.name}.`, 'info');
      setDeleteTarget(null);
      loadTestcases(Number(id));
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">
            {isNew ? 'Tạo bài tập mới' : `Quản lý bài tập: ${form.code || `#${id}`}`}
          </h1>
          <p className="text-xs text-zinc-500">Hỗ trợ Markdown + LaTeX, Nhập đề tự động AI, Upload ZIP và Sinh Testcase.</p>
        </div>
        {!isNew && id && (
          <button
            type="button"
            onClick={() => setConfirmDeleteProblem(true)}
            className="noka-btn-danger text-xs"
          >
            <Trash2 className="h-3.5 w-3.5" /> Xóa bài tập
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-zinc-200 dark:border-zinc-800">
        <button
          onClick={() => setTab('info')}
          className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'info' ? 'border-[#2A5C99] dark:border-[#89B4E8]' : 'border-transparent text-zinc-500'
          }`}
        >
          1. Thông tin bài tập
        </button>
        <button
          disabled={isNew}
          onClick={() => setTab('testcases')}
          className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px disabled:opacity-40 ${
            tab === 'testcases' ? 'border-[#2A5C99] dark:border-[#89B4E8]' : 'border-transparent text-zinc-500'
          }`}
        >
          2. Quản lý Testcase ({testcases.length})
        </button>
        <button
          disabled={isNew}
          onClick={() => setTab('generator')}
          className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 -mb-px disabled:opacity-40 ${
            tab === 'generator' ? 'border-[#2A5C99] dark:border-[#89B4E8]' : 'border-transparent text-zinc-500'
          }`}
        >
          <Sparkles className="h-3.5 w-3.5" /> 3. Generate Testcases
        </button>
      </div>

      {tab === 'info' && (
        <form onSubmit={handleSaveProblem} className="space-y-4">
          <ProblemAutoImportBox onImported={handleAutoImported} disabled={saving} />

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Mã bài (để trống sẽ tự sinh)</label>
              <input value={form.code} disabled={!isNew} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="NK0001" className="noka-input font-mono" />
            </div>
            <div className="md:col-span-3">
              <label className="block text-xs font-medium text-zinc-500 mb-1">Tên bài tập *</label>
              <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Tổng hai số nguyên" className="noka-input" />
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Time Limit (ms)</label>
              <input type="number" value={form.time_limit_ms} onChange={(e) => setForm({ ...form, time_limit_ms: Number(e.target.value) })} className="noka-input font-mono" />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Memory (MB)</label>
              <input type="number" value={form.memory_limit_mb} onChange={(e) => setForm({ ...form, memory_limit_mb: Number(e.target.value) })} className="noka-input font-mono" />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Điểm</label>
              <input type="number" value={form.points} onChange={(e) => setForm({ ...form, points: Number(e.target.value) })} className="noka-input font-mono" />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Độ khó</label>
              <select value={form.difficulty} onChange={(e) => setForm({ ...form, difficulty: e.target.value })} className="noka-input">
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-500 mb-1">Tags (dấu phẩy)</label>
              <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="math, dp" className="noka-input" />
            </div>
          </div>

          {/* Visibility & Allowed Students */}
          <div className="noka-section p-4 space-y-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
              <Shield className="h-4 w-4 text-[#2A5C99] dark:text-[#89B4E8]" />
              Chế độ hiển thị & Phân quyền bài tập
            </div>
            <ProblemAccessPicker
              visibility={form.visibility}
              allowedUsers={allowedUsers}
              onVisibilityChange={(next) => setForm({ ...form, visibility: next })}
              onAllowedUsersChange={setAllowedUsers}
            />
          </div>

          {/* Submission Retention Policy */}
          <div className="noka-section p-4 space-y-3">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
              <HardDrive className="h-4 w-4 text-[#2A5C99] dark:text-[#89B4E8]" />
              Chế độ lưu bài nộp của học sinh (Tối ưu dung lượng DB & R2)
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {[
                {
                  id: 'latest' as SubmissionRetentionMode,
                  title: 'Lưu lần nộp cuối cùng',
                  desc: 'Ghi đè mỗi lần học sinh nộp lại — tự động xóa bài nộp và file code cũ trên Neon DB & Cloudflare R2.',
                },
                {
                  id: 'best' as SubmissionRetentionMode,
                  title: 'Lưu lần có điểm cao nhất',
                  desc: 'Chỉ ghi đè khi đạt điểm cao hơn hoặc bằng lần trước; lần nộp điểm thấp hơn chỉ hiển thị kết quả rồi tự dọn.',
                },
              ].map((opt) => {
                const active = form.submission_retention_mode === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setForm({ ...form, submission_retention_mode: opt.id })}
                    className={`rounded-md border p-3 text-left transition-colors ${
                      active
                        ? 'border-[#2A5C99] bg-[#2A5C99]/[0.07] dark:border-[#89B4E8] dark:bg-[#89B4E8]/15'
                        : 'border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-800/60'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-3.5 w-3.5 rounded-full border-2 flex items-center justify-center ${
                          active ? 'border-[#2A5C99] dark:border-[#89B4E8]' : 'border-zinc-400'
                        }`}
                      >
                        {active && <span className="h-1.5 w-1.5 rounded-full bg-[#2A5C99] dark:bg-[#89B4E8]" />}
                      </span>
                      <span className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">{opt.title}</span>
                    </div>
                    <p className="mt-1 pl-5 text-[11px] text-zinc-500 leading-snug">{opt.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="noka-section p-4 space-y-4">
            <RichMarkdownField
              label="Nội dung đề bài (Markdown + LaTeX)"
              value={form.statement_md}
              onChange={(next) => setForm((prev) => ({ ...prev, statement_md: next }))}
              rows={9}
              placeholder="Cho hai số nguyên $a, b$ ($|a|, |b| \le 10^9$). Hãy tính tổng $a + b$..."
              emptyPreviewText="Chưa có nội dung đề bài."
            />

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Input Description</label>
                <textarea rows={3} value={form.input_description} onChange={(e) => setForm({ ...form, input_description: e.target.value })} className="noka-input text-xs" />
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Output Description</label>
                <textarea rows={3} value={form.output_description} onChange={(e) => setForm({ ...form, output_description: e.target.value })} className="noka-input text-xs" />
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Constraints</label>
                <textarea rows={3} value={form.constraints_md} onChange={(e) => setForm({ ...form, constraints_md: e.target.value })} className="noka-input text-xs font-mono" />
              </div>
            </div>

            {/* Dynamic Multi-Examples Section */}
            <div className="border-t border-zinc-200 dark:border-zinc-800 pt-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
                    Các ví dụ mẫu (Examples — {samples.length})
                  </div>
                  <p className="text-[11px] text-zinc-400">
                    Thêm không giới hạn số lượng ví dụ; mỗi ví dụ có thể kèm phần giải thích riêng (Markdown + LaTeX + hình ảnh).
                  </p>
                </div>
                <button type="button" onClick={addSample} className="noka-btn-secondary text-xs">
                  <Plus className="h-3.5 w-3.5" /> Thêm ví dụ
                </button>
              </div>

              <div className="space-y-4">
                {samples.map((sample, idx) => (
                  <div
                    key={idx}
                    className="rounded-md border border-zinc-200 dark:border-zinc-800 bg-zinc-50/40 dark:bg-[#14171D]/60 p-3.5 space-y-3"
                  >
                    <div className="flex items-center justify-between gap-2 border-b border-zinc-200/80 dark:border-zinc-800 pb-2">
                      <span className="text-xs font-semibold text-[#2A5C99] dark:text-[#89B4E8]">
                        Ví dụ {idx + 1}
                      </span>
                      {samples.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeSample(idx)}
                          title={`Xóa Ví dụ ${idx + 1}`}
                          className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-medium text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-950/40"
                        >
                          <Trash2 className="h-3 w-3" /> Xóa ví dụ
                        </button>
                      )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">Input mẫu {idx + 1}</label>
                        <textarea
                          rows={4}
                          spellCheck={false}
                          value={sample.input}
                          onChange={(e) => updateSample(idx, 'input', e.target.value)}
                          placeholder="Dữ liệu vào mẫu..."
                          className="noka-input font-mono text-xs"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">Output mẫu {idx + 1}</label>
                        <textarea
                          rows={4}
                          spellCheck={false}
                          value={sample.output}
                          onChange={(e) => updateSample(idx, 'output', e.target.value)}
                          placeholder="Dữ liệu ra mẫu..."
                          className="noka-input font-mono text-xs"
                        />
                      </div>
                    </div>

                    <RichMarkdownField
                      label={`Giải thích cho Ví dụ ${idx + 1} (Tùy chọn)`}
                      value={sample.explanation}
                      onChange={(next) => updateSample(idx, 'explanation', next)}
                      rows={4}
                      placeholder={`Giải thích chi tiết cho Ví dụ ${idx + 1} (hỗ trợ Markdown, LaTeX và chèn ảnh minh họa)...`}
                      emptyPreviewText="Chưa có phần giải thích cho ví dụ này."
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Checker Configuration */}
          <div className="noka-section p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                <Code2 className="h-4 w-4 text-[#2A5C99] dark:text-[#89B4E8]" />
                Trình chấm bài (Checker)
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1">Loại trình chấm</label>
                <select
                  value={form.checker_type}
                  onChange={(e) => setForm({ ...form, checker_type: e.target.value })}
                  className="noka-input text-sm"
                >
                  <option value="standard">Tiêu chuẩn (so khớp từng dòng, bỏ khoảng trắng cuối dòng)</option>
                  <option value="strict">Nghiêm ngặt (khớp chính xác từng ký tự)</option>
                  <option value="float_tol">Số thực (sai số 1e-6)</option>
                  <option value="custom">Chấp nhận bất kỳ đáp án hợp lệ (Custom Checker — OK / NO)</option>
                </select>
              </div>
              {form.checker_type === 'custom' && (
                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-1">Ngôn ngữ code trình chấm</label>
                  <div className="flex gap-2">
                    <select
                      value={form.checker_language}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          checker_language: e.target.value as 'python3' | 'cpp17' | 'cpp20',
                        })
                      }
                      className="noka-input flex-1 text-sm"
                    >
                      <option value="python3">Python 3</option>
                      <option value="cpp17">C++17</option>
                      <option value="cpp20">C++20</option>
                    </select>
                    <button
                      type="button"
                      onClick={() =>
                        setForm({
                          ...form,
                          checker_source: CHECKER_TEMPLATES[form.checker_language],
                        })
                      }
                      className="noka-btn-secondary text-xs shrink-0"
                    >
                      Chèn code mẫu
                    </button>
                  </div>
                </div>
              )}
            </div>

            {form.checker_type === 'custom' && (
              <div className="space-y-2">
                <div className="rounded border border-[#2A5C99]/20 dark:border-[#89B4E8]/25 bg-[#2A5C99]/[0.04] dark:bg-[#89B4E8]/[0.06] px-3 py-2 text-xs text-zinc-600 dark:text-zinc-300 space-y-1">
                  <div>
                    • <strong>Output của thí sinh</strong> sẽ được đưa trực tiếp vào <strong>Input (stdin / cin / input())</strong> của đoạn code bên dưới.
                  </div>
                  <div>
                    • Đoạn code in ra <code className="font-mono font-semibold text-emerald-700 dark:text-emerald-300">OK</code> → <strong>Đúng (AC)</strong>; in ra <code className="font-mono font-semibold text-rose-700 dark:text-rose-300">NO</code> (hoặc khác OK) → <strong>Sai (WA)</strong>.
                  </div>
                  <div className="text-zinc-500">
                    • Tùy chọn nâng cao: nếu cần đọc thêm Input của testcase (hoặc Output mẫu), file được truyền qua tham số dòng lệnh <code className="font-mono">argv[1]</code> (input testcase), <code className="font-mono">argv[2]</code> (output mẫu), <code className="font-mono">argv[3]</code> (output thí sinh).
                  </div>
                </div>
                <label className="block text-xs font-medium text-zinc-500">
                  Mã nguồn trình chấm (dán code vào ô bên dưới) *
                </label>
                <textarea
                  rows={12}
                  spellCheck={false}
                  value={form.checker_source}
                  onChange={(e) => setForm({ ...form, checker_source: e.target.value })}
                  placeholder={CHECKER_TEMPLATES[form.checker_language]}
                  className="noka-input font-mono text-xs leading-relaxed"
                />
              </div>
            )}
          </div>

          <div className="flex justify-end">
            <button type="submit" disabled={saving} className="noka-btn-primary">
              <Save className="h-4 w-4" /> {saving ? 'Đang lưu...' : isNew ? 'Tạo bài tập' : 'Lưu thay đổi'}
            </button>
          </div>
        </form>
      )}

      {tab === 'testcases' && !isNew && id && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <label className="noka-btn-secondary text-xs cursor-pointer">
                <Upload className="h-3.5 w-3.5" /> Upload ZIP (01.in / 01.out)
                <input type="file" accept=".zip" onChange={handleUploadZip} className="hidden" />
              </label>
              <a href={api.getTestcasesBackupUrl(Number(id))} target="_blank" rel="noreferrer" className="noka-btn-secondary text-xs">
                <Download className="h-3.5 w-3.5" /> Backup ZIP
              </a>
              <button onClick={() => setTab('generator')} className="noka-btn-primary text-xs">
                <Sparkles className="h-3.5 w-3.5" /> Generate Testcases
              </button>
            </div>
            <button onClick={handleSaveAllTestcases} className="noka-btn-secondary text-xs">
              <Save className="h-3.5 w-3.5" /> Save All
            </button>
          </div>

          {zipWarnings.length > 0 && (
            <div className="rounded border border-[#EDB57E] bg-[#FEF4EA] dark:bg-[#2A1E12] p-3 text-xs text-[#945214] dark:text-[#F4CA9E] space-y-1">
              <div className="font-semibold">Cảnh báo ghép cặp ZIP:</div>
              {zipWarnings.map((w, i) => (
                <div key={i}>• {w}</div>
              ))}
            </div>
          )}

          {/* Quick Manual Add */}
          <form onSubmit={handleAddTestcase} className="noka-section p-4 space-y-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Thêm Testcase thủ công</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
              <input value={newTc.name} onChange={(e) => setNewTc({ ...newTc, name: e.target.value })} placeholder="Tên test (VD: 01)" className="noka-input font-mono text-xs" />
              <textarea rows={2} value={newTc.input_data} onChange={(e) => setNewTc({ ...newTc, input_data: e.target.value })} placeholder="Input..." className="noka-input font-mono text-xs" />
              <textarea rows={2} value={newTc.expected_output} onChange={(e) => setNewTc({ ...newTc, expected_output: e.target.value })} placeholder="Expected Output..." className="noka-input font-mono text-xs" />
            </div>
            <div className="flex items-center justify-between">
              <label className="inline-flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={newTc.is_sample} onChange={(e) => setNewTc({ ...newTc, is_sample: e.target.checked })} />
                Đánh dấu là Sample Testcase (học sinh nhìn thấy)
              </label>
              <button type="submit" className="noka-btn-primary text-xs">
                <Plus className="h-3.5 w-3.5" /> Thêm Testcase
              </button>
            </div>
          </form>

          {/* Testcase List */}
          <div className="noka-section overflow-x-auto">
            <table className="noka-table text-xs">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Tên</th>
                  <th>Input Preview</th>
                  <th>Output Preview</th>
                  <th>Sample</th>
                  <th>Hidden</th>
                  <th className="text-right">Dung lượng</th>
                  <th className="text-right">Xóa</th>
                </tr>
              </thead>
              <tbody>
                {testcases.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-6 text-center text-zinc-500">Chưa có testcase nào.</td>
                  </tr>
                ) : (
                  testcases.map((tc, idx) => (
                    <tr key={tc.id}>
                      <td className="font-mono text-zinc-500">{idx + 1}</td>
                      <td className="font-mono font-medium">{tc.name}</td>
                      <td>
                        <pre className="max-w-[220px] truncate font-mono text-[11px] text-zinc-500">{tc.input_preview}</pre>
                      </td>
                      <td>
                        <pre className="max-w-[220px] truncate font-mono text-[11px] text-zinc-500">{tc.output_preview}</pre>
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          checked={tc.is_sample}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            setTestcases((prev) =>
                              prev.map((x) => (x.id === tc.id ? { ...x, is_sample: checked, is_hidden: checked ? false : x.is_hidden } : x))
                            );
                          }}
                        />
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          checked={tc.is_hidden}
                          disabled={tc.is_sample}
                          onChange={(e) => {
                            const checked = e.target.checked;
                            setTestcases((prev) => prev.map((x) => (x.id === tc.id ? { ...x, is_hidden: checked } : x)));
                          }}
                        />
                      </td>
                      <td className="text-right font-mono text-zinc-500">
                        {tc.input_size_bytes}B / {tc.output_size_bytes}B
                      </td>
                      <td className="text-right">
                        <button onClick={() => setDeleteTarget(tc)} className="text-[#9B3558] hover:underline">
                          <Trash2 className="h-3.5 w-3.5 inline" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'generator' && !isNew && id && (
        <TestcaseGeneratorPanel
          problemId={Number(id)}
          onSaved={() => {
            loadTestcases(Number(id));
            setTab('testcases');
          }}
        />
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Xác nhận xóa Testcase"
        description={`Bạn có chắc muốn xóa testcase "${deleteTarget?.name}"? Hành động này không thể hoàn tác.`}
        confirmLabel="Xóa"
        danger
        onConfirm={confirmDeleteTc}
        onCancel={() => setDeleteTarget(null)}
      />

      <ConfirmDialog
        open={confirmDeleteProblem}
        title={`Xóa vĩnh viễn bài tập ${form.code || `#${id}`}?`}
        description="Hành động này sẽ xóa vĩnh viễn đề bài, toàn bộ test case, ảnh đính kèm và lịch sử nộp bài khỏi hệ thống (Neon PostgreSQL & Cloudflare R2) để giải phóng bộ nhớ. Không thể hoàn tác!"
        confirmLabel={deletingProblem ? 'Đang xóa...' : 'Xóa vĩnh viễn'}
        danger
        onConfirm={handleDeleteProblem}
        onCancel={() => !deletingProblem && setConfirmDeleteProblem(false)}
      />
    </div>
  );
};
