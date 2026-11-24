import React, { useEffect, useState } from 'react';
import { Play, Download, Save, Upload, CheckSquare, Square } from 'lucide-react';
import { api } from '../../services/api';
import { useApp } from '../../stores/AppContext';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { GenerationBatchResponse, LanguageId } from '../../types';

interface Props {
  problemId: number;
  onSaved: () => void;
}

export const TestcaseGeneratorPanel: React.FC<Props> = ({ problemId, onSaved }) => {
  const { toast } = useApp();
  const [mode, setMode] = useState<'custom_generator' | 'constraints' | 'builtin_template'>('custom_generator');
  const [refLang, setRefLang] = useState<LanguageId>('cpp17');
  const [refCode, setRefCode] = useState('');
  const [genLang, setGenLang] = useState<LanguageId>('python3');
  const [genCode, setGenCode] = useState(
    `import random, sys\ntest_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 1\nseed = int(sys.argv[2]) if len(sys.argv) > 2 else 42\nrng = random.Random(seed)\na = rng.randint(1, 1000 * test_idx)\nb = rng.randint(1, 1000 * test_idx)\nprint(a, b)\n`
  );
  const [numTests, setNumTests] = useState(10);
  const [timeLimitMs, setTimeLimitMs] = useState(2000);
  const [memoryLimitMb, setMemoryLimitMb] = useState(256);
  const [seed, setSeed] = useState('');

  // Mode B schema
  const [schemaJson, setSchemaJson] = useState(
    JSON.stringify(
      {
        fields: [
          { name: 'n', type: 'int', min: 1, max: 50, newline: true },
          { name: 'arr', type: 'array', length_ref: 'n', min: -1000, max: 1000 },
        ],
      },
      null,
      2
    )
  );

  // Mode C templates & randomization
  const [templates, setTemplates] = useState<any[]>([]);
  const [templateId, setTemplateId] = useState('random_array');
  const [nMin, setNMin] = useState(5);
  const [nMax, setNMax] = useState(50);
  const [minVal, setMinVal] = useState(-1000);
  const [maxVal, setMaxVal] = useState(1000);

  const [generating, setGenerating] = useState(false);
  const [batch, setBatch] = useState<GenerationBatchResponse | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [confirmSave, setConfirmSave] = useState(false);

  useEffect(() => {
    api
      .getGeneratorTemplates()
      .then((res) => setTemplates(res.templates || []))
      .catch(() => {});
  }, []);

  const readFileTo = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => setter(String(reader.result || ''));
    reader.readAsText(f);
    e.target.value = '';
  };

  const handleGenerate = async () => {
    if (!refCode.trim()) {
      toast('Vui lòng nhập hoặc tải lên mã nguồn lời giải AC (Reference Solution).', 'warning');
      return;
    }
    setGenerating(true);
    setBatch(null);
    try {
      let parsedSchema = undefined;
      if (mode === 'constraints') {
        parsedSchema = JSON.parse(schemaJson);
      }
      const res: GenerationBatchResponse = await api.generateTestcases({
        problem_id: problemId,
        mode,
        reference_code: refCode,
        reference_language: refLang,
        num_tests: Number(numTests),
        time_limit_ms: Number(timeLimitMs),
        memory_limit_mb: Number(memoryLimitMb),
        seed: seed.trim() ? Number(seed) : undefined,
        generator_code: mode === 'custom_generator' ? genCode : undefined,
        generator_language: mode === 'custom_generator' ? genLang : undefined,
        constraint_schema: parsedSchema,
        template_id: mode === 'builtin_template' ? templateId : undefined,
        template_params:
          mode === 'builtin_template'
            ? { n_min: Number(nMin), n_max: Number(nMax), min_val: Number(minVal), max_val: Number(maxVal) }
            : undefined,
      });
      setBatch(res);
      setSelected(res.items.filter((i) => i.status === 'SUCCESS').map((i) => i.index));
      if (res.reference_compile_error || res.generator_compile_error) {
        toast('Biên dịch thất bại. Kiểm tra thông báo lỗi bên dưới.', 'error');
      } else {
        toast(`Sinh hoàn tất: ${res.success_count}/${res.requested_count} testcase thành công.`, 'success');
      }
    } catch (err: any) {
      toast(err.message, 'error');
    } finally {
      setGenerating(false);
    }
  };

  const handleConfirmSave = async () => {
    if (!batch || selected.length === 0) return;
    setConfirmSave(false);
    try {
      const res = await api.saveGeneratedBatch(batch.batch_id, {
        problem_id: problemId,
        selected_indices: selected,
        is_hidden: true,
        confirmed: true,
      });
      toast(`Đã lưu ${res.saved_count} testcase vào bài tập (không ghi đè test cũ).`, 'success');
      onSaved();
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  const toggleSelect = (idx: number) => {
    setSelected((prev) => (prev.includes(idx) ? prev.filter((x) => x !== idx) : [...prev, idx]));
  };

  return (
    <div className="space-y-5">
      {/* Mode selector */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
        {[
          { id: 'custom_generator', label: 'Mode A: Custom Generator', desc: 'Nhập code Generator + code AC (chính xác & linh hoạt nhất).' },
          { id: 'constraints', label: 'Mode B: Constraints Schema', desc: 'Cấu hình cấu trúc ràng buộc + Validator + code AC.' },
          { id: 'builtin_template', label: 'Mode C: Built-in Templates', desc: '11 mẫu dữ liệu có sẵn + phân bố biên & đặc biệt.' },
        ].map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setMode(m.id as any)}
            className={`text-left rounded-md border p-3 transition-colors ${
              mode === m.id
                ? 'border-[#2A5C99] dark:border-[#89B4E8] bg-[#EBF3FC]/60 dark:bg-[#89B4E8]/10'
                : 'border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-900'
            }`}
          >
            <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{m.label}</div>
            <div className="mt-0.5 text-xs text-zinc-500">{m.desc}</div>
          </button>
        ))}
      </div>

      {/* Common Settings */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <label className="block text-xs font-medium text-zinc-500 mb-1">Số lượng test</label>
          <input type="number" min={1} max={100} value={numTests} onChange={(e) => setNumTests(Number(e.target.value))} className="noka-input font-mono" />
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-500 mb-1">Time Limit (ms)</label>
          <input type="number" min={100} max={15000} value={timeLimitMs} onChange={(e) => setTimeLimitMs(Number(e.target.value))} className="noka-input font-mono" />
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-500 mb-1">Memory Limit (MB)</label>
          <input type="number" min={32} max={1024} value={memoryLimitMb} onChange={(e) => setMemoryLimitMb(Number(e.target.value))} className="noka-input font-mono" />
        </div>
        <div>
          <label className="block text-xs font-medium text-zinc-500 mb-1">Random Seed (tùy chọn)</label>
          <input value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="Auto" className="noka-input font-mono" />
        </div>
      </div>

      {/* Reference Solution (AC) */}
      <div className="noka-section p-4 space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-medium">1. Lời giải chuẩn AC (Reference Solution)</div>
          <div className="flex items-center gap-2">
            <select value={refLang} onChange={(e) => setRefLang(e.target.value as LanguageId)} className="noka-input w-auto text-xs font-mono">
              <option value="cpp17">C++17</option>
              <option value="cpp20">C++20</option>
              <option value="python3">Python 3</option>
            </select>
            <label className="noka-btn-secondary text-xs cursor-pointer">
              <Upload className="h-3.5 w-3.5" /> Tải file code
              <input type="file" onChange={readFileTo(setRefCode)} className="hidden" />
            </label>
          </div>
        </div>
        <textarea
          rows={8}
          value={refCode}
          onChange={(e) => setRefCode(e.target.value)}
          placeholder="Dán mã nguồn lời giải AC chạy trong sandbox để sinh Expected Output..."
          className="noka-input font-mono text-xs"
        />
      </div>

      {/* Mode-specific Input Generator */}
      {mode === 'custom_generator' && (
        <div className="noka-section p-4 space-y-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-medium">2. Mã nguồn Generator (Mode A — nhận argv[1]=test_idx, argv[2]=seed)</div>
            <div className="flex items-center gap-2">
              <select value={genLang} onChange={(e) => setGenLang(e.target.value as LanguageId)} className="noka-input w-auto text-xs font-mono">
                <option value="python3">Python 3</option>
                <option value="cpp17">C++17</option>
                <option value="cpp20">C++20</option>
              </select>
              <label className="noka-btn-secondary text-xs cursor-pointer">
                <Upload className="h-3.5 w-3.5" /> Tải file generator
                <input type="file" onChange={readFileTo(setGenCode)} className="hidden" />
              </label>
            </div>
          </div>
          <textarea
            rows={7}
            value={genCode}
            onChange={(e) => setGenCode(e.target.value)}
            className="noka-input font-mono text-xs"
          />
        </div>
      )}

      {mode === 'constraints' && (
        <div className="noka-section p-4 space-y-2">
          <div className="text-sm font-medium">2. Cấu trúc ràng buộc Input & Validator (Mode B JSON Schema)</div>
          <textarea
            rows={8}
            value={schemaJson}
            onChange={(e) => setSchemaJson(e.target.value)}
            className="noka-input font-mono text-xs"
          />
        </div>
      )}

      {mode === 'builtin_template' && (
        <div className="noka-section p-4 space-y-3">
          <div className="text-sm font-medium">2. Chọn mẫu sinh dữ liệu (Mode C — tự động phân bố biên, lặp, tăng/giảm, ngẫu nhiên)</div>
          <div className="grid grid-cols-1 sm:grid-cols-5 gap-2.5">
            <div className="sm:col-span-2">
              <label className="block text-xs text-zinc-500 mb-1">Template</label>
              <select value={templateId} onChange={(e) => setTemplateId(e.target.value)} className="noka-input text-xs">
                {(templates.length > 0
                  ? templates
                  : [
                      { id: 'random_integer', name: 'Random Integer' },
                      { id: 'random_array', name: 'Random Array' },
                      { id: 'permutation', name: 'Permutation' },
                      { id: 'tree', name: 'Tree' },
                      { id: 'random_graph', name: 'Random Graph' },
                    ]
                ).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">N min / max</label>
              <div className="flex gap-1">
                <input type="number" value={nMin} onChange={(e) => setNMin(Number(e.target.value))} className="noka-input font-mono text-xs" />
                <input type="number" value={nMax} onChange={(e) => setNMax(Number(e.target.value))} className="noka-input font-mono text-xs" />
              </div>
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs text-zinc-500 mb-1">Giá trị min / max</label>
              <div className="flex gap-1">
                <input type="number" value={minVal} onChange={(e) => setMinVal(Number(e.target.value))} className="noka-input font-mono text-xs" />
                <input type="number" value={maxVal} onChange={(e) => setMaxVal(Number(e.target.value))} className="noka-input font-mono text-xs" />
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <button onClick={handleGenerate} disabled={generating} className="noka-btn-primary">
          <Play className="h-4 w-4" /> {generating ? 'Đang chạy sandbox sinh testcase...' : 'Generate Testcases'}
        </button>
      </div>

      {/* Testcase Review Panel */}
      {batch && (
        <div className="noka-section p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 dark:border-zinc-800 pb-3">
            <div className="space-y-0.5">
              <h3 className="text-sm font-semibold">Testcase Review (Seed: {batch.seed})</h3>
              <p className="text-xs font-mono text-zinc-500">
                Yêu cầu: {batch.requested_count} · Thành công: {batch.success_count} · Thất bại: {batch.failed_count} · Thời gian: {batch.duration_ms} ms
              </p>
            </div>
            <div className="flex items-center gap-2">
              <a
                href={api.getBatchDownloadUrl(batch.batch_id)}
                target="_blank"
                rel="noreferrer"
                className="noka-btn-secondary text-xs"
              >
                <Download className="h-3.5 w-3.5" /> Tải ZIP
              </a>
              <button
                onClick={() => setConfirmSave(true)}
                disabled={selected.length === 0}
                className="noka-btn-primary text-xs"
              >
                <Save className="h-3.5 w-3.5" /> Save Selected to Problem ({selected.length})
              </button>
            </div>
          </div>

          {(batch.reference_compile_error || batch.generator_compile_error) && (
            <pre className="rounded bg-[#FDF0F4] dark:bg-[#29151C] p-3 text-xs text-[#9B3558] dark:text-[#F1B4C8] overflow-x-auto">
              {batch.reference_compile_error || batch.generator_compile_error}
            </pre>
          )}

          <div className="overflow-x-auto">
            <table className="noka-table text-xs">
              <thead>
                <tr>
                  <th className="w-10">Chọn</th>
                  <th>Test</th>
                  <th>Nhóm</th>
                  <th>Trạng thái</th>
                  <th>Input Preview</th>
                  <th>Expected Output Preview</th>
                  <th className="text-right">Dung lượng</th>
                </tr>
              </thead>
              <tbody>
                {batch.items.map((item) => {
                  const isSel = selected.includes(item.index);
                  return (
                    <tr key={item.index}>
                      <td>
                        {item.status === 'SUCCESS' && (
                          <button type="button" onClick={() => toggleSelect(item.index)} className="text-[#2A5C99] dark:text-[#89B4E8]">
                            {isSel ? <CheckSquare className="h-4 w-4" /> : <Square className="h-4 w-4 text-zinc-400" />}
                          </button>
                        )}
                      </td>
                      <td className="font-mono">{item.name}</td>
                      <td className="font-mono text-zinc-500">{item.profile}</td>
                      <td>
                        <span
                          className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${
                            item.status === 'SUCCESS'
                              ? 'bg-[#EBF7F0] text-[#1F6F45] dark:bg-[#84CBA3]/15 dark:text-[#98DFB5]'
                              : 'bg-[#FDF0F4] text-[#9B3558] dark:bg-[#E59CB4]/15 dark:text-[#F1B4C8]'
                          }`}
                        >
                          {item.status}
                        </span>
                      </td>
                      <td>
                        <pre className="max-w-xs truncate font-mono text-[11px] text-zinc-600 dark:text-zinc-400">
                          {item.error || item.input_preview}
                        </pre>
                      </td>
                      <td>
                        <pre className="max-w-xs truncate font-mono text-[11px] text-zinc-600 dark:text-zinc-400">
                          {item.output_preview || '—'}
                        </pre>
                      </td>
                      <td className="text-right font-mono text-zinc-500">
                        {item.input_size_bytes}B / {item.output_size_bytes}B
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmSave}
        title="Xác nhận lưu Testcase vào bài tập"
        description={`Bạn có chắc muốn thêm ${selected.length} testcase đã chọn vào bài tập này? Các testcase hiện có sẽ được giữ nguyên và không bị ghi đè.`}
        confirmLabel="Lưu vào bài tập"
        onConfirm={handleConfirmSave}
        onCancel={() => setConfirmSave(false)}
      />
    </div>
  );
};
