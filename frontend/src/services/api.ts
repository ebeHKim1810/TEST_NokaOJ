import { BRAND_CONFIG } from '../config/brand';

const TOKEN_KEY = 'noka_judge_token';

interface CacheEntry {
  expiresAt: number;
  data: any;
}

const responseCache = new Map<string, CacheEntry>();
const inFlightRequests = new Map<string, Promise<any>>();

export function clearApiCache(prefix?: string): void {
  if (!prefix) {
    responseCache.clear();
    return;
  }
  for (const key of responseCache.keys()) {
    if (key.includes(prefix)) responseCache.delete(key);
  }
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
  clearApiCache();
}

interface RequestOptions extends RequestInit {
  cacheTtlMs?: number;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { cacheTtlMs = 0, ...fetchOptions } = options;
  const method = (fetchOptions.method || 'GET').toUpperCase();
  const token = getStoredToken();
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const url = `${BRAND_CONFIG.apiBaseUrl}${normalizedPath}`;
  const cacheKey = `${token ? 'auth' : 'anon'}:${url}`;

  if (method === 'GET' && cacheTtlMs > 0) {
    const cached = responseCache.get(cacheKey);
    if (cached && cached.expiresAt > Date.now()) {
      return cached.data as T;
    }
    const existing = inFlightRequests.get(cacheKey);
    if (existing) {
      return existing as Promise<T>;
    }
  }

  const headers: Record<string, string> = {
    ...(fetchOptions.headers as Record<string, string> | undefined),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (!(fetchOptions.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const execute = async (): Promise<T> => {
    const res = await fetch(url, {
      ...fetchOptions,
      headers,
    });

    if (!res.ok) {
      let msg = `Request failed (${res.status})`;
      let hasApiDetail = false;
      try {
        const data = await res.json();
        if (typeof data.detail === 'string') {
          msg = data.detail;
          hasApiDetail = true;
        } else if (data.detail?.message) {
          msg = data.detail.message;
          hasApiDetail = true;
        } else if (Array.isArray(data.detail) && data.detail.length > 0) {
          // FastAPI/Pydantic validation errors (422)
          msg = data.detail
            .map((d: any) => {
              const loc = Array.isArray(d?.loc) ? d.loc.filter((x: any) => x !== 'body').join('.') : '';
              return loc ? `${loc}: ${d?.msg ?? ''}` : String(d?.msg ?? '');
            })
            .join('; ');
          hasApiDetail = true;
        }
      } catch {
        // Non-JSON response (e.g. static host 404 when Backend URL is not configured)
      }
      if (!hasApiDetail && res.status === 404 && BRAND_CONFIG.apiBaseUrl.startsWith('/')) {
        msg = `Không tìm thấy API Backend (404 tại ${url}). Hãy kiểm tra Backend đã được deploy online và cấu hình biến môi trường VITE_API_BASE_URL trên Vercel.`;
      }
      throw new Error(msg);
    }

    const parsed = (await res.json()) as T;
    if (method === 'GET' && cacheTtlMs > 0) {
      if (responseCache.size > 200) {
        const firstKey = responseCache.keys().next().value;
        if (firstKey) responseCache.delete(firstKey);
      }
      responseCache.set(cacheKey, { expiresAt: Date.now() + cacheTtlMs, data: parsed });
    } else if (method !== 'GET') {
      clearApiCache();
    }
    return parsed;
  };

  if (method === 'GET' && cacheTtlMs > 0) {
    const promise = execute().finally(() => {
      inFlightRequests.delete(cacheKey);
    });
    inFlightRequests.set(cacheKey, promise);
    return promise;
  }

  return execute();
}

export const api = {
  // Lightweight keep-alive / warmup ping (zero DB queries)
  pingHealth: () =>
    fetch(`${BRAND_CONFIG.apiBaseUrl}/health`, { method: 'GET' }).catch(() => undefined),

  // Public config & auth
  getPublicConfig: () =>
    request<{ site_name: string; allow_registration: boolean }>('/admin/public-config', {
      cacheTtlMs: 60_000,
    }),
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
    return request<any>(`/problems?${qs.toString()}`, { cacheTtlMs: 30_000 });
  },
  getProblem: (codeOrId: string | number, contestId?: number | string) => {
    const qs = contestId ? `?contest_id=${encodeURIComponent(String(contestId))}` : '';
    return request<any>(`/problems/${codeOrId}${qs}`, { cacheTtlMs: 45_000 });
  },
  prefetchProblem: (codeOrId: string | number, contestId?: number | string) => {
    const qs = contestId ? `?contest_id=${encodeURIComponent(String(contestId))}` : '';
    request<any>(`/problems/${codeOrId}${qs}`, { cacheTtlMs: 45_000 }).catch(() => {});
  },
  listTags: () =>
    request<{ items: Array<{ id: number; name: string; slug: string }> }>('/problems/tags/all', {
      cacheTtlMs: 60_000,
    }),
  createProblem: (payload: any) =>
    request<any>('/problems', { method: 'POST', body: JSON.stringify(payload) }),
  updateProblem: (id: number, payload: any) =>
    request<any>(`/problems/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  getProblemAccess: (id: number) => request<any>(`/problems/${id}/access`),
  updateProblemAccess: (
    id: number,
    payload: {
      visibility?: string;
      allowed_user_ids?: number[];
      submission_retention_mode?: 'latest' | 'best';
    }
  ) => request<any>(`/problems/${id}/access`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteProblem: (id: number) =>
    request<{
      deleted: boolean;
      id: number;
      code?: string;
      deleted_testcases?: number;
      deleted_submissions?: number;
      deleted_storage_files?: number;
    }>(`/problems/${id}`, { method: 'DELETE' }),
  uploadProblemImage: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<{
      url: string;
      path: string;
      filename: string;
      storage_key: string;
      size_bytes: number;
      content_type: string;
    }>('/problems/upload-image', {
      method: 'POST',
      body: fd,
    });
  },
  autoImportProblem: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<{
      title: string;
      description: string;
      input_description: string;
      output_description: string;
      constraints: string;
      samples?: Array<{ input: string; output: string; explanation: string }>;
      sample_input: string;
      sample_output: string;
      explanation: string;
      time_limit_ms: number;
      memory_limit_mb: number;
    }>('/problems/auto-import', {
      method: 'POST',
      body: fd,
    });
  },

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
  getGeneratorTemplates: () => request<any>('/testcase-generator/templates', { cacheTtlMs: 300_000 }),
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
  listLanguages: () => request<{ items: any[] }>('/submissions/languages', { cacheTtlMs: 300_000 }),
  runSample: (payload: any) =>
    request<any>('/submissions/run-sample', { method: 'POST', body: JSON.stringify(payload) }),
  submitCode: (payload: any) =>
    request<any>('/submissions', { method: 'POST', body: JSON.stringify(payload) }),
  listSubmissions: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') qs.set(k, String(v));
    });
    return request<any>(`/submissions?${qs.toString()}`, { cacheTtlMs: 10_000 });
  },
  getSubmission: (id: number | string) => request<any>(`/submissions/${id}`),
  rejudgeSubmission: (id: number) =>
    request<any>(`/submissions/${id}/rejudge`, { method: 'POST' }),
  deleteSubmission: (id: number) =>
    request<{ deleted: boolean; id: number }>(`/submissions/${id}`, { method: 'DELETE' }),
  bulkDeleteSubmissions: (params: {
    problem_id?: number;
    problem_code?: string;
    user_id?: number;
    username?: string;
    delete_all?: boolean;
  }) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '' && v !== false) qs.set(k, String(v));
    });
    return request<{ deleted_count: number }>(`/submissions?${qs.toString()}`, {
      method: 'DELETE',
    });
  },

  // Contests
  listContests: () => request<any>('/contests', { cacheTtlMs: 20_000 }),
  createContest: (payload: any) =>
    request<any>('/contests', { method: 'POST', body: JSON.stringify(payload) }),
  getContest: (id: number | string) => request<any>(`/contests/${id}`, { cacheTtlMs: 20_000 }),
  updateContest: (id: number | string, payload: Record<string, any>) =>
    request<any>(`/contests/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteContest: (id: number | string) =>
    request<any>(`/contests/${id}`, { method: 'DELETE' }),
  registerContest: (id: number | string) =>
    request<any>(`/contests/${id}/register`, { method: 'POST' }),
  getScoreboard: (id: number | string) =>
    request<any>(`/contests/${id}/scoreboard`, { cacheTtlMs: 10_000 }),
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
  listClassrooms: () => request<any>('/classrooms', { cacheTtlMs: 20_000 }),
  createClassroom: (payload: any) =>
    request<any>('/classrooms', { method: 'POST', body: JSON.stringify(payload) }),
  joinClassroom: (join_code: string) =>
    request<any>('/classrooms/join', { method: 'POST', body: JSON.stringify({ join_code }) }),
  getClassroom: (id: number | string) => request<any>(`/classrooms/${id}`, { cacheTtlMs: 20_000 }),
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
    request<any>(`/classrooms/${classroomId}/progress`, { cacheTtlMs: 15_000 }),
  createAssignment: (payload: any) =>
    request<any>('/assignments', { method: 'POST', body: JSON.stringify(payload) }),
  myAssignments: () => request<any>('/assignments/my', { cacheTtlMs: 20_000 }),

  // Admin & Users
  listUsers: (search = '') => request<any>(`/users?search=${encodeURIComponent(search)}`),
  createUser: (payload: any) =>
    request<any>('/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (id: number, payload: any) =>
    request<any>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteUser: (id: number) => request<any>(`/users/${id}`, { method: 'DELETE' }),
  getAdminStats: () => request<any>('/admin/stats', { cacheTtlMs: 20_000 }),
  getAdminSettings: () => request<any>('/admin/settings'),
  updateAdminSettings: (settings: Record<string, string>) =>
    request<any>('/admin/settings', { method: 'PUT', body: JSON.stringify({ settings }) }),
  listAuditLogs: () => request<any>('/admin/audit-logs'),
};
