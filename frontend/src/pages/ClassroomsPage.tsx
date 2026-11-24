import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Plus, Upload, UserPlus, KeyRound } from 'lucide-react';
import { api } from '../services/api';
import { useApp } from '../stores/AppContext';
import { ClassroomItem } from '../types';

export const ClassroomsPage: React.FC = () => {
  const { isStaff, toast } = useApp();
  const [items, setItems] = useState<ClassroomItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [joinCode, setJoinCode] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  const load = () => {
    setLoading(true);
    api.listClassrooms().then((r) => setItems(r.items || [])).finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.joinClassroom(joinCode.trim());
      toast('Đã tham gia lớp học.', 'success');
      setJoinCode('');
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createClassroom({ name, description });
      toast('Đã tạo lớp học mới.', 'success');
      setName('');
      setDescription('');
      setShowCreate(false);
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Lớp học (Classrooms)</h1>
        <div className="flex items-center gap-2">
          <form onSubmit={handleJoin} className="flex items-center gap-1.5">
            <input
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value)}
              placeholder="Nhập mã lớp..."
              className="noka-input w-36 font-mono text-xs uppercase"
            />
            <button type="submit" disabled={!joinCode.trim()} className="noka-btn-secondary text-xs">
              <KeyRound className="h-3.5 w-3.5" /> Tham gia
            </button>
          </form>
          {isStaff && (
            <button onClick={() => setShowCreate((v) => !v)} className="noka-btn-primary text-xs">
              <Plus className="h-3.5 w-3.5" /> Tạo lớp học
            </button>
          )}
        </div>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="noka-section p-4 space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Tên lớp (VD: Tin học 11A1)" className="noka-input" />
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Mô tả ngắn..." className="noka-input" />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowCreate(false)} className="noka-btn-secondary">Hủy</button>
            <button type="submit" className="noka-btn-primary">Tạo lớp</button>
          </div>
        </form>
      )}

      <div className="noka-section overflow-x-auto">
        {loading ? (
          <div className="p-8 text-center text-sm text-zinc-500">Đang tải...</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-sm text-zinc-500">Bạn chưa tham gia lớp học nào.</div>
        ) : (
          <table className="noka-table">
            <thead>
              <tr>
                <th>Tên lớp</th>
                <th>Mã tham gia</th>
                <th>Giáo viên</th>
                <th className="text-right">Học sinh</th>
                <th className="text-right">Bài giao</th>
                <th className="text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id}>
                  <td className="font-medium">
                    <Link to={`/classrooms/${c.id}`} className="hover:text-[#2A5C99] dark:hover:text-[#89B4E8]">
                      {c.name}
                    </Link>
                  </td>
                  <td className="font-mono text-xs">{c.join_code}</td>
                  <td className="text-zinc-500">{c.teacher_name || c.teacher_username || '—'}</td>
                  <td className="text-right font-mono text-xs">{c.student_count}</td>
                  <td className="text-right font-mono text-xs">{c.assignment_count}</td>
                  <td className="text-right">
                    <Link to={`/classrooms/${c.id}`} className="text-xs font-medium text-[#2A5C99] dark:text-[#89B4E8] hover:underline">
                      Mở lớp
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export const ClassroomDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { isStaff, toast } = useApp();
  const [cls, setCls] = useState<any>(null);
  const [progress, setProgress] = useState<any>(null);
  const [studentQuery, setStudentQuery] = useState('');
  const [assignForm, setAssignForm] = useState({ title: '', due_at: '', problem_ids: '' });

  const load = () => {
    if (!id) return;
    api.getClassroom(id).then(setCls).catch((e) => toast(e.message, 'error'));
    if (isStaff) {
      api.getClassroomProgress(id).then(setProgress).catch(() => {});
    }
  };

  useEffect(() => {
    load();
  }, [id, isStaff]);

  const handleAddStudent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    try {
      await api.addStudent(Number(id), studentQuery.trim());
      toast('Đã thêm học sinh vào lớp.', 'success');
      setStudentQuery('');
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !id) return;
    try {
      const res = await api.importStudents(Number(id), file);
      toast(`Đã thêm ${res.enrolled_count} học sinh (tạo mới ${res.created_accounts} tài khoản).`, 'success');
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    }
    e.target.value = '';
  };

  const handleCreateAssignment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    try {
      const pids = assignForm.problem_ids.split(',').map((x) => Number(x.trim())).filter(Boolean);
      await api.createAssignment({
        classroom_id: Number(id),
        title: assignForm.title,
        due_at: assignForm.due_at ? new Date(assignForm.due_at).toISOString() : null,
        problem_ids: pids,
      });
      toast('Đã giao bài tập cho lớp.', 'success');
      setAssignForm({ title: '', due_at: '', problem_ids: '' });
      load();
    } catch (err: any) {
      toast(err.message, 'error');
    }
  };

  if (!cls) return <div className="py-12 text-center text-sm text-zinc-500">Đang tải lớp học...</div>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 dark:border-zinc-800 pb-4">
        <div>
          <h1 className="text-xl font-semibold">{cls.name}</h1>
          <p className="mt-1 text-xs text-zinc-500">
            Mã tham gia lớp: <span className="font-mono font-semibold text-zinc-900 dark:text-zinc-100">{cls.join_code}</span>
          </p>
        </div>
        {isStaff && (
          <div className="flex flex-wrap items-center gap-2">
            <form onSubmit={handleAddStudent} className="flex gap-1.5">
              <input
                value={studentQuery}
                onChange={(e) => setStudentQuery(e.target.value)}
                placeholder="Username / Email học sinh"
                className="noka-input w-48 text-xs"
              />
              <button type="submit" disabled={!studentQuery.trim()} className="noka-btn-secondary text-xs">
                <UserPlus className="h-3.5 w-3.5" /> Thêm
              </button>
            </form>
            <label className="noka-btn-secondary text-xs cursor-pointer">
              <Upload className="h-3.5 w-3.5" /> Import CSV/Excel
              <input type="file" accept=".csv,.xlsx" onChange={handleImportFile} className="hidden" />
            </label>
          </div>
        )}
      </div>

      {/* Assignments */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Bài tập được giao</h2>
        {isStaff && (
          <form onSubmit={handleCreateAssignment} className="noka-section p-3.5 grid grid-cols-1 md:grid-cols-4 gap-2.5">
            <input
              required
              value={assignForm.title}
              onChange={(e) => setAssignForm({ ...assignForm, title: e.target.value })}
              placeholder="Tên đợt bài tập..."
              className="noka-input text-xs"
            />
            <input
              value={assignForm.problem_ids}
              onChange={(e) => setAssignForm({ ...assignForm, problem_ids: e.target.value })}
              placeholder="ID bài tập (VD: 1,2)"
              className="noka-input text-xs font-mono"
            />
            <input
              type="datetime-local"
              value={assignForm.due_at}
              onChange={(e) => setAssignForm({ ...assignForm, due_at: e.target.value })}
              className="noka-input text-xs"
            />
            <button type="submit" className="noka-btn-primary text-xs">Giao bài</button>
          </form>
        )}

        <div className="noka-section divide-y divide-zinc-100 dark:divide-zinc-800">
          {(cls.assignments || []).length === 0 ? (
            <div className="p-6 text-center text-sm text-zinc-500">Chưa có bài tập nào được giao.</div>
          ) : (
            cls.assignments.map((a: any) => (
              <div key={a.id} className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <div className="font-medium">{a.title}</div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {(a.problems || []).map((p: any) => (
                      <Link key={p.id} to={`/problems/${p.code}`} className="rounded border border-zinc-200 dark:border-zinc-700 px-2 py-0.5 font-mono text-xs hover:border-[#89B4E8]">
                        {p.code}: {p.title}
                      </Link>
                    ))}
                  </div>
                </div>
                {a.due_at && (
                  <span className="font-mono text-xs text-[#945214] dark:text-[#F3C89A]">
                    Hạn: {new Date(a.due_at).toLocaleString()}
                  </span>
                )}
              </div>
            ))
          )}
        </div>
      </section>

      {/* Progress table for teachers/admins */}
      {isStaff && progress && (
        <section className="space-y-2.5">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Tiến độ học sinh</h2>
          <div className="noka-section overflow-x-auto">
            <table className="noka-table">
              <thead>
                <tr>
                  <th>Học sinh</th>
                  <th>Username</th>
                  <th className="text-right">Đã AC</th>
                  <th className="text-right">Chưa làm</th>
                  <th className="text-right">Tổng điểm</th>
                  <th className="text-right">Lượt nộp</th>
                </tr>
              </thead>
              <tbody>
                {(progress.students || []).map((st: any) => (
                  <tr key={st.student_id}>
                    <td className="font-medium">{st.full_name || st.username}</td>
                    <td className="font-mono text-xs text-zinc-500">{st.username}</td>
                    <td className="text-right font-mono text-[#1F6F45] dark:text-[#98DFB5]">{st.ac_count}/{st.total_assigned}</td>
                    <td className="text-right font-mono text-zinc-500">{st.unsolved_count}</td>
                    <td className="text-right font-mono font-semibold">{st.total_score}</td>
                    <td className="text-right font-mono text-xs">{st.submission_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
};
