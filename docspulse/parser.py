"""
MODULE 1: parser.py
Extracts commands from README files or repositories.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

ALLOWED_TAGS = {"bash", "sh", "shell", "console", "python", "python3", "py", ""}


def is_git_url(url: str) -> bool:
    """Check if the provided string looks like a Git/GitHub URL."""
    url_lower = url.strip().lower()
    return (
        url_lower.startswith(("http://", "https://", "git@", "ssh://"))
        and ("github.com" in url_lower or url_lower.endswith(".git"))
    )


def clone_github_repo(url: str) -> tuple[Path, str]:
    """Clone a Git repository with depth 1 into a temporary directory."""
    temp_dir = tempfile.mkdtemp(prefix="docspulse_git_")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", url, temp_dir],
            check=True,
            capture_output=True,
            text=True,
        )
        return Path(temp_dir), temp_dir
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Failed to clone repository from '{url}': {exc}") from exc


def find_readme_in_dir(directory: Path) -> Path:
    """Find README.md (case-insensitive) in the specified directory."""
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    # Prioritize exact README.md case-insensitively
    for item in directory.iterdir():
        if item.is_file() and item.name.lower() == "readme.md":
            return item

    # Fallback to any file starting with readme
    for item in directory.iterdir():
        if item.is_file() and item.name.lower().startswith("readme"):
            return item

    raise FileNotFoundError(f"README.md not found in {directory}")


def resolve_target(target: str | Path) -> tuple[Path, Path, Optional[str]]:
    """
    Resolve target path or GitHub URL.
    Returns (readme_path, repo_dir, temp_dir_to_clean).
    """
    target_str = str(target).strip()
    if is_git_url(target_str):
        repo_dir, temp_dir = clone_github_repo(target_str)
        readme_path = find_readme_in_dir(repo_dir)
        return readme_path, repo_dir, temp_dir

    local_path = Path(target_str).resolve()
    if not local_path.exists():
        raise FileNotFoundError(f"Target path does not exist: {target_str}")

    if local_path.is_file():
        return local_path, local_path.parent, None

    if local_path.is_dir():
        readme_path = find_readme_in_dir(local_path)
        return readme_path, local_path, None

    raise ValueError(f"Invalid target: {target_str}")


def is_output_line(line: str) -> bool:
    """Identify common terminal output lines in code blocks."""
    s = line.strip().lower()
    if not s:
        return False
    output_prefixes = (
        "output:",
        "example output:",
        "result:",
        "successfully installed",
        "collecting ",
        "requirement already satisfied",
        "downloading ",
        "installing collected packages",
        "running ",
        "ran ",
        "ok",
        "failed ",
        "error:",
        "traceback (most recent call last):",
        "----------------------------------------------------------------------",
        "======================================================================",
    )
    return any(s.startswith(prefix) for prefix in output_prefixes)


def parse_readme_content(content: str) -> list[dict]:
    """
    Extract fenced code blocks tagged bash, sh, shell, console, python, or untagged.
    Split into individual commands, strip '$ ' prompts, join lines ending in '\\',
    and ignore comment lines and output lines.
    Returns a list of dicts: [{'line_no': int, 'command': str}].
    """
    lines = content.splitlines()
    commands: list[dict] = []

    inside_fence = False
    inside_ignored_fence = False
    fence_char = ""
    fence_len = 0
    block_lines: list[tuple[int, str]] = []

    def process_block(block: list[tuple[int, str]]) -> list[dict]:
        extracted: list[dict] = []
        # Detect if this block uses command prompts ($)
        has_prompt = False
        for _, raw in block:
            st = raw.strip()
            if not st or st.startswith("#"):
                continue
            if st.startswith("$ ") or st == "$" or re.match(r"^\$\s+", st):
                has_prompt = True
                break

        current_cmd_parts: list[str] = []
        cmd_start_line: Optional[int] = None
        in_continuation = False

        for line_num, raw in block:
            stripped = raw.strip()
            if not stripped:
                continue

            if in_continuation:
                if stripped.startswith("#"):
                    continue
                if stripped.endswith("\\"):
                    part = stripped[:-1].rstrip()
                    if part:
                        current_cmd_parts.append(part)
                else:
                    current_cmd_parts.append(stripped)
                    full_cmd = " ".join(current_cmd_parts)
                    extracted.append({"line_no": cmd_start_line, "command": full_cmd})
                    current_cmd_parts = []
                    cmd_start_line = None
                    in_continuation = False
                continue

            # Not in continuation
            if stripped.startswith("#"):
                continue

            if has_prompt:
                if not (stripped.startswith("$ ") or stripped == "$" or re.match(r"^\$\s+", stripped)):
                    # Output line in a prompt-driven block
                    continue
                cmd_line = re.sub(r"^\$\s*", "", stripped)
            else:
                if is_output_line(stripped):
                    continue
                cmd_line = stripped

            if not cmd_line:
                continue

            if cmd_line.endswith("\\"):
                in_continuation = True
                cmd_start_line = line_num
                part = cmd_line[:-1].rstrip()
                if part:
                    current_cmd_parts.append(part)
            else:
                extracted.append({"line_no": line_num, "command": cmd_line})

        if in_continuation and current_cmd_parts:
            full_cmd = " ".join(current_cmd_parts)
            extracted.append({"line_no": cmd_start_line, "command": full_cmd})

        return extracted

    for line_num, raw_line in enumerate(lines, start=1):
        fence_match = re.match(r"^\s*([`~]{3,})(.*)$", raw_line)

        if not inside_fence and not inside_ignored_fence:
            if fence_match:
                marker = fence_match.group(1)
                fence_char = marker[0]
                fence_len = len(marker)
                info = fence_match.group(2).strip()
                tag = info.split()[0].lower() if info else ""
                if tag in ALLOWED_TAGS:
                    inside_fence = True
                    block_lines = []
                else:
                    inside_ignored_fence = True
        elif inside_fence:
            closing_match = re.match(rf"^\s*{re.escape(fence_char)}{{{fence_len},}}\s*$", raw_line)
            if closing_match:
                inside_fence = False
                commands.extend(process_block(block_lines))
                block_lines = []
            else:
                block_lines.append((line_num, raw_line))
        elif inside_ignored_fence:
            closing_match = re.match(rf"^\s*{re.escape(fence_char)}{{{fence_len},}}\s*$", raw_line)
            if closing_match:
                inside_ignored_fence = False

    if inside_fence and block_lines:
        commands.extend(process_block(block_lines))

    return commands


# Convenience aliases
parse_readme = parse_readme_content


def parse_readme_file(readme_path: str | Path) -> list[dict]:
    """Parse commands from a README file."""
    path = Path(readme_path)
    content = path.read_text(encoding="utf-8", errors="replace")
    return parse_readme_content(content)


def parse(target: str | Path) -> tuple[list[dict], Path, Optional[str]]:
    """
    Parse README commands from a local path or Git URL.
    Returns (commands, repo_dir, temp_dir_to_clean).
    """
    readme_path, repo_dir, temp_dir = resolve_target(target)
    commands = parse_readme_file(readme_path)
    return commands, repo_dir, temp_dir
