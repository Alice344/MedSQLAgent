"""
Loads wholegraph.json and converts it to the standard schema format
used by SchemaStorage / format_schema_for_llm.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

WHOLEGRAPH_PATH = Path(__file__).resolve().parent.parent / "wholegraph.json"


def load_wholegraph_schema() -> Dict[str, Any]:
    """
    Parse wholegraph.json and return a schema dict with the shape:
      {
        "tables": [
          {
            "schema": "dbo",
            "name": "TableName",
            "full_name": "dbo.TableName",
            "description": "...",
            "columns": [
              {
                "name": "ColumnName",
                "data_type": "bigint",
                "is_nullable": True,
                "is_primary_key": False,
                "description": "..."
              }
            ]
          }
        ],
        "foreign_keys": [
          {
            "from_table": "dbo.SomeTable",
            "from_column": "PatientDurableKey",
            "to_table": "dbo.PatientDim",
            "to_column": "PatientDurableKey"
          }
        ]
      }
    """
    if not WHOLEGRAPH_PATH.exists():
        raise FileNotFoundError(f"wholegraph.json not found at {WHOLEGRAPH_PATH}")

    logger.info("Loading wholegraph.json (%s MB) ...", WHOLEGRAPH_PATH.stat().st_size // 1_000_000)

    with open(WHOLEGRAPH_PATH, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    # First pass: build etl_name -> full_name lookup for FK resolution
    etl_to_full: dict = {}
    for tbl in raw.get("tables", []):
        reporting_name: str = tbl.get("reporting_name") or f"dbo.{tbl['table_name']}"
        if "." in reporting_name:
            schema_part, table_part = reporting_name.split(".", 1)
        else:
            schema_part, table_part = "dbo", reporting_name
        full_name = f"{schema_part}.{table_part}"
        etl_to_full[tbl.get("etl_name") or tbl["table_name"]] = full_name
        etl_to_full[tbl["table_name"]] = full_name

    tables = []
    foreign_keys = []

    # Second pass: build tables and foreign keys
    for tbl in raw.get("tables", []):
        reporting_name = tbl.get("reporting_name") or f"dbo.{tbl['table_name']}"
        if "." in reporting_name:
            schema_part, table_part = reporting_name.split(".", 1)
        else:
            schema_part, table_part = "dbo", reporting_name
        full_name = f"{schema_part}.{table_part}"

        columns = []
        for col in tbl.get("columns", []):
            col_name: str = col.get("column_name", "")
            sql_type: str = col.get("sql_type") or col.get("data_type") or "unknown"
            is_nullable: bool = col.get("allows_null", "Yes").strip().lower() != "no"
            description: str = col.get("description") or ""

            fk_ref = col.get("fk_references")
            is_pk = (
                fk_ref is None
                and col_name.endswith("Key")
                and "bigint" in sql_type.lower()
                and col.get("allows_null", "Yes").strip().lower() == "no"
            )

            columns.append(
                {
                    "name": col_name,
                    "data_type": sql_type,
                    "is_nullable": is_nullable,
                    "is_primary_key": is_pk,
                    "description": description,
                }
            )

            if fk_ref:
                raw_target: str = fk_ref.get("table_name", "")
                # Resolve to full schema-qualified name using the lookup
                target_full = etl_to_full.get(raw_target, f"dbo.{raw_target}")
                if raw_target:
                    foreign_keys.append(
                        {
                            "from_table": full_name,
                            "from_column": col_name,
                            "to_table": target_full,
                            "to_column": col_name,
                        }
                    )

        tables.append(
            {
                "schema": schema_part,
                "name": table_part,
                "full_name": full_name,
                "description": tbl.get("description") or "",
                "columns": columns,
            }
        )

    logger.info(
        "wholegraph.json loaded: %d tables, %d foreign keys",
        len(tables),
        len(foreign_keys),
    )
    return {"tables": tables, "foreign_keys": foreign_keys}
