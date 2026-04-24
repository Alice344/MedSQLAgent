'use client';

import { useState } from 'react';
import { Download } from 'lucide-react';

type Row = Record<string, unknown>;

function toCsv(rows: Row[]): string {
  if (!rows.length) return '';
  const headers = Object.keys(rows[0]);
  const lines = [headers.join(',')];
  for (const row of rows) {
    lines.push(headers.map((h) => JSON.stringify(row[h] ?? '')).join(','));
  }
  return lines.join('\n');
}

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const PREVIEW = 10;

export default function ResultsTable({
  results,
  rowCount,
}: {
  results: Row[];
  rowCount: number;
}) {
  const [showAll, setShowAll] = useState(false);

  if (!results.length) {
    return (
      <p className="text-sm text-gray-500 italic">
        Query executed successfully — no rows returned.
      </p>
    );
  }

  const headers = Object.keys(results[0]);
  const displayed = showAll ? results : results.slice(0, PREVIEW);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500">{rowCount} rows</span>
        <div className="flex gap-2">
          <button
            onClick={() => downloadBlob(toCsv(results), 'results.csv', 'text/csv')}
            className="flex items-center gap-1 text-xs text-blue-600 hover:underline"
          >
            <Download className="w-3 h-3" /> CSV
          </button>
          <button
            onClick={() =>
              downloadBlob(JSON.stringify(results, null, 2), 'results.json', 'application/json')
            }
            className="flex items-center gap-1 text-xs text-blue-600 hover:underline"
          >
            <Download className="w-3 h-3" /> JSON
          </button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full text-xs">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {headers.map((h) => (
                <th
                  key={h}
                  className="px-3 py-2 text-left font-semibold text-gray-600 whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayed.map((row, ri) => (
              <tr
                key={ri}
                className={ri % 2 === 0 ? 'bg-white' : 'bg-gray-50'}
              >
                {headers.map((h) => (
                  <td key={h} className="px-3 py-1.5 text-gray-700 whitespace-nowrap max-w-xs truncate">
                    {String(row[h] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {results.length > PREVIEW && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="text-xs text-blue-600 hover:underline"
        >
          {showAll ? 'Show less' : `Show all ${rowCount} rows`}
        </button>
      )}
    </div>
  );
}
