import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ClipboardPaste, FileText, Loader2, Sparkles, UploadCloud } from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { AutoImportProblemResult } from '../types';

const MAX_FILE_BYTES = 10 * 1024 * 1024; // 10 MB
const ALLOWED_EXTS = ['.docx', '.pdf', '.png', '.jpg', '.jpeg', '.webp'];
const ALLOWED_MIMES = new Set([
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/webp',
]);

interface Props {
  onImported: (result: AutoImportProblemResult) => void;
  disabled?: boolean;
}

export const ProblemAutoImportBox: React.FC<Props> = ({ onImported, disabled = false }) => {
  const { toast } = useApp();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const dropzoneRef = useRef<HTMLDivElement | null>(null);
  const [importing, setImporting] = useState(false);
  const [activeFileName, setActiveFileName] = useState('');
  const [dragging, setDragging] = useState(false);

  const isValidFile = (file: File): string | null => {
    const lowerName = (file.name || '').toLowerCase();
    if (lowerName.endsWith('.doc')) {
      return 'Hệ thống hỗ trợ file Word .docx (không hỗ trợ .doc cũ). Vui lòng lưu lại dưới dạng .docx hoặc .pdf.';
    }
    const extOk = ALLOWED_EXTS.some((ext) => lowerName.endsWith(ext));
    const mimeOk = ALLOWED_MIMES.has((file.type || '').toLowerCase());
    if (!extOk && !mimeOk) {
      return 'Định dạng không hỗ trợ. Vui lòng chọn .docx, .pdf hoặc ảnh (.png, .jpg, .jpeg, .webp).';
    }
    if (file.size === 0) {
      return 'File tải lên bị trống.';
    }
    if (file.size > MAX_FILE_BYTES) {
      return 'File vượt quá dung lượng tối đa 10MB. Vui lòng nén hoặc chọn file nhỏ hơn.';
    }
    return null;
  };

  const processFile = useCallback(
    async (file: File) => {
      if (importing || disabled) return;
      const errMsg = isValidFile(file);
      if (errMsg) {
        toast(errMsg, 'error');
        return;
      }

      setImporting(true);
      setActiveFileName(file.name || 'Ảnh từ Clipboard');
      try {
        const res = await api.autoImportProblem(file);
        onImported(res);
        toast(
          'Đã trích xuất xong đề bài! Vui lòng kiểm tra lại công thức và ví dụ mẫu trước khi lưu.',
          'success'
        );
      } catch (err: any) {
        toast(err.message || 'Không thể bóc tách đề bài. Vui lòng thử lại.', 'error');
      } finally {
        setImporting(false);
        setActiveFileName('');
      }
    },
    [disabled, importing, onImported, toast]
  );

  // Page-level Ctrl+V / Cmd+V listener for pasting problem screenshots directly
  useEffect(() => {
    const handleWindowPaste = (e: ClipboardEvent) => {
      if (importing || disabled) return;
      const items = e.clipboardData?.items;
      if (!items) return;

      let imageFile: File | null = null;
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === 'file' && item.type.startsWith('image/')) {
          imageFile = item.getAsFile();
          if (imageFile) break;
        }
      }
      if (!imageFile) return;

      // Do not hijack paste when teacher is explicitly editing inside a textarea/input
      // (so Ctrl+V inside Statement/Explanation still inserts inline R2 diagrams),
      // unless focus is on this Auto-Import dropzone itself.
      const activeEl = document.activeElement as HTMLElement | null;
      const focusedInsideBox = Boolean(
        dropzoneRef.current && activeEl && dropzoneRef.current.contains(activeEl)
      );
      const focusedInFormField =
        !focusedInsideBox &&
        Boolean(
          activeEl &&
            (activeEl.tagName === 'TEXTAREA' ||
              activeEl.tagName === 'INPUT' ||
              activeEl.isContentEditable)
        );
      if (focusedInFormField) return;

      e.preventDefault();
      processFile(imageFile);
    };

    window.addEventListener('paste', handleWindowPaste);
    return () => window.removeEventListener('paste', handleWindowPaste);
  }, [disabled, importing, processFile]);

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
    if (importing || disabled) return;
    const file = e.dataTransfer?.files?.[0];
    if (file) {
      processFile(file);
    }
  };

  return (
    <div
      ref={dropzoneRef}
      tabIndex={0}
      onDragOver={(e) => {
        e.preventDefault();
        if (!importing && !disabled && !dragging) setDragging(true);
      }}
      onDragLeave={(e) => {
        if (e.currentTarget.contains(e.relatedTarget as Node)) return;
        setDragging(false);
      }}
      onDrop={handleDrop}
      className={`rounded-lg border-2 border-dashed p-4 transition-colors outline-none focus:ring-2 focus:ring-[#2A5C99]/30 dark:focus:ring-[#89B4E8]/30 ${
        dragging
          ? 'border-[#2A5C99] bg-[#2A5C99]/[0.07] dark:border-[#89B4E8] dark:bg-[#89B4E8]/15'
          : 'border-[#2A5C99]/30 dark:border-[#89B4E8]/30 bg-gradient-to-r from-[#2A5C99]/[0.03] to-transparent dark:from-[#89B4E8]/[0.06] dark:to-transparent'
      }`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-[#2A5C99]/10 dark:bg-[#89B4E8]/15 text-[#2A5C99] dark:text-[#89B4E8]">
            {importing ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Sparkles className="h-5 w-5" />
            )}
          </div>
          <div className="space-y-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                Nhập đề bài tự động (AI Auto-Import)
              </h2>
              <span className="rounded bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium text-zinc-500">
                .docx · .pdf · .png · .jpg · .webp (≤ 10MB)
              </span>
            </div>
            {importing ? (
              <p className="text-xs font-medium text-[#2A5C99] dark:text-[#89B4E8]">
                Đang đọc và bóc tách công thức toán học từ tài liệu
                {activeFileName ? ` (${activeFileName})` : ''}...
              </p>
            ) : (
              <p className="text-xs text-zinc-500 leading-relaxed">
                Chọn file, kéo thả vào khung này, hoặc bấm{' '}
                <kbd className="rounded border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-1 py-0.5 font-mono text-[10px] text-zinc-700 dark:text-zinc-300">
                  Ctrl + V
                </kbd>{' '}
                để dán trực tiếp ảnh chụp đề bài (xử lý hoàn toàn trên RAM, không tốn dung lượng lưu trữ).
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            disabled={importing || disabled}
            onClick={() => fileInputRef.current?.click()}
            className="noka-btn-primary text-xs disabled:opacity-50"
          >
            {importing ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Đang bóc tách...
              </>
            ) : (
              <>
                <UploadCloud className="h-3.5 w-3.5" /> Chọn file đề bài
              </>
            )}
          </button>
          <span
            title="Click vào vùng khung hoặc ngoài ô văn bản rồi nhấn Ctrl+V để dán ảnh chụp màn hình đề bài"
            className="hidden md:inline-flex items-center gap-1 rounded border border-zinc-200 dark:border-zinc-700 bg-white/80 dark:bg-zinc-900/70 px-2 py-1.5 text-[11px] text-zinc-500"
          >
            <ClipboardPaste className="h-3.5 w-3.5 text-[#2A5C99] dark:text-[#89B4E8]" />
            Dán ảnh Ctrl+V
          </span>
          <input
            ref={fileInputRef}
            type="file"
            accept=".docx,.pdf,.png,.jpg,.jpeg,.webp,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) processFile(f);
              e.target.value = '';
            }}
          />
        </div>
      </div>

      {dragging && (
        <div className="mt-3 flex items-center justify-center gap-2 rounded border border-[#2A5C99]/30 dark:border-[#89B4E8]/30 bg-white/70 dark:bg-zinc-900/60 py-2 text-xs font-medium text-[#2A5C99] dark:text-[#89B4E8]">
          <FileText className="h-4 w-4" /> Thả file .docx, .pdf hoặc ảnh đề bài vào đây để AI tự động điền form
        </div>
      )}
    </div>
  );
};
