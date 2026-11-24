import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { BRAND_CONFIG } from '../config/brand';

function resolveImageSrc(src?: string): string | undefined {
  if (!src) return src;
  if (src.startsWith('/api/v1/')) {
    return `${BRAND_CONFIG.apiBaseUrl}${src.slice('/api/v1'.length)}`;
  }
  return src;
}

export const MarkdownLatex: React.FC<{ content: string; className?: string }> = ({
  content,
  className = '',
}) => {
  return (
    <div
      className={`prose prose-sm dark:prose-invert max-w-none leading-relaxed text-zinc-800 dark:text-zinc-200 [&_pre]:rounded-md [&_pre]:border [&_pre]:border-zinc-200 dark:[&_pre]:border-zinc-800 [&_pre]:bg-zinc-50 dark:[&_pre]:bg-[#14171D] [&_pre]:p-3 [&_code]:font-mono ${className}`}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          img: ({ src, alt, ...props }) => (
            <span className="my-3 block text-center">
              <img
                src={resolveImageSrc(src)}
                alt={alt || 'Hình minh họa đề bài'}
                loading="lazy"
                className="mx-auto max-w-full max-h-[560px] rounded-lg border border-zinc-200 dark:border-zinc-800 object-contain shadow-sm"
                {...props}
              />
            </span>
          ),
        }}
      >
        {content || ''}
      </ReactMarkdown>
    </div>
  );
};
