import axios from 'axios';
import type {
  ConnectRequest,
  ConnectResponse,
  AgentChatResponse,
  QueryHistoryItem,
  SkillCandidate,
  PublishedSkill,
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
  current_sql?: string,
  user_query?: string,
): Promise<AgentChatResponse> {
  const r = await http.post<AgentChatResponse>('/api/agent/confirm', {
    task_id,
    connection_id,
    ...(modified_sql ? { modified_sql } : {}),
    ...(current_sql ? { current_sql } : {}),
    ...(user_query ? { user_query } : {}),
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

export async function getSkillCandidates(
  connection_id: string,
  status = 'pending',
  limit = 20,
): Promise<SkillCandidate[]> {
  const r = await http.get<SkillCandidate[]>(
    `/api/agent/skill-candidates/${connection_id}`,
    { params: { status, limit } },
  );
  return r.data;
}

export async function getPublishedSkills(
  connection_id: string,
  limit = 20,
): Promise<PublishedSkill[]> {
  const r = await http.get<PublishedSkill[]>(
    `/api/agent/published-skills/${connection_id}`,
    { params: { limit } },
  );
  return r.data;
}

export async function approveSkillCandidate(
  candidate_id: number,
  payload?: { review_notes?: string; edited_title?: string; edited_instructions?: string },
): Promise<{ status: string; published_skill_id?: number }> {
  const r = await http.post<{ status: string; published_skill_id?: number }>(
    '/api/agent/skill-candidates/approve',
    {
      candidate_id,
      ...(payload?.review_notes ? { review_notes: payload.review_notes } : {}),
      ...(payload?.edited_title ? { edited_title: payload.edited_title } : {}),
      ...(payload?.edited_instructions ? { edited_instructions: payload.edited_instructions } : {}),
    },
  );
  return r.data;
}

export async function rejectSkillCandidate(
  candidate_id: number,
  review_notes = '',
): Promise<{ status: string }> {
  const r = await http.post<{ status: string }>(
    '/api/agent/skill-candidates/reject',
    { candidate_id, review_notes },
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
