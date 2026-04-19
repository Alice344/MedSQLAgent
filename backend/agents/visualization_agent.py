"""
Visualization agent – analyses query results and produces Plotly chart configs.

Given execution results and the user's query, this agent decides:
1. What chart type(s) are appropriate (bar, line, pie, scatter, table, heatmap)
2. Which columns map to x-axis, y-axis, color, etc.
3. Chart titles, labels, and formatting

Returns a list of Plotly figure specifications (as JSON-serialisable dicts).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from .base import AgentResult, AgentRole, BaseAgent, TaskContext

logger = logging.getLogger(__name__)

VIZ_MODEL = os.getenv("OPENAI_VIZ_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = """\
You are a data visualization expert. Given a SQL query, its results, and the user's request,
produce one or more Plotly chart configurations.

Return a JSON object with this structure:
{
  "charts": [
    {
      "chart_type": "bar",
      "title": "Lab Results by Month",
      "description": "Brief description of what this chart shows",
      "plotly_config": {
        "data": [
          {
            "type": "bar",
            "x": ["Jan", "Feb", "Mar"],
            "y": [10, 20, 30],
            "name": "Count"
          }
        ],
        "layout": {
          "title": "Lab Results by Month",
          "xaxis": {"title": "Month"},
          "yaxis": {"title": "Count"},
          "template": "plotly_white"
        }
      }
    }
  ],
  "summary": "Brief text summary of what the visualizations show"
}

Rules:
- Use the actual data from the query results to populate the chart data arrays.
- Choose the most appropriate chart type based on the data shape and user request.
- Supported chart types: bar, line, pie, scatter, heatmap, histogram, box, table.
- For large datasets (>50 rows), aggregate or sample the data appropriately.
- Always use "plotly_white" template for clean appearance.
- Use clear, descriptive titles and axis labels.
- If the data has a time/date column, prefer line charts.
- If comparing categories, prefer bar charts.
- If showing proportions, prefer pie charts.
- If showing distributions, prefer histograms or box plots.
- If the user asks for multiple charts, produce multiple entries in the "charts" array.
- Keep colors professional and accessible.
- Return ONLY valid JSON, no markdown fences.
"""


class VisualizationAgent(BaseAgent):
    role = AgentRole.VISUALIZER

    def run(self, ctx: TaskContext, **kwargs: Any) -> AgentResult:
        results = ctx.execution_result or {}
        rows = results.get("results", [])
        row_count = results.get("row_count", 0)
        sql = ctx.generated_sql or ""

        if not rows:
            return AgentResult(
                success=False,
                error="No data to visualize. Run a query first.",
            )

        # Send a sample to the LLM (limit to avoid token overflow)
        sample_rows = rows[:100]
        columns = list(sample_rows[0].keys()) if sample_rows else []

        user_prompt_parts = [
            f"User request: {ctx.user_query}",
            f"\nSQL Query:\n{sql}",
            f"\nResult columns: {columns}",
            f"Total rows: {row_count}",
            f"\nSample data ({len(sample_rows)} rows):\n{json.dumps(sample_rows[:20], default=str)}",
        ]

        if row_count > 20:
            user_prompt_parts.append(
                f"\nFull data ({len(sample_rows)} rows for charting):\n"
                f"{json.dumps(sample_rows, default=str)}"
            )

        user_prompt = "\n".join(user_prompt_parts)

        try:
            raw = self._chat(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=VIZ_MODEL,
                temperature=0.2,
                max_tokens=4000,
            )
        except Exception as exc:
            logger.error("VisualizationAgent LLM call failed: %s", exc)
            return AgentResult(
                success=False,
                error=f"Visualization generation failed: {exc}",
            )

        # Parse the response
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            viz_config = json.loads(cleaned)
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.error("VisualizationAgent returned invalid JSON: %s", raw[:500])
            return AgentResult(
                success=False,
                error="Failed to parse visualization config from LLM response.",
            )

        charts = viz_config.get("charts", [])
        summary = viz_config.get("summary", "")

        if not charts:
            return AgentResult(
                success=False,
                error="No charts generated. Try rephrasing your visualization request.",
            )

        ctx.visualization_config = viz_config
        ctx.add_message(
            "agent",
            f"Generated {len(charts)} chart(s): {', '.join(c.get('chart_type', '?') for c in charts)}",
            agent=self.role.value,
        )

        return AgentResult(
            success=True,
            data={"visualization": viz_config, "chart_count": len(charts)},
        )
