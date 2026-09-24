"""
Standalone scanner CLI (`dbp-scan`) for reading db-portability findings on a
real project. Runs the checks registered in db_portability.checks for the
requested --from/--to pair (postgres -> oracle by default - the only pair
implemented so far), but prints them grouped by file and colorized instead
of a flat wall of `path:line:col: code message` lines.
"""
import argparse
import ast
import os
import pathlib
import sys
import webbrowser

from db_portability import __version__
from db_portability.checks import available_pairs, get_checks
from db_portability.report_html import render_html

DEFAULT_EXCLUDES = {
    ".venv", "venv", ".git", "__pycache__", "node_modules",
    "migrations", ".tox", "build", "dist",
}

COLORS = {
    "error": "\033[31m",
    "warn": "\033[33m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "reset": "\033[0m",
}


def _use_color(no_color_flag):
    if no_color_flag or os.environ.get("NO_COLOR") is not None:
        return False
    return sys.stdout.isatty()


def iter_python_files(paths, excludes):
    for path in paths:
        if os.path.isfile(path):
            if path.endswith(".py"):
                yield path
            continue
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in excludes and not d.startswith(".")]
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(root, name)


def scan_file(path, checks_module):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        source = fh.read()
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return None, exc
    return checks_module.run(tree), None


def main(argv=None):
    supported = ", ".join(f"{s} -> {t}" for s, t in available_pairs())
    parser = argparse.ArgumentParser(
        prog="dbp-scan",
        description="Scan a Django project for database code that will break when ported to another backend.",
        epilog=f"Supported --from/--to pairs: {supported}",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "paths", nargs="*", default=["."],
        help="Files or directories to scan (default: current directory)",
    )
    parser.add_argument(
        "--from", dest="source", default="postgres", metavar="DB",
        help="Source database currently in use (default: postgres)",
    )
    parser.add_argument(
        "--to", dest="target", default="oracle", metavar="DB",
        help="Target database being ported to (default: oracle)",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument(
        "--exclude", action="append", default=[],
        help="Additional directory name to skip (repeatable)",
    )
    parser.add_argument("--quiet", action="store_true", help="Only print the summary line")
    parser.add_argument(
        "--no-progress", action="store_true", help="Disable the live scanning progress line",
    )
    parser.add_argument(
        "--format", choices=["text", "html"], default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--output", metavar="FILE",
        help="Where to write the --format html report (default: dbp-scan-report.html). Ignored for text output.",
    )
    parser.add_argument(
        "--open", action="store_true",
        help="Open the --format html report in the default browser once written. Ignored for text output.",
    )
    args = parser.parse_args(argv)

    color = _use_color(args.no_color)

    def c(kind, text):
        return f"{COLORS[kind]}{text}{COLORS['reset']}" if color else text

    try:
        checks_module = get_checks(args.source, args.target)
    except ValueError as exc:
        print(c("error", str(exc)), file=sys.stderr)
        return 2

    warn_codes = getattr(checks_module, "WARN_CODES", set())
    excludes = DEFAULT_EXCLUDES | set(args.exclude)
    html_format = args.format == "html"

    files = sorted(iter_python_files(args.paths, excludes))
    total_files = len(files)
    total = 0
    counts = {}
    files_with_issues = 0
    records = []
    syntax_errors = []

    live_progress = sys.stderr.isatty() and not args.no_progress
    if not args.no_progress:
        print(f"Scanning {total_files} file(s) for {args.source} -> {args.target} portability issues...",
              file=sys.stderr)

    for i, path in enumerate(files, 1):
        if live_progress:
            print(f"\r\033[K[{i}/{total_files}] {path}", end="", file=sys.stderr, flush=True)

        errors, syntax_err = scan_file(path, checks_module)
        if syntax_err is not None:
            if live_progress:
                print("\r\033[K", end="", file=sys.stderr)
            print(c("warn", f"! {path}: could not parse ({syntax_err.msg}, line {syntax_err.lineno})"))
            syntax_errors.append((path, syntax_err))
            continue
        if not errors:
            continue

        files_with_issues += 1
        if live_progress:
            print("\r\033[K", end="", file=sys.stderr)
        if not args.quiet and not html_format:
            print(c("bold", path))
        for lineno, col, message in errors:
            code = message.split(" ", 1)[0]
            counts[code] = counts.get(code, 0) + 1
            total += 1
            severity = "warn" if code in warn_codes else "error"
            if html_format:
                records.append({
                    "file": path, "lineno": lineno, "col": col,
                    "code": code, "message": message, "severity": severity,
                })
            elif not args.quiet:
                loc = c("dim", f"{lineno}:{col + 1}")
                print(f"  {loc}  {c(severity, message)}")
        if not args.quiet and not html_format:
            print()

    if live_progress:
        print("\r\033[K", end="", file=sys.stderr)

    if html_format:
        output_path = args.output or "dbp-scan-report.html"
        report = render_html(records, {
            "source": args.source,
            "target": args.target,
            "total": total,
            "total_files": total_files,
            "files_with_issues": files_with_issues,
            "counts": counts,
            "syntax_errors": syntax_errors,
        })
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"HTML report written to {output_path}")
        if args.open:
            uri = pathlib.Path(output_path).resolve().as_uri()
            try:
                if not webbrowser.open(uri):
                    raise webbrowser.Error("no browser handler available")
            except webbrowser.Error as exc:
                print(c("warn", f"Could not open {uri} in a browser: {exc}"), file=sys.stderr)

    if total == 0:
        print(c("green", f"No {args.source} -> {args.target} portability issues found."))
        return 0

    summary = ", ".join(f"{code} x{n}" for code, n in sorted(counts.items()))
    print(c("bold", f"{total} issue(s) in {files_with_issues} file(s): ") + summary)
    return 1


if __name__ == "__main__":
    sys.exit(main())
