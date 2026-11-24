import React from 'react';

export const VerdictBadge: React.FC<{ verdict: string }> = ({ verdict }) => {
  const v = (verdict || 'PENDING').toUpperCase();
  const styles: Record<string, string> = {
    AC: 'bg-[#EBF7F0] text-[#1F6F45] border-[#84CBA3]/60 dark:bg-[#84CBA3]/15 dark:text-[#98DFB5]',
    OK: 'bg-[#EBF7F0] text-[#1F6F45] border-[#84CBA3]/60 dark:bg-[#84CBA3]/15 dark:text-[#98DFB5]',
    WA: 'bg-[#FDF0F4] text-[#9B3558] border-[#E59CB4]/60 dark:bg-[#E59CB4]/15 dark:text-[#F1B4C8]',
    RE: 'bg-[#FDF0F4] text-[#9B3558] border-[#E59CB4]/60 dark:bg-[#E59CB4]/15 dark:text-[#F1B4C8]',
    TLE: 'bg-[#FEF4EA] text-[#945214] border-[#EDB57E]/60 dark:bg-[#EDB57E]/15 dark:text-[#F3C89A]',
    MLE: 'bg-[#FEF4EA] text-[#945214] border-[#EDB57E]/60 dark:bg-[#EDB57E]/15 dark:text-[#F3C89A]',
    OLE: 'bg-[#FEF4EA] text-[#945214] border-[#EDB57E]/60 dark:bg-[#EDB57E]/15 dark:text-[#F3C89A]',
    CE: 'bg-[#EBF3FC] text-[#2A5C99] border-[#89B4E8]/60 dark:bg-[#89B4E8]/15 dark:text-[#A7C8F0]',
    PENDING: 'bg-zinc-100 text-zinc-600 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700',
    JUDGING: 'bg-[#EBF3FC] text-[#2A5C99] border-[#89B4E8]/60 dark:bg-[#89B4E8]/15 dark:text-[#A7C8F0]',
  };
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 font-mono text-xs font-medium ${
        styles[v] || styles.PENDING
      }`}
    >
      {v}
    </span>
  );
};

export const DifficultyBadge: React.FC<{ difficulty: string }> = ({ difficulty }) => {
  const d = (difficulty || 'easy').toLowerCase();
  const map: Record<string, { label: string; cls: string }> = {
    easy: {
      label: 'Easy',
      cls: 'bg-[#EBF7F0] text-[#1F6F45] border-[#84CBA3]/50 dark:bg-[#84CBA3]/10 dark:text-[#98DFB5]',
    },
    medium: {
      label: 'Medium',
      cls: 'bg-[#FEF4EA] text-[#945214] border-[#EDB57E]/50 dark:bg-[#EDB57E]/10 dark:text-[#F3C89A]',
    },
    hard: {
      label: 'Hard',
      cls: 'bg-[#FDF0F4] text-[#9B3558] border-[#E59CB4]/50 dark:bg-[#E59CB4]/10 dark:text-[#F1B4C8]',
    },
  };
  const cfg = map[d] || map.easy;
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
};
