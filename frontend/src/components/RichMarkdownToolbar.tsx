import React, { useRef, useState } from 'react';
import { Eye, ImagePlus, Loader2, UploadCloud } from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { MarkdownLatex } from './MarkdownLatex';

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const ALLOWED_MIME_TYPES = new Set(['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif']);

/**
 * Detects whether the caret at `pos` lies inside an unescaped `$...$` or `$$...$$` math span.
 */
export function isInsideMathMode(text: string, pos: number): boolean {
  let mode: 'none' | 'inline' | 'display' = 'none';
  let i = 0;
  const limit = Math.min(pos, text.length);
  while (i < limit) {
    const ch = text[i];
    if (ch === '\\') {
      i += 2;
      continue;
    }
    if (ch === '$') {
      if (i + 1 < limit && text[i + 1] === '$') {
        if (mode === 'display') mode = 'none';
        else if (mode === 'none') mode = 'display';
        i += 2;
        continue;
      }
      if (mode === 'inline') mode = 'none';
      else if (mode === 'none') mode = 'inline';
    }
    i += 1;
  }
  return mode !== 'none';
}

export type FormatAction = 'bold' | 'italic' | 'sup' | 'sub' | 'frac' | 'sqrt';

export function computeFormattedEdit(
  value: string,
  selStart: number,
  selEnd: number,
  action: FormatAction
): { nextValue: string; nextSelStart: number; nextSelEnd: number } {
  const before = value.slice(0, selStart);
  const selected = value.slice(selStart, selEnd);
  const after = value.slice(selEnd);
  const inMath = isInsideMathMode(value, selStart);

  if (action === 'bold') {
    if (selected) {
      const inserted = `**${selected}**`;
      return {
        nextValue: before + inserted + after,
        nextSelStart: selStart + 2,
        nextSelEnd: selStart + 2 + selected.length,
      };
    }
    const placeholder = 'văn bản';
    return {
      nextValue: `${before}**${placeholder}**${after}`,
      nextSelStart: selStart + 2,
      nextSelEnd: selStart + 2 + placeholder.length,
    };
  }

  if (action === 'italic') {
    if (selected) {
      const inserted = `*${selected}*`;
      return {
        nextValue: before + inserted + after,
        nextSelStart: selStart + 1,
        nextSelEnd: selStart + 1 + selected.length,
      };
    }
    const placeholder = 'văn bản';
    return {
      nextValue: `${before}*${placeholder}*${after}`,
      nextSelStart: selStart + 1,
      nextSelEnd: selStart + 1 + placeholder.length,
    };
  }

  const wrapMath = (expr: string, caretOffset: number) => {
    if (inMath) {
      return {
        nextValue: before + expr + after,
        nextSelStart: selStart + caretOffset,
        nextSelEnd: selStart + caretOffset,
      };
    }
    const wrapped = `$${expr}$`;
    // If caret is meant to be at the very end of the expression, place it after closing '$'
    const finalOffset = caretOffset === expr.length ? wrapped.length : caretOffset + 1;
    return {
      nextValue: before + wrapped + after,
      nextSelStart: selStart + finalOffset,
      nextSelEnd: selStart + finalOffset,
    };
  };

  if (action === 'sup') {
    if (selected) {
      const expr = `^{${selected}}`;
      return wrapMath(expr, expr.length);
    }
    return wrapMath('^{}', 2);
  }

  if (action === 'sub') {
    if (selected) {
      const expr = `_{${selected}}`;
      return wrapMath(expr, expr.length);
    }
    return wrapMath('_{}', 2);
  }

  if (action === 'frac') {
    if (selected) {
      const slashIdx = selected.indexOf('/');
      if (slashIdx !== -1) {
        const num = selected.slice(0, slashIdx).trim();
        const den = selected.slice(slashIdx + 1).trim();
        const expr = `\\frac{${num}}{${den}}`;
        const caret = den ? expr.length : `\\frac{${num}}{`.length;
        return wrapMath(expr, caret);
      }
      const expr = `\\frac{${selected}}{}`;
      return wrapMath(expr, `\\frac{${selected}}{`.length);
    }
    return wrapMath('\\frac{}{}', '\\frac{'.length);
  }

  // sqrt
  if (selected) {
    const expr = `\\sqrt{${selected}}`;
    return wrapMath(expr, expr.length);
  }
  return wrapMath('\\sqrt{}', '\\sqrt{'.length);
}

interface ToolbarProps {
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  uploading?: boolean;
  onSelectImageFile: (file: File) => void;
}

export const RichMarkdownToolbar: React.FC<ToolbarProps> = ({
  textareaRef,
  value,
  onChange,
  disabled = false,
  uploading = false,
  onSelectImageFile,
}) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const applyFormat = (action: FormatAction) => {
    if (disabled) return;
    const el = textareaRef.current;
    const start = el ? el.selectionStart : value.length;
    const end = el ? el.selectionEnd : value.length;
    const prevScrollTop = el ? el.scrollTop : 0;

    const { nextValue, nextSelStart, nextSelEnd } = computeFormattedEdit(value, start, end, action);
    onChange(nextValue);

    requestAnimationFrame(() => {
      if (!el) return;
      el.focus({ preventScroll: true });
      el.setSelectionRange(nextSelStart, nextSelEnd);
      el.scrollTop = prevScrollTop;
    });
  };

  const btnCls =
    'inline-flex h-7 min-w-[28px] items-center justify-center rounded border border-transparent px-2 text-xs text-zinc-700 dark:text-zinc-200 hover:border-zinc-200 dark:hover:border-zinc-700 hover:bg-white dark:hover:bg-zinc-800 disabled:opacity-40 transition-colors';

  return (
    <div className="flex flex-wrap items-center justify-between gap-1.5 rounded-t-md border border-b-0 border-zinc-200 dark:border-zinc-800 bg-zinc-50/80 dark:bg-[#15181E] px-2 py-1.5">
      <div className="flex flex-wrap items-center gap-0.5">
        <button
          type="button"
          disabled={disabled}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => applyFormat('bold')}
          title="In đậm (Ctrl+B)"
          className={`${btnCls} font-bold`}
        >
          B
        </button>
        <button
          type="button"
          disabled={disabled}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => applyFormat('italic')}
          title="In nghiêng (Ctrl+I)"
          className={`${btnCls} italic font-serif`}
        >
          I
        </button>

        <span className="mx-1 h-4 w-px bg-zinc-200 dark:bg-zinc-700" />

        <button
          type="button"
          disabled={disabled}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => applyFormat('sup')}
          title="Số mũ (LaTeX: ^{n})"
          className={`${btnCls} font-mono`}
        >
          x<sup className="text-[9px] ml-0.5">2</sup>
        </button>
        <button
          type="button"
          disabled={disabled}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => applyFormat('sub')}
          title="Chỉ số dưới (LaTeX: _{n})"
          className={`${btnCls} font-mono`}
        >
          x<sub className="text-[9px] ml-0.5">2</sub>
        </button>
        <button
          type="button"
          disabled={disabled}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => applyFormat('frac')}
          title="Phân số (LaTeX: \frac{a}{b} — bôi đen dạng a/b sẽ tự tách)"
          className={`${btnCls} font-mono`}
        >
          a/b
        </button>
        <button
          type="button"
          disabled={disabled}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => applyFormat('sqrt')}
          title="Căn bậc hai (LaTeX: \sqrt{x})"
          className={`${btnCls} font-mono`}
        >
          √x
        </button>

        <span className="mx-1 h-4 w-px bg-zinc-200 dark:bg-zinc-700" />

        <button
          type="button"
          disabled={disabled || uploading}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => fileInputRef.current?.click()}
          title="Tải ảnh lên Cloudflare R2 và chèn vào vị trí con trỏ (tối đa 5MB)"
          className={`${btnCls} gap-1.5 font-medium text-[#2A5C99] dark:text-[#89B4E8]`}
        >
          {uploading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ImagePlus className="h-3.5 w-3.5" />
          )}
          <span>{uploading ? 'Đang tải ảnh...' : 'Chèn ảnh'}</span>
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onSelectImageFile(file);
            e.target.value = '';
          }}
        />
      </div>

      <span className="hidden sm:inline text-[11px] text-zinc-400">
        Hỗ trợ dán ảnh (Ctrl+V) & kéo thả ảnh (tối đa 5MB)
      </span>
    </div>
  );
};

interface RichMarkdownFieldProps {
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  rows?: number;
  previewOpen?: boolean;
  onTogglePreview?: () => void;
  emptyPreviewText?: string;
}

export const RichMarkdownField: React.FC<RichMarkdownFieldProps> = ({
  label,
  value,
  onChange,
  placeholder,
  rows = 8,
  previewOpen,
  onTogglePreview,
  emptyPreviewText = 'Chưa có nội dung để xem trước.',
}) => {
  const { toast } = useApp();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const latestValueRef = useRef(value);
  latestValueRef.current = value;

  const [internalPreview, setInternalPreview] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);

  const isPreview = previewOpen !== undefined ? previewOpen : internalPreview;
  const togglePreview = onTogglePreview || (() => setInternalPreview((v) => !v));

  const uploadAndInsertImage = async (file: File) => {
    const mime = (file.type || '').toLowerCase();
    if (!ALLOWED_MIME_TYPES.has(mime)) {
      toast('Chỉ chấp nhận định dạng ảnh PNG, JPEG, WEBP hoặc GIF.', 'error');
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      toast('Ảnh vượt quá dung lượng tối đa 5MB.', 'error');
      return;
    }

    const el = textareaRef.current;
    const savedStart = el ? el.selectionStart : latestValueRef.current.length;
    const savedEnd = el ? el.selectionEnd : latestValueRef.current.length;
    const savedScrollTop = el ? el.scrollTop : 0;

    setUploading(true);
    try {
      const res = await api.uploadProblemImage(file);
      const rawName = (file.name || '').replace(/\.[^.]+$/, '').replace(/[\[\]]/g, '').trim();
      const alt = rawName && rawName.toLowerCase() !== 'image' ? rawName : 'Mô tả ảnh';
      const markdown = `![${alt}](${res.url})`;

      const currentVal = latestValueRef.current;
      const safeStart = Math.min(savedStart, currentVal.length);
      const safeEnd = Math.min(savedEnd, currentVal.length);
      const nextValue = currentVal.slice(0, safeStart) + markdown + currentVal.slice(safeEnd);
      const nextCaret = safeStart + markdown.length;

      onChange(nextValue);
      toast('Đã tải ảnh lên Cloudflare R2 và chèn vào đề bài.', 'success');

      requestAnimationFrame(() => {
        if (!el) return;
        el.focus({ preventScroll: true });
        el.setSelectionRange(nextCaret, nextCaret);
        el.scrollTop = savedScrollTop;
      });
    } catch (err: any) {
      toast(err.message || 'Không thể tải ảnh lên. Vui lòng thử lại.', 'error');
    } finally {
      setUploading(false);
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind === 'file' && item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          e.preventDefault();
          uploadAndInsertImage(file);
          return;
        }
      }
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
    const files = e.dataTransfer?.files;
    if (!files || files.length === 0) return;
    for (let i = 0; i < files.length; i++) {
      if (files[i].type.startsWith('image/')) {
        uploadAndInsertImage(files[i]);
        return;
      }
    }
    toast('Vui lòng kéo thả file ảnh (PNG, JPEG, WEBP, GIF).', 'warning');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    const key = e.key.toLowerCase();
    if (key === 'b' || key === 'i') {
      e.preventDefault();
      const el = textareaRef.current;
      const start = el ? el.selectionStart : value.length;
      const end = el ? el.selectionEnd : value.length;
      const prevScrollTop = el ? el.scrollTop : 0;
      const { nextValue, nextSelStart, nextSelEnd } = computeFormattedEdit(
        value,
        start,
        end,
        key === 'b' ? 'bold' : 'italic'
      );
      onChange(nextValue);
      requestAnimationFrame(() => {
        if (!el) return;
        el.focus({ preventScroll: true });
        el.setSelectionRange(nextSelStart, nextSelEnd);
        el.scrollTop = prevScrollTop;
      });
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
          {label}
        </span>
        <button type="button" onClick={togglePreview} className="noka-btn-secondary text-xs">
          <Eye className="h-3.5 w-3.5" /> {isPreview ? 'Chỉnh sửa' : 'Xem trước (Preview)'}
        </button>
      </div>

      {isPreview ? (
        <div className="min-h-[140px] rounded-md border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-[#12151B] p-4">
          {value.trim() ? (
            <MarkdownLatex content={value} />
          ) : (
            <p className="text-xs italic text-zinc-400">{emptyPreviewText}</p>
          )}
        </div>
      ) : (
        <div
          className="relative"
          onDragOver={(e) => {
            e.preventDefault();
            if (!dragging) setDragging(true);
          }}
          onDragLeave={(e) => {
            if (e.currentTarget.contains(e.relatedTarget as Node)) return;
            setDragging(false);
          }}
          onDrop={handleDrop}
        >
          <RichMarkdownToolbar
            textareaRef={textareaRef}
            value={value}
            onChange={onChange}
            uploading={uploading}
            onSelectImageFile={uploadAndInsertImage}
          />
          <textarea
            ref={textareaRef}
            rows={rows}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onPaste={handlePaste}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            className="noka-input rounded-t-none font-mono text-xs leading-relaxed"
          />
          {dragging && (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1.5 rounded-md border-2 border-dashed border-[#2A5C99] dark:border-[#89B4E8] bg-[#2A5C99]/10 dark:bg-[#89B4E8]/15 backdrop-blur-[1px]">
              <UploadCloud className="h-6 w-6 text-[#2A5C99] dark:text-[#89B4E8]" />
              <span className="text-xs font-semibold text-[#2A5C99] dark:text-[#89B4E8]">
                Thả ảnh vào đây để tải lên và chèn vào vị trí con trỏ
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
