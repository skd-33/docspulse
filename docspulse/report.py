"""
MODULE 5: report.py
Generates Markdown and terminal reports for verification runs.
"""

from pathlib import Path
from typing import List


def generate_counts(results: List[dict]) -> dict:
    """Calculate summary statistics from execution results."""
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "PASS")
    failed = sum(1 for r in results if r.get("status") in ("FAIL", "TIMEOUT"))
    skipped = sum(1 for r in results if r.get("status") == "SKIPPED")
    verified_fixes = sum(1 for r in results if r.get("fix_status") == "VERIFIED FIX")
    unverified_fixes = sum(1 for r in results if r.get("fix_status") == "FIX NOT VERIFIED")

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "verified_fixes": verified_fixes,
        "unverified_fixes": unverified_fixes,
    }


def has_unfixed_failures(results: List[dict]) -> bool:
    """Check if any command failed without an AI-proposed verified fix."""
    for r in results:
        status = r.get("status")
        fix_status = r.get("fix_status")
        if status in ("FAIL", "TIMEOUT") and fix_status != "VERIFIED FIX":
            return True
    return False


def escape_markdown(text: str) -> str:
    """Escape pipe characters and clean newlines for Markdown table cells."""
    if not text:
        return "-"
    cleaned = text.replace("\r", "").replace("\n", " ").replace("|", "\\|").strip()
    return cleaned if cleaned else "-"


def generate_markdown_report(results: List[dict]) -> str:
    """Generate Markdown report contents."""
    counts = generate_counts(results)

    lines = [
        "# DocsPulse Verification Report",
        "",
        "## Summary",
        f"- **Total Commands:** {counts['total']}",
        f"- **Passed:** {counts['passed']}",
        f"- **Failed:** {counts['failed']}",
        f"- **Skipped:** {counts['skipped']}",
        f"- **Verified Fixes:** {counts['verified_fixes']}",
        f"- **Unverified Fixes:** {counts['unverified_fixes']}",
        "",
        "## Details",
        "",
        "| Line | Command | Status | First Line of Error | Verified Fix |",
        "| :---: | :--- | :---: | :--- | :--- |",
    ]

    for r in results:
        line_no = r.get("line_no", "-")
        cmd_raw = r.get("command", "")
        cmd = escape_markdown(cmd_raw)
        status = r.get("status", "")
        error = escape_markdown(r.get("error_first_line", ""))

        fix_val = r.get("fix")
        fix_status = r.get("fix_status")
        if fix_status == "VERIFIED FIX" and fix_val:
            fix_str = f"`{escape_markdown(fix_val)}` *(VERIFIED)*"
        elif fix_status == "FIX NOT VERIFIED" and fix_val:
            fix_str = f"`{escape_markdown(fix_val)}` *(NOT VERIFIED)*"
        else:
            fix_str = "-"

        lines.append(f"| {line_no} | `{cmd}` | **{status}** | {error} | {fix_str} |")

    return "\n".join(lines) + "\n"


def write_report_file(results: List[dict], output_path: Path | str = "report.md") -> Path:
    """Write report.md to disk."""
    path = Path(output_path)
    md_content = generate_markdown_report(results)
    path.write_text(md_content, encoding="utf-8")
    return path


def print_terminal_summary(results: List[dict]) -> None:
    """Print a clean, readable summary to the terminal."""
    counts = generate_counts(results)
    print("\n" + "=" * 60)
    print(" DocsPulse Verification Summary")
    print("=" * 60)
    print(
        f"Total: {counts['total']} | "
        f"Passed: {counts['passed']} | "
        f"Failed: {counts['failed']} | "
        f"Skipped: {counts['skipped']} | "
        f"Verified Fixes: {counts['verified_fixes']}"
    )
    print("-" * 60)

    for r in results:
        status = r.get("status", "")
        line_no = r.get("line_no", "-")
        cmd = r.get("command", "")
        print(f"[{status:7s}] Line {line_no}: {cmd}")

        if status in ("FAIL", "TIMEOUT"):
            err = r.get("error_first_line", "")
            if err:
                print(f"          Error: {err}")
            fix = r.get("fix")
            fix_status = r.get("fix_status")
            if fix:
                print(f"          Fix ({fix_status}): {fix}")
        elif status == "SKIPPED":
            reason = r.get("error_first_line", "")
            if reason:
                print(f"          Reason: {reason}")

    print("=" * 60)
    if has_unfixed_failures(results):
        print("RESULT: FAILED (Some commands failed without a verified fix)")
    else:
        print("RESULT: PASSED (All commands executed successfully or have verified fixes)")
    print("=" * 60 + "\n")
