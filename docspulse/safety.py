"""
MODULE 2: safety.py
Validates commands against an allowlist and rejects dangerous tokens/operators.
"""

import os
import re
import shlex
from pathlib import Path
from typing import Tuple

ALLOWED_FIRST_TOKENS = {"pip", "pip3", "python", "python3", "pytest", "py"}

DANGEROUS_WORDS = {"rm", "sudo", "del", "format", "shutdown"}

DANGEROUS_WORDS_REGEX = re.compile(
    r"\b(rm|sudo|del|format|shutdown)\b",
    re.IGNORECASE,
)

SHELL_REDIRECTION_REGEX = re.compile(
    r"(?<![=!<>])>(?!=)|(?<![=!<>])<(?!=)"
)

URL_PIPED_TO_SHELL_REGEX = re.compile(
    r"\b(curl|wget)\b.*\|\s*(sh|bash|zsh|dash)",
    re.IGNORECASE,
)


def check_safety(command: str) -> Tuple[str, str]:
    """
    Check if a command is safe to execute.

    Returns:
        ("run", "") if safe.
        ("skipped", "<reason>") if dangerous or not allowed.
    """
    cmd = command.strip()
    if not cmd:
        return ("skipped", "Empty command")

    # 1. Check dangerous shell operators / control structures
    if URL_PIPED_TO_SHELL_REGEX.search(cmd):
        return ("skipped", "URL piped into shell")

    if "curl|sh" in cmd.replace(" ", "") or "wget|sh" in cmd.replace(" ", ""):
        return ("skipped", "URL piped into shell")

    if "&&" in cmd:
        return ("skipped", "Contains forbidden operator: '&&'")

    if "||" in cmd:
        return ("skipped", "Contains forbidden operator: '||'")

    if ";" in cmd:
        return ("skipped", "Contains forbidden operator: ';'")

    if "|" in cmd:
        return ("skipped", "Contains forbidden operator: '|'")

    if "`" in cmd:
        return ("skipped", "Contains forbidden operator: backtick")

    if "$(" in cmd:
        return ("skipped", "Contains forbidden operator: '$('")

    if SHELL_REDIRECTION_REGEX.search(cmd):
        return ("skipped", "Contains forbidden redirection operator: '>' or '<'")

    # 2. Tokenize using shlex with OS-specific posix setting
    try:
        tokens = shlex.split(cmd, posix=(os.name != "nt"))
    except ValueError as exc:
        return ("skipped", f"Invalid command syntax: {exc}")

    if not tokens:
        return ("skipped", "Empty command")

    # 3. Check first token against allowlist
    first_token = tokens[0].lower()
    first_token_stem = Path(first_token).stem.lower()
    if first_token not in ALLOWED_FIRST_TOKENS and first_token_stem not in ALLOWED_FIRST_TOKENS:
        return ("skipped", f"First token '{tokens[0]}' is not allowed")

    # 4. Check whole-word dangerous commands via regex boundary
    match_danger = DANGEROUS_WORDS_REGEX.search(cmd)
    if match_danger:
        return ("skipped", f"Contains dangerous word: '{match_danger.group(1)}'")

    # 5. Check all tokens for dangerous whole words
    for token in tokens:
        token_lower = token.lower()
        token_stem = Path(token_lower).stem.lower()
        if token_lower in DANGEROUS_WORDS or token_stem in DANGEROUS_WORDS:
            return ("skipped", f"Contains dangerous token: '{token}'")

    return ("run", "")


# Convenience alias
is_safe = check_safety
validate_command = check_safety
