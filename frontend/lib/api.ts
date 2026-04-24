import axios from 'axios';
import type {
  ConnectRequest,
  ConnectResponse,
  AgentChatResponse,
  QueryHistoryItem,
} from './types';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8001';

const http = axios.create({ baseURL: BASE, timeout: 120_000 });

export async function checkHealth(): Promise<boolean> {
  try {
    const r = await http.get('/api/health', { timeout: 5000 });
    return r.status === 200;
  } catch {
    return false;
  }
}

export async function connectDatabase(payload: ConnectRequest): Promise<ConnectResponse> {
  const r = await http.post<ConnectResponse>('/api/connect', payload);
  return r.data;
}

export async function agentChat(
  message: string,
  connection_id: string,
): Promise<AgentChatResponse> {
  const r = await http.post<AgentChatResponse>('/api/agent/chat', { message, connection_id });
  return r.data;
}

export async function agentConfirm(
  task_id: string,
  connection_id: string,
  modified_sql?: string,
): Promise<AgentChatResponse> {
  const r = await http.post<AgentChatResponse>('/api/agent/confirm', {
    task_id,
    connection_id,
    ...(modified_sql ? { modified_sql } : {}),
  });
  return r.data;
}

export async function agentReject(
  task_id: string,
  connection_id: string,
  reason = '',
): Promise<void> {
  await http.post('/api/agent/reject', { task_id, connection_id, reason });
}

export async function agentVisualize(
  task_id: string,
  connection_id: string,
): Promise<AgentChatResponse> {
  const r = await http.post<AgentChatResponse>(
    '/api/agent/visualize',
    { task_id, connection_id },
    { timeout: 120_000 },
  );
  return r.data;
}

export async function getQueryHistory(
  connection_id: string,
  limit = 10,
): Promise<QueryHistoryItem[]> {
  const r = await http.get<QueryHistoryItem[]>(
    `/api/agent/query-history/${connection_id}`,
    { params: { limit } },
  );
  return r.data;
}

export async function clearHistory(connection_id: string): Promise<void> {
  await http.delete(`/api/agent/history/${connection_id}`);
}

export async function newConversation(connection_id: string): Promise<void> {
  await http.post(`/api/agent/new-conversation/${connection_id}`, {});
}

export async function refreshSchema(connection_id: string) {
  const r = await http.post(`/api/schema/${connection_id}/refresh`, {}, { timeout: 300_000 });
  return r.data;
}

export async function executeRawSql(
  connection_id: string,
  sql_query: string,
) {
  const r = await http.post(`/api/query/execute-sql/${connection_id}`, { sql_query });
  return r.data as { results: Record<string, unknown>[]; row_count: number };
}
