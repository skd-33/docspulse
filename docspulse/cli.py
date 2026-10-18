"""
MODULE 5: cli.py
Command-line interface for DocsPulse.
"""

import argparse
import shutil
import sys
from pathlib import Path

from docspulse.fixer import attempt_fix
from docspulse.parser import parse
from docspulse.report import has_unfixed_failures, print_terminal_summary, write_report_file
from docspulse.runner import VenvRunner


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        prog="docspulse",
        description="Verify README install instructions by actually running them in an isolated environment.",
    )
    parser.add_argument(
        "target",
        help="Local repository/directory path, README file path, or GitHub URL.",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "gemini", "none"],
        default="ollama",
        help="LLM provider for generating proposed fixes (default: ollama).",
    )
    parser.add_argument(
        "--model",
        default="qwen2.5:1.5b",
        help="LLM model name to query (default: qwen2.5:1.5b).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout in seconds for each command execution (default: 120).",
    )
    return parser.parse_args(args)


def run_pipeline(
    target: str,
    provider: str = "ollama",
    model: str = "qwen2.5:1.5b",
    timeout: int = 120,
) -> int:
    """Run the complete DocsPulse verification pipeline."""
    temp_dir = None
    try:
        commands, repo_dir, temp_dir = parse(target)
    except Exception as exc:
        print(f"[DocsPulse] Error resolving target '{target}': {exc}", file=sys.stderr)
        return 1

    if not commands:
        print(f"[DocsPulse] No testable install instructions found in {target}.")
        empty_results = []
        write_report_file(empty_results)
        print_terminal_summary(empty_results)
        return 0

    print(f"[DocsPulse] Found {len(commands)} command(s) to verify in {repo_dir}.")

    results = []
    with VenvRunner(repo_dir=repo_dir, timeout=timeout) as runner:
        for item in commands:
            cmd_res = runner.run_command(item)
            if cmd_res.get("status") == "FAIL" and provider != "none":
                attempt_fix(cmd_res, runner, provider=provider, model=model)
            results.append(cmd_res)

    # Write report.md to working directory
    report_path = write_report_file(results, "report.md")
    print(f"\n[DocsPulse] Report written to: {report_path.resolve()}")

    # Print human-readable summary
    print_terminal_summary(results)

    # Cleanup temporary git clone if created
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Exit code 1 if any step failed without verified fix
    return 1 if has_unfixed_failures(results) else 0


def main(args=None):
    parsed = parse_args(args)
    exit_code = run_pipeline(
        target=parsed.target,
        provider=parsed.provider,
        model=parsed.model,
        timeout=parsed.timeout,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
