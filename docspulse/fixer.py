"""
MODULE 4: fixer.py
Generates and verifies fixes for failed commands using LLM providers (Ollama, Gemini, none).
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Optional

from docspulse.safety import check_safety

if TYPE_CHECKING:
    from docspulse.runner import VenvRunner


def clean_llm_response(text: str) -> str:
    """Strip code fences, backticks, prompts, and return single line command."""
    if not text:
        return ""
    # Strip fences, language tags, and backticks
    cleaned = re.sub(r"```[a-zA-Z]*", "", text)
    cleaned = cleaned.replace("```", "").replace("`", "")
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""
    cmd = lines[0]
    # Strip leading '$ ' prompt
    cmd = re.sub(r"^\$\s*", "", cmd)
    return cmd.strip()


def extract_versions_line(text: str) -> Optional[str]:
    """Extract line containing (from versions: ...) if present."""
    for line in text.splitlines():
        if "(from versions:" in line.lower():
            return line.strip()
    return None


def get_heuristic_pip_fixes(command: str, stderr: str, stdout: str = "") -> list[str]:
    """
    Deterministic fixes for pip install failures containing:
    'No matching distribution found' or 'Could not find a version'
    (a) if the error has '(from versions: ...)', propose pip install <pkg>==<highest listed version>
    (b) otherwise propose the same install without the version pin.
    """
    combined = f"{stderr}\n{stdout}"
    combined_lower = combined.lower()

    if not ("no matching distribution found" in combined_lower or "could not find a version" in combined_lower):
        return []

    # Find pinned package in command: <pkg>==<ver>
    pkg_pin_match = re.search(r"\b([a-zA-Z0-9_\-\.]+)\s*==\s*[a-zA-Z0-9_\-\.]+", command)
    if not pkg_pin_match:
        # Fallback: check requirement in error message
        req_match = re.search(r"requirement\s+([a-zA-Z0-9_\-\.]+)==", combined, re.IGNORECASE)
        if req_match:
            pkg_name = req_match.group(1)
            pkg_pin_match = re.search(rf"\b{re.escape(pkg_name)}\s*==\s*[a-zA-Z0-9_\-\.]+", command)
        else:
            return []

    if not pkg_pin_match:
        return []

    pkg_name = pkg_pin_match.group(1)
    full_pin = pkg_pin_match.group(0)

    candidates: list[str] = []

    # Check (a): (from versions: ...)
    m_versions = re.search(r"\(from versions:\s*([^\)]+)\)", combined, re.IGNORECASE)
    if m_versions:
        content = m_versions.group(1).strip()
        if content and content.lower() != "none":
            versions = [v.strip() for v in content.split(",") if v.strip() and v.strip().lower() != "none"]
            if versions:
                highest_version = versions[-1]
                cand_a = command.replace(full_pin, f"{pkg_name}=={highest_version}")
                if cand_a != command:
                    candidates.append(cand_a)

    # Candidate (b): same install without version pin
    cand_b = command.replace(full_pin, pkg_name)
    if cand_b != command and cand_b not in candidates:
        candidates.append(cand_b)

    return candidates


def build_fix_prompt(
    failed_command: str,
    stderr_tail: str,
    attempt: int = 1,
    previous_fix: Optional[str] = None,
    previous_error: Optional[str] = None,
    versions_line: Optional[str] = None,
) -> str:
    """Create a short, strict prompt for LLM fix generation."""
    versions_section = f"\nAvailable versions info:\n{versions_line}\n" if versions_line else ""

    if attempt == 1:
        return (
            f"Fix this failed command.\n"
            f"Command: {failed_command}\n"
            f"Error:\n{stderr_tail}{versions_section}\n\n"
            f"Reply with ONLY one corrected command on one line. No explanation, no markdown."
        )
    else:
        prev_err_text = f"\nError from previous fix:\n{previous_error}" if previous_error else ""
        return (
            f"Fix this failed command.\n"
            f"Original Command: {failed_command}\n"
            f"Original Error:\n{stderr_tail}{versions_section}\n"
            f"Previous attempt that FAILED: {previous_fix}{prev_err_text}\n\n"
            f"Instruct: Do NOT repeat the previous failed command '{previous_fix}' or the original command.\n"
            f"Reply with ONLY one DIFFERENT corrected command on one line. No explanation, no markdown."
        )


def ask_llm(
    prompt: str,
    provider: str = "ollama",
    model: str = "qwen2.5-coder:3b",
) -> str:
    """
    Dispatch LLM query by provider:
    - ollama: POST http://localhost:11434/api/chat, stream=false, temperature 0
    - gemini: REST API using GEMINI_API_KEY env var
    - none: skip fixing entirely
    """
    prov = provider.lower() if provider else "none"

    if prov == "none":
        return ""

    if prov == "ollama":
        url = "http://localhost:11434/api/chat"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                return resp_json.get("message", {}).get("content", "").strip()
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            print("[DocsPulse] Ollama is not running at http://localhost:11434. Continuing without fixes.")
            return ""

    if prov == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            print("[DocsPulse] GEMINI_API_KEY is not set. Continuing without fixes.")
            return ""

        gemini_model = model if "gemini" in model.lower() else "gemini-1.5-flash"
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{gemini_model}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                candidates = resp_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
                return ""
        except Exception as exc:
            print(f"[DocsPulse] Gemini request failed: {exc}. Continuing without fixes.")
            return ""

    return ""


def attempt_fix(
    cmd_result: dict,
    runner: "VenvRunner",
    provider: str = "ollama",
    model: str = "qwen2.5-coder:3b",
) -> dict:
    """
    Attempt to fix a failed command using:
    1. Deterministic heuristic fixes (run BEFORE LLM)
    2. LLM fixes (if provider is not none)
    Max 3 candidates total per failed command, deduplicated.
    Labels each fix with fix_source ('heuristic' or 'llm').
    """
    if cmd_result.get("status") != "FAIL":
        return cmd_result

    failed_cmd = cmd_result.get("command", "")
    stderr = cmd_result.get("stderr", "")
    stdout = cmd_result.get("stdout", "")
    stderr_tail = cmd_result.get("stderr_tail", "")

    tried_candidates = {failed_cmd}
    candidates_count = 0

    # 1. Deterministic heuristic fixes (run BEFORE LLM)
    heuristic_candidates = get_heuristic_pip_fixes(failed_cmd, stderr, stdout)
    for candidate in heuristic_candidates:
        if candidates_count >= 3:
            break
        if candidate in tried_candidates:
            continue

        tried_candidates.add(candidate)
        candidates_count += 1
        cmd_result["fix"] = candidate
        cmd_result["fix_source"] = "heuristic"

        safety_status, reason = check_safety(candidate)
        if safety_status != "run":
            print(f"[DocsPulse] Proposed heuristic fix '{candidate}' rejected by safety: {reason}")
            cmd_result["fix_status"] = "FIX NOT VERIFIED"
            continue

        print(f"[DocsPulse] Testing heuristic fix ({candidates_count}/3): {candidate}")
        rerun_res = runner.run_raw(candidate)
        if rerun_res.get("exit_code") == 0:
            cmd_result["fix_status"] = "VERIFIED FIX"
            cmd_result["fix"] = candidate
            cmd_result["fix_source"] = "heuristic"
            return cmd_result
        else:
            cmd_result["fix_status"] = "FIX NOT VERIFIED"
            stderr_tail = rerun_res.get("stderr_tail") or stderr_tail

    # 2. LLM fixes (if provider is not none and budget remaining)
    if provider == "none" or candidates_count >= 3:
        return cmd_result

    prev_fix = cmd_result.get("fix")
    prev_error = stderr_tail
    versions_line = extract_versions_line(f"{stderr}\n{stdout}")

    while candidates_count < 3:
        prompt = build_fix_prompt(
            failed_cmd,
            stderr_tail,
            attempt=candidates_count + 1,
            previous_fix=prev_fix,
            previous_error=prev_error,
            versions_line=versions_line,
        )
        raw_reply = ask_llm(prompt, provider=provider, model=model)
        candidate = clean_llm_response(raw_reply)

        if not candidate:
            break

        cmd_result["fix"] = candidate
        cmd_result["fix_source"] = "llm"

        if candidate in tried_candidates:
            print(f"[DocsPulse] LLM proposed already-tried command '{candidate}'. Skipping re-run.")
            cmd_result["fix_status"] = "FIX NOT VERIFIED"
            break

        tried_candidates.add(candidate)
        candidates_count += 1
        prev_fix = candidate

        safety_status, reason = check_safety(candidate)
        if safety_status != "run":
            print(f"[DocsPulse] Proposed fix '{candidate}' rejected by safety: {reason}")
            cmd_result["fix_status"] = "FIX NOT VERIFIED"
            prev_error = reason
            continue

        print(f"[DocsPulse] Testing LLM fix ({candidates_count}/3): {candidate}")
        rerun_res = runner.run_raw(candidate)
        if rerun_res.get("exit_code") == 0:
            cmd_result["fix_status"] = "VERIFIED FIX"
            cmd_result["fix"] = candidate
            cmd_result["fix_source"] = "llm"
            return cmd_result
        else:
            cmd_result["fix_status"] = "FIX NOT VERIFIED"
            prev_error = rerun_res.get("stderr_tail") or rerun_res.get("stdout_tail") or "Command failed"

    return cmd_result
