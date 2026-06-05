"""
dashboard.py

Generates a self-contained HTML dashboard from benchmark results
and opens it in the default browser.

Usage
-----
    from utils.dashboard import generate_dashboard
    generate_dashboard(results, cases)          # opens browser automatically
    generate_dashboard(results, cases, open_browser=False)  # just writes file
"""

import json
import os
import tempfile
import webbrowser
from datetime import datetime


def _score_color(score: float) -> str:
    if score >= 0.9:  return "#56d364"
    if score >= 0.7:  return "#e3b341"
    return "#f85149"


def _bool_html(val: bool) -> str:
    if val:
        return '<span class="bool-true">✓ true</span>'
    return '<span class="bool-false">✗ false</span>'


def _badge(passed: bool) -> str:
    cls = "pass" if passed else "fail"
    txt = "PASS" if passed else "FAIL"
    return f'<span class="badge {cls}">{txt}</span>'


def _score_bar_html(score: float, width: int = 120) -> str:
    fill = int(score * width)
    color = _score_color(score)
    return (
        f'<div class="score-bar-track" style="width:{width}px">'
        f'<div class="score-bar-fill" style="width:{fill}px;background:{color}"></div>'
        f'</div>'
    )


def _code_block(code: str) -> str:
    escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<pre class="code-block">{escaped}</pre>'


def _rows(data: dict, keys: list[tuple]) -> str:
    """Render a list of (label, value, type) tuples as table rows."""
    html = ""
    for label, val, kind in keys:
        if val is None or val == "" or val == []:
            continue
        if kind == "bool":
            v = _bool_html(val)
        elif kind == "score":
            color = _score_color(float(val))
            v = f'<span style="color:{color};font-weight:700">{val}</span>'
        elif kind == "badge":
            v = _badge(val)
        elif kind == "dim":
            v = f'<span class="dim">{val}</span>'
        elif kind == "code":
            v = _code_block(val)
        elif kind == "warn":
            v = f'<span class="warn">{val}</span>'
        else:
            v = str(val)
        html += f'<div class="row"><span class="key">{label}</span><span class="val">{v}</span></div>\n'
    return html


def _card(title: str, dot_color: str, subtitle: str, body: str, open: bool = False) -> str:
    open_class = "open" if open else ""
    return f'''
<div class="card">
  <div class="card-header" onclick="toggle(this)">
    <span class="dot" style="background:{dot_color}"></span>
    <span class="card-title" style="color:{dot_color}">{title}</span>
    <span class="card-subtitle">{subtitle}</span>
    <span class="chevron {open_class}">▶</span>
  </div>
  <div class="card-body {open_class}">{body}</div>
</div>'''


def _repair_history_html(history: list) -> str:
    if not history:
        return '<span class="dim">No retries — passed on first attempt</span>'
    html = ""
    for entry in history:
        attempt = entry.get("attempt", "?")
        ev      = entry.get("evaluation", {})
        crit    = entry.get("critique", {})
        score   = ev.get("score", 0)
        color   = _score_color(score)
        guidance = crit.get("retry_guidance", [])
        guidance_html = "".join(f"<li>{g}</li>" for g in guidance)

        html += f'''
<div class="subcard">
  <div class="subcard-title">Attempt {attempt}
    <span style="color:{color};margin-left:8px;font-weight:700">{score}</span>
    {"" if ev.get("passed") else '<span class="badge fail" style="font-size:10px;padding:1px 6px;margin-left:6px">FAILED</span>'}
  </div>
  {_rows(ev, [
      ("intent_preserved",      ev.get("intent_preserved"),      "bool"),
      ("root_cause_fixed",      ev.get("root_cause_fixed"),      "bool"),
      ("minimal_fix",           ev.get("minimal_fix"),           "bool"),
      ("introduced_regression", ev.get("introduced_regression"), "bool"),
      ("eval reasoning",        ev.get("reasoning"),             "str"),
  ])}
  <div class="subcard-title" style="margin-top:10px">Critique</div>
  {_rows(crit, [
      ("failure_type",  crit.get("failure_type"),  "warn"),
      ("should_retry",  crit.get("should_retry"),  "bool"),
      ("critique",      crit.get("critique"),       "str"),
  ])}
  {"<ul class='guidance'>" + guidance_html + "</ul>" if guidance else ""}
</div>'''
    return html


def _run_html(result: dict, case: dict, index: int) -> str:
    run_id   = result.get("run_id", "?")
    ev       = result.get("evaluation", {})
    analysis = result.get("analysis", {})
    fix      = result.get("fix", {})
    metrics  = result.get("metrics", {})
    exec_r   = result.get("execution_result", {})
    history  = result.get("repair_history", [])
    heur     = ev.get("heuristics", {})

    passed   = ev.get("passed", False)
    score    = ev.get("score", 0.0)
    bug_type = case.get("bug_type", "Unknown")
    task_id  = case.get("task_id", run_id)
    mutation = case.get("mutation_desc", "")
    sc       = _score_color(score)

    penalties     = heur.get("penalties", [])
    penalties_str = ", ".join(penalties) if penalties else "none"
    struct        = heur.get("structural_ratio", None)
    struct_str    = f"{struct*100:.2f}%" if struct is not None else "—"

    repair_count  = len(history)

    # ── Analysis card ───────────────────────────────────────────────────────
    analysis_body = _rows(analysis, [
        ("root_cause",       analysis.get("root_cause"),       "str"),
        ("error_line",       analysis.get("error_line"),       "str"),
        ("analyzer_latency", analysis.get("analyzer_latency"), "dim"),
        ("parse_success",    analysis.get("parse_success"),    "bool"),
        ("reasoning",        analysis.get("reasoning"),        "str"),
    ])

    # ── Repair history card ──────────────────────────────────────────────────
    history_subtitle = (
        f"{repair_count} retr{'y' if repair_count == 1 else 'ies'} · retried"
        if repair_count else "no retries"
    )
    history_body = _repair_history_html(history)

    # ── Fix card ─────────────────────────────────────────────────────────────
    fix_body = _rows(fix, [
        ("explanation",   fix.get("explanation"),   "str"),
        ("fixer_latency", fix.get("fixer_latency"), "dim"),
        ("parse_success", fix.get("parse_success"), "bool"),
        ("patched_code",  fix.get("patched_code"),  "code"),
    ])

    # ── Execution card ───────────────────────────────────────────────────────
    exec_body = _rows(exec_r, [
        ("success", exec_r.get("success"), "bool"),
        ("stdout",  exec_r.get("stdout") or "—", "dim"),
        ("stderr",  exec_r.get("stderr") or "—", "dim"),
    ])

    # ── Evaluation card ──────────────────────────────────────────────────────
    eval_body = _rows(ev, [
        ("passed",                ev.get("passed"),                "badge"),
        ("score (blended)",       score,                           "score"),
        ("intent_preserved",      ev.get("intent_preserved"),      "bool"),
        ("root_cause_fixed",      ev.get("root_cause_fixed"),      "bool"),
        ("minimal_fix",           ev.get("minimal_fix"),           "bool"),
        ("introduced_regression", ev.get("introduced_regression"), "bool"),
        ("reasoning",             ev.get("reasoning"),             "str"),
    ])
    eval_body += f'''
<div class="subcard-title" style="margin-top:10px">Heuristics</div>
{_rows(heur, [
    ("heuristic score",  heur.get("score"),     "score"),
    ("structural_ratio", struct_str,             "dim"),
    ("penalties",        penalties_str,          "dim"),
])}'''

    # ── Metrics card ─────────────────────────────────────────────────────────
    metrics_body = _rows(metrics, [
        ("analysis_latency",  metrics.get("analysis_latency"),  "dim"),
        ("fix_latency",       metrics.get("fix_latency"),       "dim"),
        ("execution_latency", metrics.get("execution_latency"), "dim"),
        ("eval_latency",      metrics.get("eval_latency"),      "dim"),
        ("critique_latency",  metrics.get("critique_latency"),  "dim"),
        ("total_latency",     metrics.get("total_latency"),     "str"),
    ])

    return f'''
<div class="run-wrapper" id="run-{index}">
  <div class="run-header">
    <span class="run-index">#{index}</span>
    <span class="run-task">{task_id}</span>
    {_badge(passed)}
    <span class="run-bugtype">{bug_type}</span>
    <span class="run-id">run {run_id}</span>
    <div class="run-score-wrap">
      {_score_bar_html(score, 100)}
      <span class="run-score" style="color:{sc}">{score:.3f}</span>
    </div>
  </div>
  <div class="mutation-desc">{mutation}</div>

  {_card("ANALYSIS",       "#79c0ff", f"{analysis.get('root_cause','?')} · line {analysis.get('error_line','?')} · {analysis.get('analyzer_latency','?')}", analysis_body, open=True)}
  {_card("REPAIR HISTORY", "#e3b341", history_subtitle, history_body, open=bool(history))}
  {_card("FIX",            "#56d364", f"{fix.get('fixer_latency','?')}", fix_body, open=True)}
  {_card("EXECUTION",      "#56d364" if exec_r.get("success") else "#f85149", "success" if exec_r.get("success") else "failed", exec_body, open=False)}
  {_card("EVALUATION",     "#d2a8ff", f"score {score:.3f} · {metrics.get('eval_latency','?')}", eval_body, open=True)}
  {_card("METRICS",        "#484f58", f"total {metrics.get('total_latency','?')}", metrics_body, open=False)}
</div>'''


def _summary_html(results: list, cases: list) -> str:
    from collections import defaultdict
    total   = len(results)
    passed  = sum(1 for r in results if r.get("evaluation", {}).get("passed"))
    scores  = [r.get("evaluation", {}).get("score", 0.0) for r in results]
    avg_sc  = sum(scores) / total if total else 0.0
    pass_rt = passed / total if total else 0.0
    sc_color = _score_color(avg_sc)
    pr_color = _score_color(pass_rt)

    by_type = defaultdict(lambda: {"total": 0, "passed": 0})
    for r, c in zip(results, cases):
        bt = c.get("bug_type", "Unknown")
        by_type[bt]["total"]  += 1
        by_type[bt]["passed"] += int(r.get("evaluation", {}).get("passed", False))

    type_rows = ""
    for bt, data in sorted(by_type.items()):
        rate = data["passed"] / data["total"] if data["total"] else 0
        rc   = _score_color(rate)
        fill = int(rate * 80)
        type_rows += f'''
<div class="type-row">
  <span class="type-name">{bt}</span>
  <span class="type-counts" style="color:{rc}">{data["passed"]}/{data["total"]}</span>
  <div class="type-bar-track"><div class="type-bar-fill" style="width:{fill}px;background:{rc}"></div></div>
  <span class="type-rate" style="color:{rc}">{rate:.0%}</span>
</div>'''

    return f'''
<div class="summary-grid">
  <div class="summary-card">
    <div class="summary-label">pass@1</div>
    <div class="summary-val" style="color:{pr_color}">{passed}/{total}</div>
    <div class="summary-sub" style="color:{pr_color}">{pass_rt:.1%}</div>
  </div>
  <div class="summary-card">
    <div class="summary-label">avg score</div>
    <div class="summary-val" style="color:{sc_color}">{avg_sc:.3f}</div>
    {_score_bar_html(avg_sc, 80)}
  </div>
  <div class="summary-card">
    <div class="summary-label">total cases</div>
    <div class="summary-val">{total}</div>
  </div>
  <div class="summary-card">
    <div class="summary-label">failed</div>
    <div class="summary-val" style="color:#f85149">{total - passed}</div>
  </div>
</div>
<div class="type-breakdown">{type_rows}</div>'''


def _nav_items(results: list, cases: list) -> str:
    items = []
    for i, (r, c) in enumerate(zip(results, cases)):
        passed  = r.get("evaluation", {}).get("passed", False)
        cls     = "pass" if passed else "fail"
        label   = "PASS" if passed else "FAIL"
        task_id = c.get("task_id", r.get("run_id", "?"))
        items.append(
            f'<a class="nav-item {cls}" href="#run-{i+1}">'
            f'<span>{task_id}</span>'
            f'<span class="nav-badge">{label}</span>'
            f'</a>'
        )
    return "\n    ".join(items)


def _html(results: list, cases: list) -> str:
    runs_html    = "\n".join(_run_html(r, c, i+1) for i, (r, c) in enumerate(zip(results, cases)))
    summary_html = _summary_html(results, cases)
    now          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total        = len(results)
    passed       = sum(1 for r in results if r.get("evaluation", {}).get("passed"))

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agentic Debugger — Benchmark Results</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:       #0d1117;
    --bg2:      #161b22;
    --bg3:      #21262d;
    --border:   #30363d;
    --border2:  #21262d;
    --text:     #c9d1d9;
    --dim:      #8b949e;
    --dim2:     #484f58;
    --green:    #56d364;
    --yellow:   #e3b341;
    --red:      #f85149;
    --cyan:     #79c0ff;
    --magenta:  #d2a8ff;
    --white:    #f0f6fc;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12.5px;
    line-height: 1.7;
    min-height: 100vh;
  }}

  /* ── Layout ── */
  .page {{ display: flex; min-height: 100vh; }}

  .sidebar {{
    width: 260px;
    flex-shrink: 0;
    background: var(--bg2);
    border-right: 1px solid var(--border);
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
    padding: 20px 0;
  }}

  .main {{
    flex: 1;
    padding: 28px 32px;
    overflow-x: hidden;
  }}

  /* ── Sidebar ── */
  .sidebar-title {{
    font-family: 'Syne', sans-serif;
    font-size: 15px;
    font-weight: 800;
    color: var(--white);
    padding: 0 18px 16px;
    border-bottom: 1px solid var(--border2);
    margin-bottom: 12px;
    letter-spacing: -0.02em;
  }}

  .sidebar-subtitle {{
    color: var(--dim);
    font-size: 10.5px;
    font-weight: 400;
    display: block;
    margin-top: 2px;
  }}

  .nav-item {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 18px;
    cursor: pointer;
    border-left: 2px solid transparent;
    transition: all 0.15s;
    font-size: 11.5px;
    color: var(--dim);
    text-decoration: none;
  }}

  .nav-item:hover {{ color: var(--white); background: var(--bg3); }}
  .nav-item.pass  {{ border-left-color: var(--green); }}
  .nav-item.fail  {{ border-left-color: var(--red); }}
  .nav-item .nav-badge {{
    margin-left: auto;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 3px;
  }}
  .nav-item.pass .nav-badge {{ background: #1a4731; color: var(--green); }}
  .nav-item.fail .nav-badge {{ background: #4a1515; color: var(--red); }}

  .nav-section {{
    padding: 10px 18px 4px;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--dim2);
  }}

  /* ── Header ── */
  .page-header {{
    margin-bottom: 24px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }}

  .page-title {{
    font-family: 'Syne', sans-serif;
    font-size: 22px;
    font-weight: 800;
    color: var(--white);
    letter-spacing: -0.03em;
    margin-bottom: 4px;
  }}

  .page-meta {{ color: var(--dim); font-size: 11px; }}

  /* ── Summary ── */
  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 16px;
  }}

  .summary-card {{
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
  }}

  .summary-label {{ color: var(--dim); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }}
  .summary-val   {{ font-size: 24px; font-weight: 700; color: var(--white); margin-bottom: 4px; }}
  .summary-sub   {{ font-size: 11px; }}

  .type-breakdown {{ display: flex; flex-direction: column; gap: 6px; margin-bottom: 28px; }}
  .type-row {{ display: flex; align-items: center; gap: 12px; padding: 6px 12px; background: var(--bg2); border: 1px solid var(--border2); border-radius: 6px; }}
  .type-name {{ min-width: 130px; color: var(--text); }}
  .type-counts {{ min-width: 40px; font-weight: 700; }}
  .type-bar-track {{ flex: 1; height: 4px; background: var(--bg3); border-radius: 2px; }}
  .type-bar-fill  {{ height: 100%; border-radius: 2px; }}
  .type-rate {{ min-width: 40px; text-align: right; font-weight: 700; }}

  /* ── Run ── */
  .run-wrapper {{
    margin-bottom: 24px;
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    scroll-margin-top: 20px;
  }}

  .run-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }}

  .run-index {{ color: var(--dim2); font-size: 11px; }}
  .run-task  {{ font-weight: 700; color: var(--white); font-size: 13px; }}
  .run-bugtype {{ color: var(--cyan); }}
  .run-id    {{ color: var(--dim2); font-size: 10.5px; }}
  .run-score-wrap {{ margin-left: auto; display: flex; align-items: center; gap: 8px; }}
  .run-score {{ font-weight: 700; font-size: 14px; }}

  .mutation-desc {{
    padding: 8px 16px;
    background: var(--bg);
    color: var(--dim);
    font-size: 11px;
    border-bottom: 1px solid var(--border2);
  }}

  /* ── Cards ── */
  .card {{ border-bottom: 1px solid var(--border2); }}
  .card:last-child {{ border-bottom: none; }}

  .card-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 16px;
    cursor: pointer;
    user-select: none;
    transition: background 0.15s;
  }}
  .card-header:hover {{ background: var(--bg3); }}

  .dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
  .card-title    {{ font-weight: 700; font-size: 11px; letter-spacing: 0.05em; }}
  .card-subtitle {{ color: var(--dim); font-size: 11px; }}
  .chevron {{ margin-left: auto; color: var(--dim2); font-size: 10px; transition: transform 0.2s; }}
  .chevron.open {{ transform: rotate(90deg); }}

  .card-body {{ display: none; padding: 10px 16px 14px; }}
  .card-body.open {{ display: block; }}

  /* ── Rows ── */
  .row {{
    display: flex;
    gap: 12px;
    padding: 4px 0;
    border-bottom: 1px solid var(--border2);
    align-items: flex-start;
  }}
  .row:last-child {{ border-bottom: none; }}
  .key {{
    color: var(--cyan);
    min-width: 170px;
    flex-shrink: 0;
    font-size: 11.5px;
  }}
  .val {{ font-size: 11.5px; word-break: break-word; flex: 1; }}

  .bool-true  {{ color: var(--green); font-weight: 700; }}
  .bool-false {{ color: var(--red);   font-weight: 700; }}
  .dim        {{ color: var(--dim); }}
  .warn       {{ color: var(--yellow); font-weight: 700; }}

  /* ── Badges ── */
  .badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 4px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.04em;
  }}
  .badge.pass {{ background: #1a4731; color: var(--green); }}
  .badge.fail {{ background: #4a1515; color: var(--red); }}

  /* ── Score bar ── */
  .score-bar-track {{ height: 5px; background: var(--bg3); border-radius: 3px; overflow: hidden; }}
  .score-bar-fill  {{ height: 100%; border-radius: 3px; }}

  /* ── Subcard ── */
  .subcard {{
    background: var(--bg);
    border: 1px solid var(--border2);
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 10px;
  }}
  .subcard-title {{
    color: var(--dim);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    margin-bottom: 8px;
  }}

  /* ── Code block ── */
  .code-block {{
    background: #010409;
    border: 1px solid var(--border2);
    border-radius: 6px;
    padding: 12px;
    font-size: 11.5px;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--text);
    max-height: 240px;
    overflow-y: auto;
    margin-top: 6px;
    line-height: 1.6;
  }}

  /* ── Guidance list ── */
  ul.guidance {{
    margin: 8px 0 0 16px;
    color: var(--dim);
    font-size: 11.5px;
  }}
  ul.guidance li {{ margin-bottom: 4px; }}

  /* ── Scrollbar ── */
  ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background: var(--bg3); border-radius: 3px; }}
</style>
</head>
<body>
<div class="page">

  <!-- Sidebar nav -->
  <aside class="sidebar">
    <div class="sidebar-title">
      Agentic Debugger
      <span class="sidebar-subtitle">HumanEval Benchmark</span>
    </div>
    <div class="nav-section">Runs ({total})</div>
    {_nav_items(results, cases)}
  </aside>

  <!-- Main content -->
  <main class="main">
    <div class="page-header">
      <div class="page-title">Benchmark Results</div>
      <div class="page-meta">
        Qwen2.5-Coder-32B-AWQ &nbsp;·&nbsp; {now} &nbsp;·&nbsp; {passed}/{total} passed
      </div>
    </div>

    {summary_html}

    <div class="nav-section" style="padding:0 0 12px;color:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:0.08em;">Run Details</div>

    {runs_html}
  </main>
</div>

<script>
  function toggle(header) {{
    const body    = header.nextElementSibling;
    const chevron = header.querySelector('.chevron');
    body.classList.toggle('open');
    chevron.classList.toggle('open');
  }}
</script>
</body>
</html>'''


def generate_dashboard(
    results: list[dict],
    cases:   list[dict],
    output_path: str | None = None,
    open_browser: bool = True,
) -> str:
    """
    Generate an HTML dashboard from benchmark results.

    Parameters
    ----------
    results      : list of context dicts from DebugOrchestrator.run()
    cases        : matching list of benchmark case dicts
    output_path  : where to write the HTML (default: temp file)
    open_browser : whether to open the dashboard in the default browser

    Returns
    -------
    Path to the generated HTML file.
    """
    html = _html(results, cases)

    if output_path is None:
        # Save next to main_humaneval.py in the project root, not /tmp
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_path  = os.path.join(project_root, "benchmark_results.html")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    abs_path = os.path.abspath(output_path)
    print(f"\n  Dashboard written → {abs_path}")

    if open_browser:
        import subprocess
        try:
            # xdg-open is reliable on Linux desktops (Ubuntu, Fedora, etc.)
            subprocess.Popen(["xdg-open", abs_path],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            print(f"  Opening in browser...\n")
        except FileNotFoundError:
            # Fallback for non-Linux or missing xdg-open
            webbrowser.open(f"file://{abs_path}")
            print(f"  If browser didn't open, manually open:\n  file://{abs_path}\n")

    return output_path
