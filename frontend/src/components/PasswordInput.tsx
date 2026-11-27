import React, { useCallback, useRef, useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

export interface PasswordInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  wrapperClassName?: string;
}

export const PasswordInput = React.forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ className = 'noka-input', wrapperClassName = '', disabled, ...props }, forwardedRef) => {
    const [visible, setVisible] = useState(false);
    const internalRef = useRef<HTMLInputElement | null>(null);

    const setRefs = useCallback(
      (node: HTMLInputElement | null) => {
        internalRef.current = node;
        if (typeof forwardedRef === 'function') {
          forwardedRef(node);
        } else if (forwardedRef) {
          forwardedRef.current = node;
        }
      },
      [forwardedRef]
    );

    const handleToggleVisibility = () => {
      const el = internalRef.current;
      const selectionStart = el?.selectionStart ?? null;
      const selectionEnd = el?.selectionEnd ?? null;

      setVisible((prev) => !prev);

      requestAnimationFrame(() => {
        if (!el) return;
        el.focus();
        if (selectionStart !== null && selectionEnd !== null) {
          try {
            el.setSelectionRange(selectionStart, selectionEnd);
          } catch {
            // Some browsers disallow setSelectionRange immediately after type swap
          }
        }
      });
    };

    return (
      <div className={`relative ${wrapperClassName}`}>
        <input
          ref={setRefs}
          type={visible ? 'text' : 'password'}
          disabled={disabled}
          className={`${className} !pr-9`}
          {...props}
        />
        <button
          type="button"
          tabIndex={-1}
          disabled={disabled}
          onMouseDown={(e) => e.preventDefault()}
          onClick={handleToggleVisibility}
          aria-label={visible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
          aria-pressed={visible}
          title={visible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
          className="absolute inset-y-0 right-0 flex items-center justify-center px-2.5 text-zinc-400 hover:text-zinc-700 dark:text-zinc-500 dark:hover:text-zinc-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    );
  }
);

PasswordInput.displayName = 'PasswordInput';
