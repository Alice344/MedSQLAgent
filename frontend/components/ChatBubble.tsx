'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { ChevronDown, ChevronUp, Bot, User } from 'lucide-react';
import dynamic from 'next/dynamic';
import ResultsTable from './ResultsTable';
import type { ChatMessage } from '@/lib/types';

const PlotlyChart = dynamic(() => import('./PlotlyChart'), { ssr: false });

export default function ChatBubble({
  msg,
  onVisualize,
  lastTaskId,
}: {
  msg: ChatMessage;
  onVisualize?: () => void;
  lastTaskId: string | null;
}) {
  const [traceOpen, setTraceOpen] = useState(false);

  if (msg.role === 'user') {
    return (
      <div className="flex justify-end gap-2">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-blue-600 text-white px-4 py-2.5 text-sm whitespace-pre-wrap">
          {msg.content}
        </div>
        <User className="w-7 h-7 text-blue-500 shrink-0 mt-1" />
      </div>
    );
  }

  if (msg.role === 'assistant') {
    return (
      <div className="flex gap-2">
        <Bot className="w-7 h-7 text-gray-400 shrink-0 mt-1" />
        <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-white border border-gray-200 px-4 py-3 text-sm prose prose-sm">
          <ReactMarkdown>{msg.content}</ReactMarkdown>
        </div>
      </div>
    );
  }

  if (msg.role === 'sql') {
    return (
      <div className="flex gap-2">
        <Bot className="w-7 h-7 text-gray-400 shrink-0 mt-1" />
        <div className="max-w-[85%] w-full">
          <SyntaxHighlighter
            language="sql"
            style={oneLight}
            customStyle={{ borderRadius: '0.75rem', fontSize: '0.82rem', margin: 0 }}
          >
            {msg.content}
          </SyntaxHighlighter>
        </div>
      </div>
    );
  }

  if (msg.role === 'results') {
    const results = msg.data?.results ?? [];
    const rowCount = msg.data?.row_count ?? results.length;
    return (
      <div className="flex gap-2">
        <Bot className="w-7 h-7 text-gray-400 shrink-0 mt-1" />
        <div className="max-w-full w-full space-y-2">
          <ResultsTable results={results} rowCount={rowCount} />
          {onVisualize && lastTaskId && (
            <button
              onClick={onVisualize}
              className="text-xs text-blue-600 hover:underline"
            >
              📊 Generate visualizations
            </button>
          )}
        </div>
      </div>
    );
  }

  if (msg.role === 'visualization') {
    const viz = msg.data?.viz;
    if (!viz) return null;
    return (
      <div className="flex gap-2">
        <Bot className="w-7 h-7 text-gray-400 shrink-0 mt-1" />
        <div className="max-w-full w-full">
          <p className="text-sm font-semibold mb-2">📊 Visualizations</p>
          <PlotlyChart viz={viz} />
        </div>
      </div>
    );
  }

  if (msg.role === 'agent_trace') {
    const trace = msg.data?.trace ?? [];
    return (
      <div className="flex gap-2">
        <Bot className="w-7 h-7 text-gray-400 shrink-0 mt-1" />
        <div className="max-w-[85%]">
          <button
            onClick={() => setTraceOpen((v) => !v)}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
          >
            {traceOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            🔍 Agent reasoning trace ({trace.length} steps)
          </button>
          {traceOpen && (
            <div className="mt-2 space-y-1">
              {trace.map((step, i) => (
                <div key={i} className="text-xs text-gray-600">
                  <span className="font-semibold text-blue-600">[{step.agent}]</span>{' '}
                  {step.content}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (msg.role === 'error') {
    return (
      <div className="flex gap-2">
        <Bot className="w-7 h-7 text-gray-400 shrink-0 mt-1" />
        <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-2.5 text-sm text-red-700">
          ❌ {msg.content}
        </div>
      </div>
    );
  }

  return null;
}
