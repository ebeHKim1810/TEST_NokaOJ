import React, { useEffect, useState } from 'react';
import { Check, EyeOff, Globe, Lock, Search, Users, X } from 'lucide-react';
import { api } from '../services/api';
import { AllowedUserItem, Visibility } from '../types';

interface Props {
  visibility: Visibility;
  allowedUsers: AllowedUserItem[];
  onVisibilityChange: (next: Visibility) => void;
  onAllowedUsersChange: (next: AllowedUserItem[]) => void;
}

export const ProblemAccessPicker: React.FC<Props> = ({
  visibility,
  allowedUsers,
  onVisibilityChange,
  onAllowedUsersChange,
}) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<AllowedUserItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (visibility !== 'private') return;
    let active = true;
    const t = setTimeout(() => {
      setLoading(true);
      api
        .listUsers(query.trim())
        .then((res) => {
          if (active) setResults(res.items || []);
        })
        .catch(() => {})
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [visibility, query]);

  const selectedIds = new Set(allowedUsers.map((u) => u.id));

  const toggleUser = (u: AllowedUserItem) => {
    if (selectedIds.has(u.id)) {
      onAllowedUsersChange(allowedUsers.filter((x) => x.id !== u.id));
    } else {
      onAllowedUsersChange([...allowedUsers, u]);
    }
  };

  const modes: Array<{
    id: Visibility;
    label: string;
    desc: string;
    icon: React.ReactNode;
  }> = [
    {
      id: 'public',
      label: 'Public (Công khai)',
      desc: 'Tất cả học sinh đều thấy và nộp bài được.',
      icon: <Globe className="h-4 w-4" />,
    },
    {
      id: 'private',
      label: 'Private (Chỉ định học sinh)',
      desc: 'Chỉ các tài khoản được tích chọn bên dưới mới thấy và làm bài.',
      icon: <Lock className="h-4 w-4" />,
    },
    {
      id: 'hidden',
      label: 'Hidden (Ẩn)',
      desc: 'Ẩn hoàn toàn khỏi học sinh; chỉ Admin / Giáo viên nhìn thấy.',
      icon: <EyeOff className="h-4 w-4" />,
    },
  ];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
        {modes.map((m) => {
          const active = visibility === m.id;
          return (
            <button
              key={m.id}
              type="button"
              onClick={() => onVisibilityChange(m.id)}
              className={`flex items-start gap-2.5 rounded-md border p-3 text-left transition-colors ${
                active
                  ? 'border-[#2A5C99] bg-[#2A5C99]/[0.07] dark:border-[#89B4E8] dark:bg-[#89B4E8]/15'
                  : 'border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-800/60'
              }`}
            >
              <span
                className={`mt-0.5 shrink-0 ${
                  active ? 'text-[#2A5C99] dark:text-[#89B4E8]' : 'text-zinc-400'
                }`}
              >
                {m.icon}
              </span>
              <span className="space-y-0.5">
                <span className="block text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                  {m.label}
                </span>
                <span className="block text-[11px] text-zinc-500 leading-snug">{m.desc}</span>
              </span>
            </button>
          );
        })}
      </div>

      {visibility === 'private' && (
        <div className="rounded-md border border-zinc-200 dark:border-zinc-800 p-3 space-y-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-700 dark:text-zinc-300">
              <Users className="h-3.5 w-3.5 text-[#2A5C99] dark:text-[#89B4E8]" />
              Danh sách học sinh được cấp quyền ({allowedUsers.length} đã chọn)
            </div>
            {allowedUsers.length > 0 && (
              <button
                type="button"
                onClick={() => onAllowedUsersChange([])}
                className="text-[11px] text-rose-600 dark:text-rose-400 hover:underline"
              >
                Bỏ chọn tất cả
              </button>
            )}
          </div>

          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.preventDefault();
              }}
              placeholder="Tìm học sinh theo tên, username hoặc email..."
              className="noka-input pl-8 text-xs"
            />
          </div>

          <div className="max-h-44 overflow-y-auto rounded border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-100 dark:divide-zinc-800">
            {loading ? (
              <div className="p-3 text-center text-xs text-zinc-500">Đang tải danh sách tài khoản...</div>
            ) : results.length === 0 ? (
              <div className="p-3 text-center text-xs text-zinc-500">Không tìm thấy tài khoản nào.</div>
            ) : (
              results.map((u) => {
                const picked = selectedIds.has(u.id);
                return (
                  <button
                    type="button"
                    key={u.id}
                    onClick={() => toggleUser(u)}
                    className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800 ${
                      picked ? 'bg-[#2A5C99]/[0.06] dark:bg-[#89B4E8]/10' : ''
                    }`}
                  >
                    <span className="truncate">
                      <span className="font-medium text-zinc-900 dark:text-zinc-100">
                        {u.full_name || u.username}
                      </span>{' '}
                      <span className="font-mono text-zinc-500">@{u.username}</span>
                      {u.email && <span className="text-zinc-400 ml-1.5">({u.email})</span>}
                    </span>
                    <span
                      className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                        picked
                          ? 'border-[#2A5C99] bg-[#2A5C99] text-white dark:border-[#89B4E8] dark:bg-[#89B4E8] dark:text-zinc-950'
                          : 'border-zinc-300 dark:border-zinc-600'
                      }`}
                    >
                      {picked && <Check className="h-3 w-3" />}
                    </span>
                  </button>
                );
              })
            )}
          </div>

          {allowedUsers.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {allowedUsers.map((u) => (
                <span
                  key={u.id}
                  className="inline-flex items-center gap-1 rounded bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-700 dark:text-zinc-200"
                >
                  {u.full_name || u.username}
                  <span className="font-mono text-zinc-400">@{u.username}</span>
                  <button
                    type="button"
                    onClick={() => toggleUser(u)}
                    className="ml-0.5 text-zinc-400 hover:text-rose-600"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
