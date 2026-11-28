import React, { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Check, Search, X } from 'lucide-react';
import { api } from '../services/api';

export interface PickedProblem {
  id: number;
  code: string;
  title: string;
  difficulty?: string;
  visibility?: string;
}

interface Props {
  value: PickedProblem[];
  onChange: (next: PickedProblem[]) => void;
}

const labelOf = (idx: number) => String.fromCharCode(65 + idx);

const VISIBILITY_BADGE: Record<string, { label: string; cls: string }> = {
  hidden: {
    label: 'Ẩn',
    cls: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
  },
  private: {
    label: 'Chỉ định',
    cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  },
  classroom: {
    label: 'Lớp học',
    cls: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
  },
};

/**
 * Lets staff pick contest problems by clicking them in a searchable list
 * (search by numeric ID, problem code or title, including hidden/private problems)
 * instead of typing IDs manually.
 */
export const ContestProblemPicker: React.FC<Props> = ({ value, onChange }) => {
  const [query, setQuery] = useState('');
  const [visibilityFilter, setVisibilityFilter] = useState('');
  const [results, setResults] = useState<PickedProblem[]>([]);
  const [loading, setLoading] = useState(false);
  const reqSeq = useRef(0);

  useEffect(() => {
    const seq = ++reqSeq.current;
    const q = query.trim();
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const listPromise = api
          .listProblems({
            search: q,
            visibility: visibilityFilter || undefined,
            page_size: 100,
          })
          .then((r) => (r.items || []) as PickedProblem[])
          .catch(() => [] as PickedProblem[]);
        // Backend search matches code/title only, so also look up an exact numeric ID.
        const idPromise = /^\d+$/.test(q)
          ? api
              .getProblem(Number(q))
              .then((p) => (p && typeof p.id === 'number' ? [p as PickedProblem] : []))
              .catch(() => [] as PickedProblem[])
          : Promise.resolve([] as PickedProblem[]);
        const [byId, list] = await Promise.all([idPromise, listPromise]);
        if (seq !== reqSeq.current) return;
        const seen = new Set<number>();
        const merged: PickedProblem[] = [];
        [...byId, ...list].forEach((p) => {
          if (!seen.has(p.id)) {
            seen.add(p.id);
            merged.push({
              id: p.id,
              code: p.code,
              title: p.title,
              difficulty: p.difficulty,
              visibility: p.visibility,
            });
          }
        });
        setResults(merged);
      } finally {
        if (seq === reqSeq.current) setLoading(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [query, visibilityFilter]);

  const selectedIds = new Set(value.map((p) => p.id));

  const toggle = (p: PickedProblem) => {
    if (selectedIds.has(p.id)) onChange(value.filter((x) => x.id !== p.id));
    else onChange([...value, p]);
  };

  const move = (idx: number, dir: -1 | 1) => {
    const j = idx + dir;
    if (j < 0 || j >= value.length) return;
    const next = [...value];
    [next[idx], next[j]] = [next[j], next[idx]];
    onChange(next);
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {/* Search & click-to-add */}
      <div>
        <div className="mb-2 flex gap-1.5">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  // Prevent submitting the contest form; add the first result instead.
                  e.preventDefault();
                  const first = results.find((r) => !selectedIds.has(r.id));
                  if (first) toggle(first);
                }
              }}
              placeholder="Tìm theo ID, mã hoặc tên bài..."
              className="noka-input pl-8"
            />
          </div>
          <select
            value={visibilityFilter}
            onChange={(e) => setVisibilityFilter(e.target.value)}
            aria-label="Lọc theo trạng thái hiển thị bài tập"
            className="noka-input w-32 shrink-0 text-xs"
          >
            <option value="">Tất cả</option>
            <option value="hidden">Ẩn (Hidden)</option>
            <option value="private">Chỉ định</option>
            <option value="public">Công khai</option>
          </select>
        </div>
        <div className="max-h-64 overflow-y-auto rounded border border-zinc-200 dark:border-zinc-700">
          {loading && results.length === 0 ? (
            <div className="p-3 text-center text-xs text-zinc-500">Đang tải...</div>
          ) : results.length === 0 ? (
            <div className="p-3 text-center text-xs text-zinc-500">Không tìm thấy bài tập.</div>
          ) : (
            results.map((p) => {
              const picked = selectedIds.has(p.id);
              const visBadge = p.visibility ? VISIBILITY_BADGE[p.visibility] : undefined;
              return (
                <button
                  type="button"
                  key={p.id}
                  onClick={() => toggle(p)}
                  className={`flex w-full items-center gap-2 border-b border-zinc-100 dark:border-zinc-800 px-3 py-1.5 text-left text-sm last:border-b-0 hover:bg-zinc-50 dark:hover:bg-zinc-800 ${
                    picked ? 'bg-[#2A5C99]/5 dark:bg-[#89B4E8]/10' : ''
                  }`}
                  title={picked ? 'Bỏ chọn' : 'Thêm vào kỳ thi'}
                >
                  <span className="w-10 shrink-0 font-mono text-xs text-zinc-400">#{p.id}</span>
                  <span className="w-20 shrink-0 truncate font-mono text-xs">{p.code}</span>
                  <span className="flex-1 truncate">{p.title}</span>
                  {visBadge && (
                    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${visBadge.cls}`}>
                      {visBadge.label}
                    </span>
                  )}
                  {picked && <Check className="h-4 w-4 shrink-0 text-[#2A5C99] dark:text-[#89B4E8]" />}
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Selected problems (ordered A, B, C...) */}
      <div>
        <div className="mb-2 text-xs text-zinc-500">Đã chọn: {value.length} bài</div>
        <div className="max-h-[17.5rem] overflow-y-auto rounded border border-zinc-200 dark:border-zinc-700">
          {value.length === 0 ? (
            <div className="p-3 text-center text-xs text-zinc-500">Chưa chọn bài nào. Click vào bài ở danh sách bên trái để thêm.</div>
          ) : (
            value.map((p, idx) => {
              const visBadge = p.visibility ? VISIBILITY_BADGE[p.visibility] : undefined;
              return (
                <div
                  key={p.id}
                  className="flex items-center gap-2 border-b border-zinc-100 dark:border-zinc-800 px-3 py-1.5 text-sm last:border-b-0"
                >
                  <span className="w-6 shrink-0 font-mono font-semibold">{labelOf(idx)}</span>
                  <span className="w-20 shrink-0 truncate font-mono text-xs">{p.code}</span>
                  <span className="flex-1 truncate">{p.title}</span>
                  {visBadge && (
                    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${visBadge.cls}`}>
                      {visBadge.label}
                    </span>
                  )}
                  <button type="button" onClick={() => move(idx, -1)} disabled={idx === 0} className="p-0.5 text-zinc-400 hover:text-zinc-700 disabled:opacity-30" title="Lên">
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                  <button type="button" onClick={() => move(idx, 1)} disabled={idx === value.length - 1} className="p-0.5 text-zinc-400 hover:text-zinc-700 disabled:opacity-30" title="Xuống">
                    <ArrowDown className="h-3.5 w-3.5" />
                  </button>
                  <button type="button" onClick={() => toggle(p)} className="p-0.5 text-zinc-400 hover:text-red-600" title="Bỏ chọn">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
