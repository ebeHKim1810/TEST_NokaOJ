import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

export const MarkdownLatex: React.FC<{ content: string; className?: string }> = ({
  content,
  className = '',
}) => {
  return (
    <div
      className={`prose prose-sm dark:prose-invert max-w-none leading-relaxed text-zinc-800 dark:text-zinc-200 [&_pre]:rounded-md [&_pre]:border [&_pre]:border-zinc-200 dark:[&_pre]:border-zinc-800 [&_pre]:bg-zinc-50 dark:[&_pre]:bg-[#14171D] [&_pre]:p-3 [&_code]:font-mono ${className}`}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {content || ''}
      </ReactMarkdown>
    </div>
  );
};
