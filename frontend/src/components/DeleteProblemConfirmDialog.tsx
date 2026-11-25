import React, { useEffect, useState } from 'react';
import { AlertTriangle, Check, Copy, Trash2, X } from 'lucide-react';

interface DeleteProblemConfirmDialogProps {
  open: boolean;
  problemCode: string;
  problemTitle?: string;
  deleting?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const DeleteProblemConfirmDialog: React.FC<DeleteProblemConfirmDialogProps> = ({
  open,
  problemCode,
  problemTitle,
  deleting = false,
  onConfirm,
  onCancel,
}) => {
  const [typed, setTyped] = useState('');
  const [copied, setCopied] = useState(false);

  const normalizedCode = (problemCode || '').trim() || 'PROBLEM';
  const expectedCode = `XOA ${normalizedCode}`;
  const isMatched = typed === expectedCode;

  useEffect(() => {
    if (open) {
      setTyped('');
      setCopied(false);
    }
  }, [open, problemCode]);

  if (!open) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(expectedCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API unavailable in restricted context
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isMatched || deleting) return;
    onConfirm();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={() => !deleting && onCancel()}
    >
      <div
        className="w-full max-w-md rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-[#14171D] p-5 shadow-xl space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-rose-100 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                Xóa vĩnh viễn bài tập {normalizedCode}
              </h3>
              {problemTitle && (
                <p className="text-xs text-zinc-500 line-clamp-1">{problemTitle}</p>
              )}
            </div>
          </div>
          <button
            type="button"
            disabled={deleting}
            onClick={onCancel}
            className="rounded p-1 text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-40"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="rounded-md border border-rose-300 dark:border-rose-800/80 bg-rose-50 dark:bg-rose-950/35 p-3 text-xs leading-relaxed text-rose-800 dark:text-rose-200">
          <strong>Cảnh báo:</strong> Hành động này sẽ xóa vĩnh viễn đề bài, toàn bộ test case và lịch sử nộp bài của học sinh khỏi cơ sở dữ liệu (Neon PostgreSQL & Cloudflare R2) và <strong>không thể khôi phục</strong>.
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1.5">
            <div className="text-xs text-zinc-600 dark:text-zinc-300">
              Để xác nhận, vui lòng nhập chính xác chuỗi bên dưới:
            </div>
            <div className="flex items-center justify-between gap-2 rounded-md border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-[#101318] px-3 py-2">
              <code className="font-mono text-xs font-bold tracking-wide text-rose-700 dark:text-rose-300 select-all">
                {expectedCode}
              </code>
              <button
                type="button"
                onClick={handleCopy}
                title="Sao chép chuỗi xác nhận"
                className="inline-flex items-center gap-1 rounded border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-2 py-0.5 text-[11px] text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
              >
                {copied ? (
                  <>
                    <Check className="h-3 w-3 text-[#1F6F45] dark:text-[#84CBA3]" /> Đã copy
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" /> Copy
                  </>
                )}
              </button>
            </div>
          </div>

          <div>
            <input
              type="text"
              autoFocus
              autoComplete="off"
              spellCheck={false}
              disabled={deleting}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={`Nhập chính xác: ${expectedCode}`}
              className={`noka-input font-mono text-xs ${
                typed.length > 0 && !isMatched
                  ? 'border-rose-400 focus:border-rose-500'
                  : isMatched
                  ? 'border-emerald-500 focus:border-emerald-600'
                  : ''
              }`}
            />
            {typed.length > 0 && !isMatched && (
              <p className="mt-1 text-[11px] text-rose-600 dark:text-rose-400">
                Chuỗi xác nhận chưa khớp 100% (phân biệt chữ hoa/thường và dấu cách).
              </p>
            )}
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-zinc-200 dark:border-zinc-800">
            <button
              type="button"
              disabled={deleting}
              onClick={onCancel}
              className="noka-btn-secondary text-xs"
            >
              Hủy
            </button>
            <button
              type="submit"
              disabled={!isMatched || deleting}
              className="noka-btn-danger text-xs disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Trash2 className="h-3.5 w-3.5" />
              {deleting ? 'Đang xóa vĩnh viễn...' : 'Xác nhận xóa vĩnh viễn'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
