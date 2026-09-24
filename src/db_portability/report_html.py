"""
Static HTML renderer for `dbp-scan --format html`. Takes the same
(file, lineno, col, code, message, severity) records the text reporter in
cli.py prints to the terminal and turns them into a single self-contained
HTML report (no external assets, so it can be opened offline or attached to
a CI artifact).
"""
import html
import itertools
from datetime import datetime, timezone

_STYLE = """
:root {
  color-scheme: light dark;
  --bg: #ffffff;
  --fg: #1c1e21;
  --muted: #6b7280;
  --border: #e5e7eb;
  --panel: #f8f9fb;
  --error: #b91c1c;
  --error-bg: #fef2f2;
  --warn: #92400e;
  --warn-bg: #fffbeb;
  --accent: #2563eb;
  --ok: #15803d;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #16181d;
    --fg: #e6e8eb;
    --muted: #9aa2ad;
    --border: #2c2f36;
    --panel: #1d2026;
    --error: #f87171;
    --error-bg: #2a1414;
    --warn: #fbbf24;
    --warn-bg: #2a2210;
    --accent: #60a5fa;
    --ok: #4ade80;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 2rem 1.25rem 4rem;
  background: var(--bg);
  color: var(--fg);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
main { max-width: 960px; margin: 0 auto; }
h1 { font-size: 1.4rem; margin: 0 0 0.25rem; }
.subtitle { color: var(--muted); margin: 0 0 1.5rem; font-size: 0.9rem; }
.summary {
  display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1.5rem;
}
.card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  padding: 0.75rem 1rem; min-width: 120px;
}
.card .num { font-size: 1.5rem; font-weight: 600; display: block; }
.card .label { color: var(--muted); font-size: 0.8rem; }
.codes { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1.5rem; }
.code-chip {
  border: 1px solid var(--border); border-radius: 999px; padding: 0.2rem 0.65rem;
  font-size: 0.8rem; color: var(--muted); background: var(--panel);
}
.controls {
  display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; align-items: center;
}
.controls input[type="search"] {
  flex: 1; min-width: 180px; padding: 0.45rem 0.6rem; border-radius: 6px;
  border: 1px solid var(--border); background: var(--bg); color: var(--fg); font-size: 0.9rem;
}
.controls button {
  padding: 0.4rem 0.75rem; border-radius: 6px; border: 1px solid var(--border);
  background: var(--panel); color: var(--fg); font-size: 0.85rem; cursor: pointer;
}
.controls button.active { border-color: var(--accent); color: var(--accent); }
.file-group { border: 1px solid var(--border); border-radius: 8px; margin-bottom: 1rem; overflow: hidden; }
.file-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0.6rem 0.9rem; background: var(--panel); font-weight: 600;
  font-size: 0.9rem; word-break: break-all;
}
.file-header .count { color: var(--muted); font-weight: 400; font-size: 0.8rem; }
table { width: 100%; border-collapse: collapse; }
tr.issue-row td { padding: 0.5rem 0.9rem; border-top: 1px solid var(--border); vertical-align: top; font-size: 0.88rem; }
td.loc { color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; width: 5.5rem; }
.badge { display: inline-block; border-radius: 4px; padding: 0.05rem 0.4rem; font-size: 0.72rem; font-weight: 600; text-transform: uppercase; }
.badge.error { color: var(--error); background: var(--error-bg); }
.badge.warn { color: var(--warn); background: var(--warn-bg); }
.msg code { background: var(--panel); border-radius: 4px; padding: 0 0.25rem; }
.syntax-errors { margin-bottom: 1.5rem; }
.syntax-errors li { margin-bottom: 0.25rem; }
.empty { color: var(--ok); font-weight: 600; padding: 1rem 0; }
footer { color: var(--muted); font-size: 0.78rem; margin-top: 2rem; }
tr.issue-row[hidden], .file-group[hidden] { display: none; }
"""

_SCRIPT = """
(function () {
  var search = document.getElementById('dbp-search');
  var buttons = document.querySelectorAll('.controls button[data-severity]');
  var active = 'all';

  function apply() {
    var term = (search.value || '').toLowerCase();
    document.querySelectorAll('.file-group').forEach(function (group) {
      var visible = 0;
      group.querySelectorAll('tr.issue-row').forEach(function (row) {
        var matchesSeverity = active === 'all' || row.dataset.severity === active;
        var matchesTerm = !term || row.dataset.search.indexOf(term) !== -1;
        var show = matchesSeverity && matchesTerm;
        row.hidden = !show;
        if (show) visible++;
      });
      group.hidden = visible === 0;
    });
  }

  buttons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      buttons.forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      active = btn.dataset.severity;
      apply();
    });
  });
  if (search) search.addEventListener('input', apply);
})();
"""


def render_html(records, meta):
    """Render a self-contained HTML report.

    records: list of dicts with keys file, lineno, col, code, message, severity.
    meta: dict with source, target, total, total_files, files_with_issues,
          counts (code -> int), syntax_errors (list of (path, SyntaxError)),
          suppressed (int, optional).
    """
    esc = html.escape
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    source, target = meta["source"], meta["target"]
    total = meta["total"]
    counts = meta["counts"]
    syntax_errors = meta.get("syntax_errors", [])

    cards = [
        (str(total), "Issue(s)"),
        (str(meta["files_with_issues"]), "File(s) with issues"),
        (str(meta["total_files"]), "File(s) scanned"),
    ]
    if meta.get("suppressed"):
        cards.append((str(meta["suppressed"]), "Suppressed"))
    cards_html = "".join(
        f'<div class="card"><span class="num">{esc(n)}</span>'
        f'<span class="label">{esc(label)}</span></div>'
        for n, label in cards
    )

    codes_html = "".join(
        f'<span class="code-chip">{esc(code)} &times; {n}</span>'
        for code, n in sorted(counts.items())
    )

    syntax_html = ""
    if syntax_errors:
        items = "".join(
            f"<li><code>{esc(path)}</code> &mdash; {esc(exc.msg)} "
            f"(line {exc.lineno})</li>"
            for path, exc in syntax_errors
        )
        syntax_html = (
            '<section class="syntax-errors">'
            "<h2>Files that could not be parsed</h2>"
            f"<ul>{items}</ul></section>"
        )

    if not records:
        body_html = f'<p class="empty">No {esc(source)} &rarr; {esc(target)} portability issues found.</p>'
    else:
        groups = []
        for path, rows in itertools.groupby(records, key=lambda r: r["file"]):
            rows = list(rows)
            row_html = []
            for r in rows:
                loc = f'{r["lineno"]}:{r["col"] + 1}'
                search_blob = esc(f'{r["file"]} {r["code"]} {r["message"]}').lower()
                row_html.append(
                    '<tr class="issue-row" data-severity="{sev}" data-search="{search}">'
                    '<td class="loc">{loc}</td>'
                    '<td><span class="badge {sev}">{sev}</span></td>'
                    '<td class="msg">{msg}</td></tr>'.format(
                        sev=r["severity"],
                        search=search_blob,
                        loc=esc(loc),
                        msg=esc(r["message"]),
                    )
                )
            groups.append(
                '<div class="file-group">'
                f'<div class="file-header"><span>{esc(path)}</span>'
                f'<span class="count">{len(rows)} issue(s)</span></div>'
                f"<table><tbody>{''.join(row_html)}</tbody></table>"
                "</div>"
            )
        body_html = (
            '<div class="controls">'
            '<button data-severity="all" class="active">All</button>'
            '<button data-severity="error">Errors</button>'
            '<button data-severity="warn">Warnings</button>'
            '<input type="search" id="dbp-search" placeholder="Filter by file, code or message...">'
            "</div>" + "".join(groups)
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>db-portability report: {esc(source)} &rarr; {esc(target)}</title>
<style>{_STYLE}</style>
</head>
<body>
<main>
  <h1>Database portability report</h1>
  <p class="subtitle">{esc(source)} &rarr; {esc(target)} &middot; generated {esc(generated_at)}</p>
  <div class="summary">{cards_html}</div>
  <div class="codes">{codes_html}</div>
  {syntax_html}
  {body_html}
  <footer>Generated by dbp-scan --format html</footer>
</main>
<script>{_SCRIPT}</script>
</body>
</html>
"""
