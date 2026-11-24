import React, { useEffect, useState } from 'react';
import { Check, Globe, GraduationCap, Search, ShieldCheck, Users, X } from 'lucide-react';
import { api } from '../services/api';
import { ClassroomItem } from '../types';

export interface PickedUser {
  id: number;
  username: string;
  full_name: string;
}

export interface InitialContestAccess {
  mode: 'public' | 'restricted';
  classrooms: ClassroomItem[];
  users: PickedUser[];
}

interface Props {
  value: InitialContestAccess;
  onChange: (next: InitialContestAccess) => void;
}

export const ContestInitialAccessPicker: React.FC<Props> = ({ value, onChange }) => {
  const [allClassrooms, setAllClassrooms] = useState<ClassroomItem[]>([]);
  const [userQuery, setUserQuery] = useState('');
  const [userResults, setUserResults] = useState<PickedUser[]>([]);

  useEffect(() => {
    if (value.mode !== 'restricted') return;
    api
      .listClassrooms()
      .then((r) => setAllClassrooms(r.items || []))
      .catch(() => {});
  }, [value.mode]);

  useEffect(() => {
    if (value.mode !== 'restricted') return;
    const t = setTimeout(() => {
      api
        .listUsers(userQuery.trim())
        .then((r) => setUserResults(r.items || []))
        .catch(() => {});
    }, 200);
    return () => clearTimeout(t);
  }, [value.mode, userQuery]);

  const selectedClassroomIds = new Set(value.classrooms.map((c) => c.id));
  const selectedUserIds = new Set(value.users.map((u) => u.id));

  const toggleClassroom = (cl: ClassroomItem) => {
    if (selectedClassroomIds.has(cl.id)) {
      onChange({ ...value, classrooms: value.classrooms.filter((x) => x.id !== cl.id) });
    } else {
      onChange({ ...value, classrooms: [...value.classrooms, cl] });
    }
  };

  const toggleUser = (u: PickedUser) => {
    if (selectedUserIds.has(u.id)) {
      onChange({ ...value, users: value.users.filter((x) => x.id !== u.id) });
    } else {
      onChange({ ...value, users: [...value.users, u] });
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onChange({ ...value, mode: 'public' })}
          className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
            value.mode === 'public'
              ? 'border-[#2A5C99] bg-[#2A5C99]/10 text-[#2A5C99] dark:border-[#89B4E8] dark:bg-[#89B4E8]/15 dark:text-[#89B4E8]'
              : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800'
          }`}
        >
          <Globe className="h-3.5 w-3.5" /> Công khai (Tất cả mọi người)
        </button>
        <button
          type="button"
          onClick={() => onChange({ ...value, mode: 'restricted' })}
          className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
            value.mode === 'restricted'
              ? 'border-[#2A5C99] bg-[#2A5C99]/10 text-[#2A5C99] dark:border-[#89B4E8] dark:bg-[#89B4E8]/15 dark:text-[#89B4E8]'
              : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50 dark:hover:bg-zinc-800'
          }`}
        >
          <ShieldCheck className="h-3.5 w-3.5" /> Chỉ định học sinh / lớp học
        </button>
      </div>

      {value.mode === 'restricted' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 rounded-md border border-zinc-200 dark:border-zinc-800 p-3">
          {/* Classrooms picker */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-600 dark:text-zinc-300">
              <GraduationCap className="h-3.5 w-3.5 text-[#2A5C99] dark:text-[#89B4E8]" />
              Chọn lớp học (tất cả học sinh trong lớp) — đã chọn {value.classrooms.length}
            </div>
            <div className="max-h-44 overflow-y-auto rounded border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-100 dark:divide-zinc-800">
              {allClassrooms.length === 0 ? (
                <div className="p-3 text-center text-xs text-zinc-500">Chưa có lớp học nào.</div>
              ) : (
                allClassrooms.map((cl) => {
                  const picked = selectedClassroomIds.has(cl.id);
                  return (
                    <button
                      type="button"
                      key={cl.id}
                      onClick={() => toggleClassroom(cl)}
                      className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800 ${
                        picked ? 'bg-[#2A5C99]/5 dark:bg-[#89B4E8]/10' : ''
                      }`}
                    >
                      <span className="truncate">
                        <span className="font-medium">{cl.name}</span>{' '}
                        <span className="text-zinc-500">({cl.student_count} học sinh)</span>
                      </span>
                      {picked && <Check className="h-3.5 w-3.5 shrink-0 text-[#2A5C99] dark:text-[#89B4E8]" />}
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* Individual students picker */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-zinc-600 dark:text-zinc-300">
              <Users className="h-3.5 w-3.5 text-[#2A5C99] dark:text-[#89B4E8]" />
              Chọn học sinh cụ thể — đã chọn {value.users.length}
            </div>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400" />
              <input
                value={userQuery}
                onChange={(e) => setUserQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') e.preventDefault();
                }}
                placeholder="Tìm theo tên, username hoặc email..."
                className="noka-input pl-8 text-xs"
              />
            </div>
            <div className="max-h-36 overflow-y-auto rounded border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-100 dark:divide-zinc-800">
              {userResults.length === 0 ? (
                <div className="p-3 text-center text-xs text-zinc-500">Không tìm thấy tài khoản.</div>
              ) : (
                userResults.map((u) => {
                  const picked = selectedUserIds.has(u.id);
                  return (
                    <button
                      type="button"
                      key={u.id}
                      onClick={() => toggleUser(u)}
                      className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800 ${
                        picked ? 'bg-[#2A5C99]/5 dark:bg-[#89B4E8]/10' : ''
                      }`}
                    >
                      <span className="truncate">
                        <span className="font-medium">{u.full_name || u.username}</span>{' '}
                        <span className="font-mono text-zinc-500">@{u.username}</span>
                      </span>
                      {picked && <Check className="h-3.5 w-3.5 shrink-0 text-[#2A5C99] dark:text-[#89B4E8]" />}
                    </button>
                  );
                })
              )}
            </div>
            {value.users.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {value.users.map((u) => (
                  <span
                    key={u.id}
                    className="inline-flex items-center gap-1 rounded bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 text-[11px]"
                  >
                    {u.full_name || u.username}
                    <button
                      type="button"
                      onClick={() => toggleUser(u)}
                      className="text-zinc-400 hover:text-red-600"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
