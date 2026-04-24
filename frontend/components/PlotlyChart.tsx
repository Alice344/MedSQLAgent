'use client';

import dynamic from 'next/dynamic';
import type { VizConfig } from '@/lib/types';

// plotly must be loaded client-side
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

export default function PlotlyChart({ viz }: { viz: VizConfig }) {
  return (
    <div className="space-y-3">
      {viz.summary && <p className="text-sm text-gray-600">{viz.summary}</p>}
      {viz.charts.map((chart, i) => (
        <div key={i} className="rounded-xl border bg-white p-3 overflow-hidden">
          {chart.title && <p className="font-semibold text-sm mb-1">{chart.title}</p>}
          {chart.description && (
            <p className="text-xs text-gray-500 mb-2">{chart.description}</p>
          )}
          <Plot
            data={(chart.plotly_config as { data?: Plotly.Data[] }).data ?? []}
            layout={{
              autosize: true,
              margin: { t: 30, l: 40, r: 20, b: 40 },
              ...(chart.plotly_config as { layout?: Partial<Plotly.Layout> }).layout,
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%', minHeight: 320 }}
          />
        </div>
      ))}
    </div>
  );
}
