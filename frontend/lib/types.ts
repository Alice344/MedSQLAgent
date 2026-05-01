// ── API request/response types ───────────────────────────────────────────────

export interface ConnectRequest {
  server: string;
  database: string;
  username: string;
  password?: string;
  port: number;
  auth_method: 'sql' | 'azure_ad';
  use_mfa: boolean;
  refresh_schema: boolean;
  use_wholegraph: boolean;
}

export interface ConnectResponse {
  connection_id: string;
  message: string;
  tables_count: number;
  foreign_keys_count: number;
  schema_source: string;
}

export interface AgentChatResponse {
  status: 'completed' | 'awaiting_confirmation' | 'clarification_needed' | 'error' | string;
  task_id?: string;
  generated_sql?: string;
  confirmation_message?: string;
  explanation?: string;
  results?: Record<string, unknown>[];
  row_count?: number;
  visualization?: VizConfig;
  agent_trace?: TraceStep[];
  refined_query?: string;
  error?: string;
  tables?: TableSummary[];
  total_tables?: number;
}

export interface TraceStep {
  agent: string;
  content: string;
}

export interface VizConfig {
  summary?: string;
  charts: Chart[];
}

export interface Chart {
  title?: string;
  description?: string;
  plotly_config: Record<string, unknown>;
}

export interface QueryHistoryItem {
  task_id: string;
  user_query: string;
  status: 'completed' | 'failed' | string;
  created_at?: string;
}

export interface SkillCandidate {
  id: number;
  title: string;
  summary: string;
  trigger_query: string;
  representative_sql?: string;
  confidence: number;
  status: 'pending' | 'approved' | 'rejected' | string;
  metadata?: {
    selected_tables?: string[];
    example_queries?: string[];
    example_sqls?: string[];
    instructions?: string;
    avg_similarity?: number;
    top_similarity?: number;
    review_notes?: string;
  };
}

export interface PublishedSkill {
  id: number;
  title: string;
  summary: string;
  instructions: string;
  metadata?: {
    selected_tables?: string[];
    example_queries?: string[];
    review_notes?: string;
  };
}

export interface TableSummary {
  full_name: string;
  description?: string;
  column_count: number;
}

// ── Chat message types (client-side) ────────────────────────────────────────

export type MessageRole =
  | 'user'
  | 'assistant'
  | 'sql'
  | 'results'
  | 'visualization'
  | 'agent_trace'
  | 'error';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  data?: {
    results?: Record<string, unknown>[];
    row_count?: number;
    viz?: VizConfig;
    trace?: TraceStep[];
  };
}

export interface PendingTask {
  task_id: string;
  generated_sql: string;
  confirmation_message?: string;
  user_query?: string;
}
