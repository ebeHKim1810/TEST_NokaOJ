import { BRAND_CONFIG } from '../config/brand';

const TOKEN_KEY = 'noka_judge_token';

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${BRAND_CONFIG.apiBaseUrl}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === 'string') msg = data.detail;
      else if (data.detail?.message) msg = data.detail.message;
      else if (Array.isArray(data.detail) && data.detail.length > 0) {
        // FastAPI/Pydantic validation errors (422)
        msg = data.detail
          .map((d: any) => {
            const loc = Array.isArray(d?.loc) ? d.loc.filter((x: any) => x !== 'body').join('.') : '';
            return loc ? `${loc}: ${d?.msg ?? ''}` : String(d?.msg ?? '');
          })
          .join('; ');
      }
    } catch {
      // ignore
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Public config & auth
  getPublicConfig: () => request<{ site_name: string; allow_registration: boolean }>('/admin/public-config'),
  login: (username: string, password: string) =>
    request<{ access_token: string; user: any }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  register: (payload: { username: string; email: string; full_name: string; password: string }) =>
    request<{ access_token: string; user: any }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  me: () => request<any>('/auth/me'),

  // Problems
  listProblems: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') qs.set(k, String(v));
    });
    return request<any>(`/problems?${qs.toString()}`);
  },
  getProblem: (codeOrId: string | number, contestId?: number | string) => {
    const qs = contestId ? `?contest_id=${encodeURIComponent(String(contestId))}` : '';
    return request<any>(`/problems/${codeOrId}${qs}`);
  },
  listTags: () => request<{ items: Array<{ id: number; name: string; slug: string }> }>('/problems/tags/all'),
  createProblem: (payload: any) =>
    request<any>('/problems', { method: 'POST', body: JSON.stringify(payload) }),
  updateProblem: (id: number, payload: any) =>
    request<any>(`/problems/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteProblem: (id: number) => request<any>(`/problems/${id}`, { method: 'DELETE' }),

  // Testcases
  listTestcases: (problemId: number) => request<any>(`/testcases/problem/${problemId}`),
  createTestcase: (problemId: number, payload: any) =>
    request<any>(`/testcases/problem/${problemId}`, { method: 'POST', body: JSON.stringify(payload) }),
  updateTestcase: (testcaseId: number, payload: any) =>
    request<any>(`/testcases/${testcaseId}`, { method: 'PUT', body: JSON.stringify(payload) }),
  saveAllTestcases: (problemId: number, items: any[]) =>
    request<any>(`/testcases/problem/${problemId}/save-all`, {
      method: 'POST',
      body: JSON.stringify({ items }),
    }),
  deleteTestcase: (testcaseId: number) =>
    request<any>(`/testcases/${testcaseId}`, { method: 'DELETE' }),
  createTestcaseGroup: (problemId: number, payload: any) =>
    request<any>(`/testcases/problem/${problemId}/groups`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  uploadTestcasesZip: (problemId: number, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<any>(`/testcases/problem/${problemId}/upload-zip`, {
      method: 'POST',
      body: fd,
    });
  },
  getTestcasesBackupUrl: (problemId: number) =>
    `${BRAND_CONFIG.apiBaseUrl}/testcases/problem/${problemId}/backup`,

  // Advanced Testcase Generator
  getGeneratorTemplates: () => request<any>('/testcase-generator/templates'),
  generateTestcases: (payload: any) =>
    request<any>('/testcase-generator/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  saveGeneratedBatch: (batchId: string, payload: any) =>
    request<any>(`/testcase-generator/batches/${batchId}/save`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getBatchDownloadUrl: (batchId: string) =>
    `${BRAND_CONFIG.apiBaseUrl}/testcase-generator/batches/${batchId}/download`,

  // Submissions
  listLanguages: () => request<{ items: any[] }>('/submissions/languages'),
  runSample: (payload: any) =>
    request<any>('/submissions/run-sample', { method: 'POST', body: JSON.stringify(payload) }),
  submitCode: (payload: any) =>
    request<any>('/submissions', { method: 'POST', body: JSON.stringify(payload) }),
  listSubmissions: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') qs.set(k, String(v));
    });
    return request<any>(`/submissions?${qs.toString()}`);
  },
  getSubmission: (id: number | string) => request<any>(`/submissions/${id}`),
  rejudgeSubmission: (id: number) =>
    request<any>(`/submissions/${id}/rejudge`, { method: 'POST' }),

  // Contests
  listContests: () => request<any>('/contests'),
  createContest: (payload: any) =>
    request<any>('/contests', { method: 'POST', body: JSON.stringify(payload) }),
  getContest: (id: number | string) => request<any>(`/contests/${id}`),
  updateContest: (id: number | string, payload: Record<string, any>) =>
    request<any>(`/contests/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteContest: (id: number | string) =>
    request<any>(`/contests/${id}`, { method: 'DELETE' }),
  registerContest: (id: number | string) =>
    request<any>(`/contests/${id}/register`, { method: 'POST' }),
  getScoreboard: (id: number | string) => request<any>(`/contests/${id}/scoreboard`),
  getContestAccess: (id: number | string) => request<any>(`/contests/${id}/access`),
  addContestUsers: (id: number | string, payload: { user_ids?: number[]; usernames?: string[] }) =>
    request<any>(`/contests/${id}/access/users`, { method: 'POST', body: JSON.stringify(payload) }),
  removeContestUser: (id: number | string, userId: number) =>
    request<any>(`/contests/${id}/access/users/${userId}`, { method: 'DELETE' }),
  addContestClassroom: (id: number | string, classroom_id: number) =>
    request<any>(`/contests/${id}/access/classrooms`, {
      method: 'POST',
      body: JSON.stringify({ classroom_id }),
    }),
  removeContestClassroom: (id: number | string, classroomId: number) =>
    request<any>(`/contests/${id}/access/classrooms/${classroomId}`, { method: 'DELETE' }),

  // Classrooms & Assignments
  listClassrooms: () => request<any>('/classrooms'),
  createClassroom: (payload: any) =>
    request<any>('/classrooms', { method: 'POST', body: JSON.stringify(payload) }),
  joinClassroom: (join_code: string) =>
    request<any>('/classrooms/join', { method: 'POST', body: JSON.stringify({ join_code }) }),
  getClassroom: (id: number | string) => request<any>(`/classrooms/${id}`),
  addStudent: (classroomId: number, username_or_email: string) =>
    request<any>(`/classrooms/${classroomId}/students`, {
      method: 'POST',
      body: JSON.stringify({ username_or_email }),
    }),
  importStudents: (classroomId: number, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<any>(`/classrooms/${classroomId}/students/import`, {
      method: 'POST',
      body: fd,
    });
  },
  getClassroomProgress: (classroomId: number | string) =>
    request<any>(`/classrooms/${classroomId}/progress`),
  createAssignment: (payload: any) =>
    request<any>('/assignments', { method: 'POST', body: JSON.stringify(payload) }),
  myAssignments: () => request<any>('/assignments/my'),

  // Admin & Users
  listUsers: (search = '') => request<any>(`/users?search=${encodeURIComponent(search)}`),
  createUser: (payload: any) =>
    request<any>('/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (id: number, payload: any) =>
    request<any>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteUser: (id: number) => request<any>(`/users/${id}`, { method: 'DELETE' }),
  getAdminStats: () => request<any>('/admin/stats'),
  getAdminSettings: () => request<any>('/admin/settings'),
  updateAdminSettings: (settings: Record<string, string>) =>
    request<any>('/admin/settings', { method: 'PUT', body: JSON.stringify({ settings }) }),
  listAuditLogs: () => request<any>('/admin/audit-logs'),
};
