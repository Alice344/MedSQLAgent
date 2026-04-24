'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Bot,
  RefreshCw,
  Trash2,
  PlusCircle,
  LogOut,
  Send,
  Loader2,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useAppStore } from '@/store/useStore';
import {
  agentChat,
  agentConfirm,
  agentReject,
  agentVisualize,
  getQueryHistory,
  clearHistory,
  newConversation,
  refreshSchema,
} from '@/lib/api';
import type { PendingTask, QueryHistoryItem } from '@/lib/types';
import ChatBubble from '@/components/ChatBubble';
import SqlConfirmation from '@/components/SqlConfirmation';
import RawSqlPanel from '@/components/RawSqlPanel';

export default function ChatPage() {
  const router = useRouter();
  const {
    connectionId,
    connectedServer,
    chatMessages,
    pendingTask,
    lastTaskId,
    lastSqlQuery,
    addMessage,
    clearMessages,
    setPendingTask,
    setLastTaskId,
    setLastSqlQuery,
    disconnect,
  } = useAppStore();

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'chat' | 'sql'>('chat');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>([]);
  const [schemaMsg, setSchemaMsg] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  // Redirect if not connected
  useEffect(() => {
    if (!connectionId) {
      router.replace('/');
    }
  }, [connectionId, router]);

  // Load query history
  const loadHistory = useCallback(async () => {
    if (!connectionId) return;
    try {
      const h = await getQueryHistory(connectionId, 10);
      setQueryHistory(h);
    } catch {}
  }, [connectionId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, pendingTask]);

  if (!connectionId) return null;

  // ── Send chat message ────────────────────────────────────────────────────

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    setSending(true);
    addMessage({ role: 'user', content: text });

    try {
      const data = await agentChat(text, connectionId!);

      if (data.agent_trace?.length) {
        addMessage({ role: 'agent_trace', content: '', data: { trace: data.agent_trace } });
      }

      if (data.status === 'awaiting_confirmation') {
        setPendingTask({
          task_id: data.task_id!,
          generated_sql: data.generated_sql!,
          confirmation_message: data.confirmation_message,
        });
        addMessage({ role: 'assistant', content: 'I\'ve generated SQL for your request. Please review before execution.' });
      } else if (data.status === 'completed') {
        if (data.generated_sql) {
          addMessage({ role: 'sql', content: data.generated_sql });
          setLastSqlQuery(data.generated_sql);
        }
        if (data.explanation) addMessage({ role: 'assistant', content: data.explanation });
        if (data.results != null) {
          addMessage({
            role: 'results',
            content: '',
            data: { results: data.results, row_count: data.row_count ?? data.results.length },
          });
        }
        if (data.visualization) {
          addMessage({ role: 'visualization', content: '', data: { viz: data.visualization } });
        }
        if (data.task_id) setLastTaskId(data.task_id);
        loadHistory();
      } else if (data.status === 'clarification_needed') {
        addMessage({ role: 'assistant', content: data.refined_query || 'Could you clarify your request?' });
      } else if (data.status === 'error') {
        addMessage({ role: 'error', content: data.error || 'Unknown error' });
      } else {
        // Schema explore etc.
        if (data.tables) {
          const lines = [`Found **${data.total_tables ?? data.tables.length}** tables:\n`];
          data.tables.slice(0, 30).forEach((t) => {
            lines.push(`- \`${t.full_name}\` (${t.column_count} cols)${t.description ? ' — ' + t.description : ''}`);
          });
          if (data.tables.length > 30) lines.push(`- … and ${data.tables.length - 30} more`);
          addMessage({ role: 'assistant', content: lines.join('\n') });
        }
        if (data.explanation) addMessage({ role: 'assistant', content: data.explanation });
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (err as Error)?.message || 'Agent pipeline failed';
      addMessage({ role: 'error', content: msg });
    } finally {
      setSending(false);
    }
  }

  // ── Confirm SQL ──────────────────────────────────────────────────────────

  async function handleConfirm(modifiedSql?: string) {
    if (!pendingTask) return;
    setConfirmLoading(true);
    try {
      const data = await agentConfirm(pendingTask.task_id, connectionId!, modifiedSql);
      setPendingTask(null);
      if (data.status === 'completed') {
        if (data.generated_sql) addMessage({ role: 'sql', content: modifiedSql ?? data.generated_sql });
        if (data.explanation) addMessage({ role: 'assistant', content: data.explanation });
        if (data.results != null) {
          addMessage({
            role: 'results',
            content: '',
            data: { results: data.results, row_count: data.row_count ?? data.results.length },
          });
        }
        if (data.visualization) {
          addMessage({ role: 'visualization', content: '', data: { viz: data.visualization } });
        }
        if (data.task_id) setLastTaskId(data.task_id);
        loadHistory();
      } else {
        addMessage({ role: 'error', content: data.error || 'Execution failed' });
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (err as Error)?.message || 'Execution failed';
      addMessage({ role: 'error', content: msg });
    } finally {
      setConfirmLoading(false);
    }
  }

  // ── Reject SQL ───────────────────────────────────────────────────────────

  async function handleReject() {
    if (!pendingTask) return;
    setConfirmLoading(true);
    try {
      await agentReject(pendingTask.task_id, connectionId!, 'User cancelled');
      setPendingTask(null);
      addMessage({ role: 'assistant', content: 'Query cancelled.' });
    } finally {
      setConfirmLoading(false);
    }
  }

  // ── Visualize ────────────────────────────────────────────────────────────

  async function handleVisualize() {
    if (!lastTaskId) return;
    try {
      const data = await agentVisualize(lastTaskId, connectionId!);
      if (data.visualization) {
        addMessage({ role: 'visualization', content: '', data: { viz: data.visualization } });
      }
    } catch {}
  }

  // ── Sidebar actions ──────────────────────────────────────────────────────

  async function handleClearChat() {
    clearMessages();
    try { await clearHistory(connectionId!); } catch {}
  }

  async function handleNewConversation() {
    clearMessages();
    try { await newConversation(connectionId!); } catch {}
  }

  async function handleRefreshSchema() {
    setSchemaMsg('Refreshing…');
    try {
      const r = await refreshSchema(connectionId!);
      setSchemaMsg(`✅ ${r.tables_count} tables refreshed`);
    } catch {
      setSchemaMsg('❌ Refresh failed');
    }
    setTimeout(() => setSchemaMsg(''), 4000);
  }

  function handleDisconnect() {
    disconnect();
    router.replace('/');
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <aside
        className={`${
          sidebarOpen ? 'w-64' : 'w-0 overflow-hidden'
        } transition-all duration-200 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col`}
      >
        <div className="p-4 border-b">
          <div className="flex items-center gap-2 mb-1">
            <Bot className="w-5 h-5 text-blue-600" />
            <span className="font-semibold text-sm">SQL Agent</span>
          </div>
          <p className="text-xs text-gray-400 font-mono truncate">{connectedServer}</p>
        </div>

        <div className="p-3 space-y-1">
          <SidebarBtn icon={<RefreshCw className="w-4 h-4" />} label="Refresh schema" onClick={handleRefreshSchema} />
          {schemaMsg && <p className="text-xs text-gray-500 pl-2">{schemaMsg}</p>}
          <SidebarBtn icon={<Trash2 className="w-4 h-4" />} label="Clear chat" onClick={handleClearChat} />
          <SidebarBtn icon={<PlusCircle className="w-4 h-4" />} label="New conversation" onClick={handleNewConversation} />
          <SidebarBtn icon={<LogOut className="w-4 h-4" />} label="Disconnect" onClick={handleDisconnect} danger />
        </div>

        {/* Query history */}
        <div className="flex-1 overflow-y-auto p-3 border-t">
          <p className="text-xs font-semibold text-gray-500 mb-2">Recent queries</p>
          {queryHistory.length === 0 && (
            <p className="text-xs text-gray-400 italic">No queries yet</p>
          )}
          {queryHistory.map((q) => (
            <div key={q.task_id} className="flex items-start gap-1.5 mb-1.5">
              <span className="text-xs mt-0.5">{q.status === 'completed' ? '✅' : '❌'}</span>
              <p className="text-xs text-gray-600 line-clamp-2">{q.user_query}</p>
            </div>
          ))}
        </div>
      </aside>

      {/* ── Main area ───────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="flex items-center gap-3 px-4 py-2.5 bg-white border-b border-gray-200">
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            className="p-1 rounded-lg hover:bg-gray-100 text-gray-500"
          >
            {sidebarOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
          <h1 className="font-semibold text-sm flex items-center gap-2">
            🤖 SQL Agent
          </h1>
          {/* Tabs */}
          <div className="ml-auto flex gap-1 bg-gray-100 rounded-lg p-1">
            {(['chat', 'sql'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  activeTab === tab ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab === 'chat' ? '💬 Chat' : '📝 Raw SQL'}
              </button>
            ))}
          </div>
        </header>

        {activeTab === 'chat' ? (
          <>
            {/* Messages area */}
            <div className="flex-1 overflow-y-auto thin-scroll p-4 space-y-4">
              {chatMessages.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full text-gray-400">
                  <Bot className="w-14 h-14 mb-3 text-gray-300" />
                  <p className="text-sm">Ask a question about your database</p>
                </div>
              )}
              {chatMessages.map((msg) => (
                <ChatBubble
                  key={msg.id}
                  msg={msg}
                  onVisualize={handleVisualize}
                  lastTaskId={lastTaskId}
                />
              ))}
              {pendingTask && (
                <SqlConfirmation
                  task={pendingTask}
                  onConfirm={handleConfirm}
                  onReject={handleReject}
                  loading={confirmLoading}
                />
              )}
              {sending && (
                <div className="flex gap-2 items-center text-sm text-gray-400">
                  <Loader2 className="w-4 h-4 animate-spin" /> Agents working…
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="bg-white border-t border-gray-200 px-4 py-3">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSend();
                }}
                className="flex gap-2"
              >
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask a question about your database…"
                  disabled={sending}
                  className="flex-1 rounded-xl border border-gray-300 px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:bg-gray-50"
                />
                <button
                  type="submit"
                  disabled={sending || !input.trim()}
                  className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium transition-colors"
                >
                  {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  Send
                </button>
              </form>
            </div>
          </>
        ) : (
          <RawSqlPanel connectionId={connectionId!} initialSql={lastSqlQuery} onSqlChange={setLastSqlQuery} />
        )}
      </div>
    </div>
  );
}

// ── Sidebar button ────────────────────────────────────────────────────────────

function SidebarBtn({
  icon,
  label,
  onClick,
  danger,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 w-full px-2 py-1.5 rounded-lg text-sm transition-colors ${
        danger
          ? 'text-red-600 hover:bg-red-50'
          : 'text-gray-700 hover:bg-gray-100'
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
