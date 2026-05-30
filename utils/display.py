"""
display.py

Terminal display for the agentic debugger benchmark.
Uses only the standard library (no rich/blessed required).

Two public functions:
    print_case_result(result, case)   — call after each orchestrator.run()
    print_final_report(results, cases) — call once at the end
"""

import os
import shutil

# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------

def _width() -> int:
    return min(shutil.get_terminal_size((100, 40)).columns, 120)

def _hr(char: str = "─", color: str = "") -> None:
    w = _width()
    print(f"{color}{char * w}{RESET}")

def _center(text: str, width: int | None = None) -> str:
    w = width or _width()
    return text.center(w)

# ANSI codes
RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"

BLACK   = "\033[30m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"

BG_BLACK   = "\033[40m"
BG_RED     = "\033[41m"
BG_GREEN   = "\033[42m"
BG_YELLOW  = "\033[43m"
BG_BLUE    = "\033[44m"
BG_MAGENTA = "\033[45m"
BG_CYAN    = "\033[46m"
BG_WHITE   = "\033[47m"

# Bright variants
BRIGHT_GREEN   = "\033[92m"
BRIGHT_RED     = "\033[91m"
BRIGHT_YELLOW  = "\033[93m"
BRIGHT_CYAN    = "\033[96m"
BRIGHT_BLUE    = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_WHITE   = "\033[97m"

# ---------------------------------------------------------------------------
# Score / pass helpers
# ---------------------------------------------------------------------------

def _score_color(score: float) -> str:
    if score >= 0.9:  return BRIGHT_GREEN
    if score >= 0.7:  return BRIGHT_YELLOW
    return BRIGHT_RED

def _pass_badge(passed: bool) -> str:
    if passed:
        return f"{BG_GREEN}{BLACK}{BOLD}  PASS  {RESET}"
    return f"{BG_RED}{WHITE}{BOLD}  FAIL  {RESET}"

def _bug_type_color(bug_type: str) -> str:
    colors = {
        "TypeError":        BRIGHT_CYAN,
        "NameError":        BRIGHT_MAGENTA,
        "IndexError":       BRIGHT_YELLOW,
        "ZeroDivisionError": BRIGHT_RED,
        "SyntaxError":      BRIGHT_BLUE,
        "LogicError":       YELLOW,
        "AttributeError":   CYAN,
        "KeyError":         MAGENTA,
    }
    return colors.get(bug_type, WHITE)

def _score_bar(score: float, width: int = 24) -> str:
    filled = round(score * width)
    empty  = width - filled
    color  = _score_color(score)
    bar    = f"{color}{'█' * filled}{DIM}{'░' * empty}{RESET}"
    return bar

def _fmt_latency(s: str) -> str:
    """'3.4587s' → '3.46s'"""
    try:
        return f"{float(s.rstrip('s')):.2f}s"
    except Exception:
        return s

def _truncate(text: str, max_len: int = 72) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= max_len else text[:max_len - 1] + "…"

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

def print_banner() -> None:
    w = _width()
    print()
    _hr("═", BRIGHT_BLUE)
    title = f"{BOLD}{BRIGHT_WHITE}  AGENTIC DEBUGGER  {RESET}{DIM}// HumanEval Benchmark{RESET}"
    print(f"{BRIGHT_BLUE}║{RESET}  {title}")
    subtitle = f"{DIM}  Qwen2.5-Coder-32B-AWQ  ·  Analyze → Fix → Execute → Evaluate → Critique{RESET}"
    print(subtitle)
    _hr("═", BRIGHT_BLUE)
    print()

# ---------------------------------------------------------------------------
# Per-case result
# ---------------------------------------------------------------------------

def print_case_result(result: dict, case: dict, case_num: int, total: int) -> None:
    w         = _width()
    ev        = result.get("evaluation", {})
    metrics   = result.get("metrics", {})
    analysis  = result.get("analysis", {})
    fix       = result.get("fix", {})
    execution = result.get("execution_result", {})

    passed    = ev.get("passed", False)
    score     = ev.get("score", 0.0)
    bug_type  = case.get("bug_type", "Unknown")
    task_id   = case.get("task_id", result.get("run_id", "?"))
    mutation  = case.get("mutation_desc", "")
    run_id    = result.get("run_id", "")

    bt_color  = _bug_type_color(bug_type)
    sc_color  = _score_color(score)

    # ── Header row ──────────────────────────────────────────────────────────
    print()
    _hr("─", DIM)
    progress = f"{DIM}[{case_num}/{total}]{RESET}"
    id_str   = f"{BRIGHT_WHITE}{BOLD}{task_id}{RESET}"
    badge    = _pass_badge(passed)
    bug_str  = f"{bt_color}{BOLD}{bug_type}{RESET}"
    rid_str  = f"{DIM}#{run_id}{RESET}"
    print(f"  {progress}  {id_str}  {badge}  {bug_str}  {rid_str}")

    # ── Mutation description ─────────────────────────────────────────────────
    if mutation:
        print(f"  {DIM}original code mutation :{RESET} {_truncate(mutation, w - 16)}")

    print()

    # ── Three-column grid: Analysis | Fix | Evaluation ───────────────────────
    col = (w - 6) // 3

    def _col_line(label: str, value: str, color: str = WHITE) -> str:
        return f"  {DIM}{label:<12}{RESET}{color}{value}{RESET}"

    # Column content
    root_cause  = analysis.get("root_cause", "—")
    error_line  = str(analysis.get("error_line", "—"))
    a_latency   = _fmt_latency(metrics.get("analysis_latency", "—"))
    reasoning_a = analysis.get("reasoning", "").replace("\n", " ")

    f_latency       = _fmt_latency(metrics.get("fix_latency", "—"))
    explanation     = fix.get("explanation", "").replace("\n", " ")
    heuristics      = ev.get("heuristics", {})
    struct_ratio    = heuristics.get("structural_ratio", None)
    struct_str      = f"{struct_ratio*100:.2f}%" if struct_ratio is not None else "—"
    penalties       = heuristics.get("penalties", [])
    penalties_str   = ", ".join(penalties) if penalties else "none"
    h_score         = heuristics.get("score", None)
    h_score_str     = f"{h_score:.3f}" if h_score is not None else "—"
    repair_attempts = len(result.get("repair_history", [])) + 1
    repair_max      = 3
    critique_lat    = _fmt_latency(metrics.get("critique_latency", "0.0000s"))

    intent      = "✓" if ev.get("intent_preserved") else "✗"
    rcf         = "✓" if ev.get("root_cause_fixed") else "✗"
    minimal     = "✓" if ev.get("minimal_fix") else "✗"
    regression  = "✓" if not ev.get("introduced_regression") else "✗"
    e_latency   = _fmt_latency(metrics.get("eval_latency", "—"))
    reasoning_e = _truncate(ev.get("reasoning", ""), col - 2)

    stdout      = execution.get("stdout", "").strip()
    exec_ok     = "✓ success" if execution.get("success") else "✗ failed"
    exec_color  = BRIGHT_GREEN if execution.get("success") else BRIGHT_RED

    # Print side-by-side sections
    print(f"  {BOLD}{BRIGHT_CYAN}── ANALYSIS {BRIGHT_CYAN}── {RESET}{'─' * (col - 10)}  "
          f"{BOLD}{BRIGHT_YELLOW}── FIX {BRIGHT_YELLOW}── {RESET}{'─' * (col - 5)}  "
          f"{BOLD}{BRIGHT_MAGENTA}── EVALUATION {BRIGHT_MAGENTA}── {RESET}")

    print(_col_line("root cause",  root_cause,  bt_color) + "  " +
          _col_line("change",      struct_str, DIM) + "  " +
          _col_line("intent",      intent, BRIGHT_GREEN if intent == "✓" else BRIGHT_RED))

    print(_col_line("error line",  error_line) + "  " +
          _col_line("latency",     f_latency, DIM) + "  " +
          _col_line("root fixed",  rcf, BRIGHT_GREEN if rcf == "✓" else BRIGHT_RED))

    print(_col_line("latency",     a_latency, DIM) + "  " +
          _col_line("execution",   exec_ok, exec_color) + "  " +
          _col_line("minimal",     minimal, BRIGHT_GREEN if minimal == "✓" else BRIGHT_RED))

    print(_col_line("reasoning",   reasoning_a, DIM) + "  " +
          _col_line("",            "") + "  " +
          _col_line("no regress",  regression, BRIGHT_GREEN if regression == "✓" else BRIGHT_RED))

    # ── Fixer explanation ────────────────────────────────────────────────────
    if explanation:
        print()
        print(f"  {DIM}fixer    : {explanation}{RESET}")

    # ── Heuristics row ───────────────────────────────────────────────────────
    print(f"  {DIM}heuristic: score {RESET}{_score_color(h_score or 0)}{h_score_str}{RESET}"
          f"  {DIM}│  structural change {RESET}{DIM}{struct_str}{RESET}"
          f"  {DIM}│  penalties {RESET}{BRIGHT_RED if penalties else DIM}{penalties_str}{RESET}")

    # ── Attempt counters ─────────────────────────────────────────────────────
    a_attempts = analysis.get("analyzer_latency", None)   # present = succeeded
    f_attempts = fix.get("fixer_latency", None)
    e_attempts = ev.get("reasoning", None)
    print(f"  {DIM}attempts : repair {RESET}{BRIGHT_CYAN}{repair_attempts}/{repair_max}{RESET}"
          f"  {DIM}│  analyzer {RESET}{DIM}{1 if a_attempts else '?'}/2{RESET}"
          f"  {DIM}│  fixer {RESET}{DIM}{1 if f_attempts else '?'}/2{RESET}"
          f"  {DIM}│  evaluator {RESET}{DIM}{1 if e_attempts else '?'}/2{RESET}")

    # ── Stdout on its own line ───────────────────────────────────────────────
    if stdout:
        print()
        print(f"  {DIM}stdout   : {stdout}{RESET}")

    print()

    # ── Score bar ───────────────────────────────────────────────────────────
    bar       = _score_bar(score)
    score_str = f"{sc_color}{BOLD}{score:.3f}{RESET}"
    total_lat = _fmt_latency(metrics.get("total_latency", "—"))
    print(f"  score  {bar}  {score_str}    {DIM}total {total_lat}{RESET}")

    # ── Evaluator reasoning ─────────────────────────────────────────────────
    if ev.get("reasoning"):
        verdict_text = ev["reasoning"].replace("\n", " ")
        wrap_width   = w - 14
        words        = verdict_text.split()
        lines_out    = []
        current      = ""
        for word in words:
            if len(current) + len(word) + 1 <= wrap_width:
                current = (current + " " + word).lstrip()
            else:
                if current:
                    lines_out.append(current)
                current = word
        if current:
            lines_out.append(current)
        indent = "             "  # aligns with text after "verdict : "
        print(f"  {DIM}verdict : {lines_out[0]}{RESET}")
        for extra_line in lines_out[1:]:
            print(f"  {DIM}{indent}{extra_line}{RESET}")

# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

def print_final_report(results: list[dict], cases: list[dict]) -> None:
    from collections import defaultdict

    def _fmt(s: str) -> float:
        try: return float(s.rstrip("s"))
        except: return 0.0

    w      = _width()
    total  = len(results)
    passed = sum(1 for r in results if r.get("evaluation", {}).get("passed"))
    failed = total - passed
    scores = [r.get("evaluation", {}).get("score", 0.0) for r in results]
    avg_sc = sum(scores) / total if total else 0.0

    pass_rate = passed / total if total else 0.0

    # Latency averages
    def _avg(key):
        vals = [_fmt(r.get("metrics", {}).get(key, "0s")) for r in results]
        return sum(vals) / len(vals) if vals else 0.0

    # Per bug type
    by_type = defaultdict(lambda: {"total": 0, "passed": 0, "scores": []})
    for r, c in zip(results, cases):
        bt = c.get("bug_type", "Unknown")
        ev = r.get("evaluation", {})
        by_type[bt]["total"]  += 1
        by_type[bt]["passed"] += int(ev.get("passed", False))
        by_type[bt]["scores"].append(ev.get("score", 0.0))

    print()
    print()
    _hr("═", BRIGHT_BLUE)
    print(f"{BRIGHT_BLUE}║{RESET}  {BOLD}{BRIGHT_WHITE}BENCHMARK COMPLETE{RESET}")
    _hr("═", BRIGHT_BLUE)
    print()

    # ── Top-level stats ──────────────────────────────────────────────────────
    pass_color = BRIGHT_GREEN if pass_rate >= 0.8 else BRIGHT_YELLOW if pass_rate >= 0.5 else BRIGHT_RED
    sc_color   = _score_color(avg_sc)

    bar_w = 36
    filled = round(pass_rate * bar_w)
    pass_bar = f"{BRIGHT_GREEN}{'█' * filled}{DIM}{'░' * (bar_w - filled)}{RESET}"

    print(f"  {BOLD}pass@1{RESET}   {pass_bar}  "
          f"{pass_color}{BOLD}{passed}/{total}{RESET}  "
          f"{DIM}({pass_rate:.1%}){RESET}")

    sc_bar_w = 36
    sc_filled = round(avg_sc * sc_bar_w)
    sc_bar = f"{sc_color}{'█' * sc_filled}{DIM}{'░' * (sc_bar_w - sc_filled)}{RESET}"
    print(f"  {BOLD}avg score{RESET} {sc_bar}  {sc_color}{BOLD}{avg_sc:.3f}{RESET}")

    print()

    # ── Latency breakdown ────────────────────────────────────────────────────
    _hr("─", DIM)
    print(f"  {BOLD}LATENCY{RESET}")
    print()

    stage_keys = [
        ("analysis",   "analysis_latency"),
        ("fix",        "fix_latency"),
        ("execution",  "execution_latency"),
        ("evaluation", "eval_latency"),
        ("total",      "total_latency"),
    ]
    stage_labels = [label for label, _ in stage_keys]

    # Build a 2D grid: per_run_vals[run_idx][stage_idx]
    per_run_vals = []
    for r in results:
        row = [_fmt(r.get("metrics", {}).get(key, "0s")) for _, key in stage_keys]
        per_run_vals.append(row)

    avgs = [
        sum(per_run_vals[r][s] for r in range(len(results))) / len(results)
        for s in range(len(stage_keys))
    ]

    # Column widths: stage label + 7 chars per value ("12.62s")
    val_w   = 8   # "  12.62s"
    label_w = 10  # "run 20   "

    # Header row — stage names
    hdr = f"  {'':{label_w}}"
    for label in stage_labels:
        hdr += f"  {label:>{val_w}}"
    print(f"{DIM}{hdr}{RESET}")
    print(f"  {DIM}{'-' * label_w}{''.join(['  ' + '-' * val_w for _ in stage_labels])}{RESET}")

    # One row per run
    for i, row_vals in enumerate(per_run_vals):
        task_id = cases[i].get("task_id", f"run {i+1}") if cases else f"run {i+1}"
        # Shorten "HumanEval/4" → "HE/4" to save space
        short_id = task_id.replace("HumanEval", "HE")
        line = f"  {short_id:{label_w}}"
        for s, v in enumerate(row_vals):
            color = BRIGHT_WHITE if s == len(stage_keys) - 1 else DIM
            line += f"  {color}{v:>{val_w}.2f}s{RESET}"
        print(line)

    # Separator + average row
    print(f"  {DIM}{'-' * label_w}{''.join(['  ' + '-' * val_w for _ in stage_labels])}{RESET}")
    avg_row = f"  {'avg':{label_w}}"
    for s, avg_val in enumerate(avgs):
        color = BRIGHT_WHITE if s == len(stage_keys) - 1 else BRIGHT_CYAN
        avg_row += f"  {color}{avg_val:>{val_w}.2f}s{RESET}"
    print(avg_row)

    print()

    # Bar chart of averages (fix is always the longest — good visual anchor)
    max_lat = max(avgs) or 1
    for (label, _), val in zip(stage_keys, avgs):
        bar_w  = 28
        filled = round((val / max_lat) * bar_w)
        color  = BRIGHT_CYAN if label != "total" else BRIGHT_WHITE
        bar    = f"{color}{'▓' * filled}{DIM}{'░' * (bar_w - filled)}{RESET}"
        print(f"  {label:<12} {bar}  {DIM}{val:.2f}s{RESET}")

    print()

    # ── Per bug-type table ───────────────────────────────────────────────────
    _hr("─", DIM)
    print(f"  {BOLD}PER BUG TYPE{RESET}")
    print()

    hdr = f"  {'BUG TYPE':<22} {'PASS':>5}{'TOTAL':>7}{'RATE':>8}  {'AVG SCORE':<12}  BAR"
    print(f"{DIM}{hdr}{RESET}")
    print(f"  {DIM}{'─'*22} {'─'*5}{'─'*7}{'─'*8}  {'─'*12}  {'─'*20}{RESET}")

    for bt, data in sorted(by_type.items()):
        rate   = data["passed"] / data["total"] if data["total"] else 0
        avg_bt = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
        rc     = BRIGHT_GREEN if rate >= 0.8 else BRIGHT_YELLOW if rate >= 0.5 else BRIGHT_RED
        sc     = _score_color(avg_bt)
        bw     = 20
        bf     = round(rate * bw)
        bar    = f"{rc}{'█' * bf}{DIM}{'░' * (bw - bf)}{RESET}"
        bt_c   = _bug_type_color(bt)
        print(f"  {bt_c}{bt:<22}{RESET} "
              f"{rc}{data['passed']:>5}{RESET}"
              f"{DIM}{data['total']:>7}{RESET}"
              f"{rc}{rate:>8.1%}{RESET}  "
              f"{sc}{avg_bt:<12.3f}{RESET}  {bar}")

    print()

    # ── Failures ─────────────────────────────────────────────────────────────
    fail_cases = [(r, c) for r, c in zip(results, cases)
                  if not r.get("evaluation", {}).get("passed")]

    if fail_cases:
        _hr("─", DIM)
        print(f"  {BOLD}{BRIGHT_RED}FAILURES  {DIM}({len(fail_cases)}){RESET}")
        print()
        for r, c in fail_cases:
            ev      = r.get("evaluation", {})
            task_id = c.get("task_id", r.get("run_id", "?"))
            bt      = c.get("bug_type", "?")
            bt_c    = _bug_type_color(bt)
            score   = ev.get("score", 0.0)
            reason  = ev.get("reasoning", "—").replace("\n", " ")
            mutation= c.get("mutation_desc", "—").replace("\n", " ")
            print(f"  {BRIGHT_WHITE}{BOLD}{task_id}{RESET}  {bt_c}{bt}{RESET}  "
                  f"{_score_color(score)}{score:.3f}{RESET}")
            # Word-wrap mutation and verdict to terminal width
            for field_label, field_text in [("mutation", mutation), ("verdict ", reason)]:
                wrap_width = w - 18
                words      = field_text.split()
                lines_out  = []
                current    = ""
                for word in words:
                    if len(current) + len(word) + 1 <= wrap_width:
                        current = (current + " " + word).lstrip()
                    else:
                        if current:
                            lines_out.append(current)
                        current = word
                if current:
                    lines_out.append(current)
                indent = "    " + " " * (len(field_label) + 3)
                print(f"    {DIM}{field_label} : {lines_out[0]}{RESET}")
                for extra_line in lines_out[1:]:
                    print(f"{DIM}{indent}{extra_line}{RESET}")
            print()
    else:
        print(f"  {BRIGHT_GREEN}{BOLD}✓ All cases passed!{RESET}")
        print()

    _hr("═", BRIGHT_BLUE)
    print()
