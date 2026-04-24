'use client';

import { useState } from 'react';
import { Play, Loader2 } from 'lucide-react';
import { executeRawSql } from '@/lib/api';
import ResultsTable from './ResultsTable';

type Row = Record<string, unknown>;

export default function RawSqlPanel({
  connectionId,
  initialSql,
  onSqlChange,
}: {
  connectionId: string;
  initialSql: string;
  onSqlChange: (sql: string) => void;
}) {
  const [sql, setSql] = useState(initialSql || '');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<Row[] | null>(null);
  const [rowCount, setRowCount] = useState(0);
  const [error, setError] = useState('');

  async function handleExecute() {
    if (!sql.trim()) return;
    setLoading(true);
    setError('');
    setResults(null);
    try {
      const data = await executeRawSql(connectionId, sql);
      setResults(data.results);
      setRowCount(data.row_count);
      onSqlChange(sql);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err as Error)?.message ||
        'Execution failed';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4 thin-scroll">
      <h2 className="font-semibold text-sm">Execute SQL directly</h2>
      <textarea
        value={sql}
        onChange={(e) => setSql(e.target.value)}
        placeholder="SELECT TOP 100 * FROM dbo.PatientDim;"
        rows={8}
        className="w-full font-mono text-sm border border-gray-300 rounded-xl p-3 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 resize-y"
      />
      <button
        onClick={handleExecute}
        disabled={loading || !sql.trim()}
        className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium transition-colors"
      >
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {loading ? 'Executing…' : 'Execute SQL'}
      </button>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
          ❌ {error}
        </div>
      )}

      {results !== null && (
        <div>
          <ResultsTable results={results} rowCount={rowCount} />
        </div>
      )}
    </div>
  );
}
