'use client';

import { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Check, X, Pencil, ChevronDown, ChevronUp } from 'lucide-react';
import type { PendingTask } from '@/lib/types';

interface Props {
  task: PendingTask;
  onConfirm: (modifiedSql?: string) => Promise<void>;
  onReject: () => Promise<void>;
  loading: boolean;
}

export default function SqlConfirmation({ task, onConfirm, onReject, loading }: Props) {
  const [editing, setEditing] = useState(false);
  const [editedSql, setEditedSql] = useState(task.generated_sql);
  const [traceOpen, setTraceOpen] = useState(false);

  return (
    <div className="rounded-xl border-2 border-amber-400 bg-amber-50 p-4 space-y-3">
      <p className="text-sm font-semibold text-amber-800">
        ⚠️ SQL awaiting your confirmation before execution
      </p>

      {task.confirmation_message && (
        <p className="text-sm text-gray-700">{task.confirmation_message}</p>
      )}

      {editing ? (
        <textarea
          className="w-full rounded-lg border border-gray-300 font-mono text-sm p-2 min-h-[120px] focus:outline-none focus:border-blue-500"
          value={editedSql}
          onChange={(e) => setEditedSql(e.target.value)}
        />
      ) : (
        <SyntaxHighlighter
          language="sql"
          style={oneLight}
          customStyle={{ borderRadius: '0.5rem', margin: 0, fontSize: '0.82rem' }}
        >
          {task.generated_sql}
        </SyntaxHighlighter>
      )}

      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => onConfirm(editing ? editedSql : undefined)}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-600 hover:bg-green-700 text-white text-sm font-medium disabled:opacity-50 transition-colors"
        >
          <Check className="w-4 h-4" />
          {loading ? 'Executing…' : 'Execute'}
        </button>

        <button
          onClick={onReject}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-100 hover:bg-red-200 text-red-700 text-sm font-medium disabled:opacity-50 transition-colors"
        >
          <X className="w-4 h-4" /> Cancel
        </button>

        <button
          onClick={() => setEditing((v) => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium transition-colors"
        >
          <Pencil className="w-4 h-4" /> {editing ? 'View original' : 'Modify SQL'}
        </button>

        {editing && (
          <button
            onClick={() => onConfirm(editedSql)}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium disabled:opacity-50 transition-colors"
          >
            <Check className="w-4 h-4" /> Submit modified
          </button>
        )}
      </div>
    </div>
  );
}
