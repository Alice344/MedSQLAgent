"""
Extract foreign key information from HTML files.

Finds where foreign keys are displayed in the HTML and captures all of them.
No web scraping, no browser — pure HTML parsing.

Pattern: <tr class="nowrap"> with <td class="key-symbol" title="Foreign Key"> and
<td class="column-name"> (in table.data-table or any table). Table name from
article[data-table-name], <h1>, or filename.

Usage:
  python scrape_foreign_keys.py --er-pages-dir er_pages --output foreign_keys.json
  python scrape_foreign_keys.py --html path/to/page.html --output foreign_keys.json

Requires: pip install beautifulsoup4
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List


def unwrap_viewer_html(html: str) -> str:
    """
    If the HTML is wrapped in a line-number viewer (e.g. Cursor "Line wrap" save),
    extract the inner document from td.line-content cells and return it.
    Otherwise return the original html.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return html

    soup = BeautifulSoup(html, "html.parser")
    cells = soup.select("td.line-content")
    if not cells:
        return html
    # Rebuild the original HTML from each line's text (entities are already decoded by BS)
    lines = []
    for td in cells:
        lines.append(td.get_text())
    inner = "\n".join(lines)
    # Only use if it looks like an HTML document
    if "<!DOCTYPE" in inner or (inner.strip().startswith("<") and "</html>" in inner):
        return inner
    return html


def get_table_name_from_html(html: str, filename: str = "") -> str:
    """Get table name from page: article[data-table-name], h1, or filename (e.g. er_MyTable.html)."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        if filename:
            base = Path(filename).stem
            return base.replace("er_", "", 1) if base.startswith("er_") else base
        return ""

    soup = BeautifulSoup(html, "html.parser")
    art = soup.select_one("article[data-table-name]")
    if art and art.get("data-table-name"):
        return (art.get("data-table-name") or "").strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    if filename:
        base = Path(filename).stem
        return base.replace("er_", "", 1) if base.startswith("er_") else base
    return ""


def extract_foreign_keys_from_html(html: str, from_table: str = "") -> List[Dict]:
    """
    Find where foreign keys are displayed and capture all of them.

    Handles two patterns:
    1. Center table "Foreign Keys" section: tr with key-link (e.g. AbstractedInfectionProviderBridge-SK)
       and td.column-name. to_table from key-link (part before first '-').
    2. Side cards: tr with td.key-symbol[title="Foreign Key"] and td.column-name in table.data-table.
       Table name from parent card's data-column-name or card title; to_table from "Links to:" or infer.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Install beautifulsoup4: pip install beautifulsoup4", file=sys.stderr)
        sys.exit(1)

    soup = BeautifulSoup(html, "html.parser")

    if not from_table:
        from_table = get_table_name_from_html(html)

    fks = []

    # --- Pattern 1: Center table "Foreign Keys" section (tr with key-link, no FK td) ---
    article = soup.select_one("article[data-table-name]")
    root = article if article else soup
    main_table = (article.get("data-table-name") if article else None) or from_table
    for table in root.select("table.data-table"):
        prev = table.find_previous_sibling() or table.find_previous()
        if prev and "Foreign Keys" in (prev.get_text() or ""):
            for tr in table.select("tbody tr"):
                key_link = tr.get("key-link")
                name_td = tr.select_one("td.column-name")
                if not key_link or not name_td:
                    continue
                from_col = (name_td.get("title") or name_td.get_text(strip=True) or "").strip()
                if not from_col:
                    continue
                # key-link e.g. "AbstractedInfectionProviderBridge-SK" -> to_table = AbstractedInfectionProviderBridge
                to_t = key_link.split("-")[0].strip() if key_link else ""
                to_c = "Id" if from_col.endswith("Id") else ("Key" if from_col.endswith("Key") else from_col)
                fks.append({
                    "from_table": main_table,
                    "from_column": from_col,
                    "to_table": to_t or main_table,
                    "to_column": to_c,
                    "constraint_name": "",
                })
            break

    # --- Pattern 2: Side cards / any table with tr that has td.key-symbol[title="Foreign Key"] ---
    for card in soup.select(".connection-border, .er-card"):
        card_table = card.get("data-column-name") or ""
        if not card_table:
            tit = card.select_one(".card-title a, .card-title")
            if tit:
                card_table = (tit.get("title") or tit.get_text(strip=True) or "").strip()
        if not card_table:
            card_table = from_table

        # "Links to:" gives to_table for this card
        to_table_from_card = ""
        for p in card.select("p.card-header"):
            if p and "Links to" in (p.get_text() or ""):
                n = p.find_next_sibling() or p.find_next()
                if n:
                    a = n.select_one("a[data-table-name]")
                    if a:
                        to_table_from_card = (a.get("data-table-name") or a.get("title") or a.get_text(strip=True) or "").strip()
                break

        for tbody in card.select("table.data-table tbody"):
            for tr in tbody.select("tr.nowrap, tr"):
                key_td = tr.select_one('td.key-symbol[title="Foreign Key"]')
                if not key_td:
                    continue
                name_td = tr.select_one("td.column-name")
                if not name_td:
                    continue
                from_column = (name_td.get("title") or name_td.get_text(strip=True) or "").strip()
                if not from_column:
                    continue

                to_table = to_table_from_card
                to_column = ""
                for td in tr.find_all("td"):
                    a = td.find("a", href=True)
                    if a and a.get("data-table-name"):
                        to_table = to_table or (a.get("data-table-name") or "").strip()
                    if td.get("data-ref") and "." in (td.get("data-ref") or ""):
                        to_table, to_column = (td.get("data-ref") or "").split(".", 1)[0].strip(), (td.get("data-ref") or "").split(".", 1)[1].strip()

                if not to_table or not to_column:
                    if from_column.endswith("Id"):
                        to_column = to_column or "Id"
                        to_table = to_table or from_column[:-2]
                    elif from_column.endswith("Key"):
                        to_column = to_column or from_column
                        to_table = to_table or (from_column[:-3] if len(from_column) > 3 else "")
                    else:
                        to_column = to_column or from_column
                        to_table = to_table or from_column

                fks.append({
                    "from_table": card_table,
                    "from_column": from_column,
                    "to_table": to_table or card_table,
                    "to_column": to_column or from_column,
                    "constraint_name": "",
                })

    # Deduplicate by (from_table, from_column), keeping first occurrence
    seen = set()
    out = []
    for r in fks:
        k = (r["from_table"], r["from_column"])
        if k not in seen and _looks_like_real_fk(r):
            seen.add(k)
            out.append(r)
    return out


def _looks_like_real_fk(fk: Dict) -> bool:
    """Filter out inferred junk (e.g. TomorrowDate -> TomorrowDate)."""
    from_t = (fk.get("from_table") or "").strip()
    from_c = (fk.get("from_column") or "").strip()
    to_t = (fk.get("to_table") or "").strip()
    to_c = (fk.get("to_column") or "").strip()
    if not from_t or not from_c:
        return False
    # Same table + same column is not a FK to another table
    if from_t == to_t and from_c == to_c:
        return False
    # Inferred garbage: to_table == to_column == from_column (e.g. TomorrowDate -> TomorrowDate)
    if to_t == to_c and to_t == from_c:
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Extract foreign keys from HTML files (no web scraping)")
    parser.add_argument("--er-pages-dir", type=Path, default=None,
                        help="Folder of HTML files (e.g. er_pages). All .html files are parsed.")
    parser.add_argument("--html", type=Path, default=None,
                        help="Single HTML file to parse")
    parser.add_argument("--output", type=Path, default=Path("foreign_keys.json"),
                        help="Output JSON file (default: foreign_keys.json)")
    args = parser.parse_args()

    if args.er_pages_dir is not None:
        er_dir = Path(args.er_pages_dir)
        if not er_dir.is_dir():
            # Try relative to script directory (e.g. scripts/er_pages when cwd is scripts)
            script_dir = Path(__file__).resolve().parent
            for candidate in [script_dir / er_dir, script_dir / er_dir.name]:
                if candidate.is_dir():
                    er_dir = candidate
                    break
            else:
                print(f"Not a directory: {args.er_pages_dir}", file=sys.stderr)
                sys.exit(1)
        html_files = sorted(er_dir.glob("*.html"))
        if not html_files:
            print(f"No .html files in {er_dir}", file=sys.stderr)
            sys.exit(1)
        paths = html_files
    elif args.html:
        p = Path(args.html)
        if p.exists():
            paths = [p]
        elif Path(str(p) + ".html").exists():
            paths = [Path(str(p) + ".html")]
        else:
            print(f"File not found: {p} (tried with .html as well)", file=sys.stderr)
            sys.exit(1)
    else:
        print("Use --er-pages-dir <folder> or --html <file>", file=sys.stderr)
        sys.exit(1)

    all_fks = []
    seen = set()
    for i, path in enumerate(paths):
        raw = path.read_text(encoding="utf-8")
        html = unwrap_viewer_html(raw)
        from_table = get_table_name_from_html(html, str(path)) or path.stem.replace("er_", "", 1)
        fks = extract_foreign_keys_from_html(html, from_table)
        for fk in fks:
            key = (fk.get("from_table"), fk.get("from_column"), fk.get("to_table"), fk.get("to_column"))
            if key not in seen and fk.get("from_table") and fk.get("from_column"):
                seen.add(key)
                all_fks.append(fk)
        print(f"[{i+1}/{len(paths)}] {path.name}  table={from_table or '?'}  FKs={len(fks)}  total={len(all_fks)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(all_fks, indent=2), encoding="utf-8")
    print(f"\nWrote {len(all_fks)} foreign keys to {args.output}")


if __name__ == "__main__":
    main()
