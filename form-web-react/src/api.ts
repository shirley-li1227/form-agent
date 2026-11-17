import axios from 'axios';
import type { RunInfo } from './types';

// 开发默认打到本机网关；生产构建留空即同源请求，由 nginx 反代 /api 到网关
const base =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? 'http://localhost:3000' : '');

const api = axios.create({ baseURL: base, timeout: 30000 });

export const generateForm = (requirement: string, needApproval = true) =>
  api.post<RunInfo>('/api/form/generate', {
    requirement,
    need_approval: needApproval,
  });

export const getRun = (runId: string) =>
  api.get<RunInfo>(`/api/form/run/${runId}`);

export const approval = (runId: string, approved: boolean, comment?: string) =>
  api.post<RunInfo>(`/api/form/approval/${runId}`, { approved, comment });

/** 把网关/后端的错误信息取成人能读的文案。 */
export function errorText(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: { message?: string } } }).response
    ?.data;
  return data?.message ?? (err as Error)?.message ?? fallback;
}
