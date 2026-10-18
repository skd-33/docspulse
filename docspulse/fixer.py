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


def build_fix_prompt(failed_command: str, stderr_tail: str) -> str:
    """Create a short, strict prompt for LLM fix generation."""
    return (
        f"Fix this failed command.\n"
        f"Command: {failed_command}\n"
        f"Error:\n{stderr_tail}\n\n"
        f"Reply with ONLY one corrected command on one line. No explanation, no markdown."
    )


def ask_llm(
    prompt: str,
    provider: str = "ollama",
    model: str = "qwen2.5:1.5b",
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
    model: str = "qwen2.5:1.5b",
) -> dict:
    """
    Attempt to fix a failed command using LLM and verify by re-running in the venv.
    Labels 'VERIFIED FIX' or 'FIX NOT VERIFIED' (max 2 attempts).
    """
    if provider == "none" or cmd_result.get("status") != "FAIL":
        return cmd_result

    failed_cmd = cmd_result.get("command", "")
    stderr_tail = cmd_result.get("stderr_tail", "")

    for attempt in range(1, 3):
        prompt = build_fix_prompt(failed_cmd, stderr_tail)
        raw_reply = ask_llm(prompt, provider=provider, model=model)
        candidate = clean_llm_response(raw_reply)

        if not candidate:
            # LLM unavailable or empty reply
            cmd_result["fix"] = None
            cmd_result["fix_status"] = None
            return cmd_result

        cmd_result["fix"] = candidate

        # Safety validation
        safety_status, reason = check_safety(candidate)
        if safety_status != "run":
            print(f"[DocsPulse] Proposed fix '{candidate}' rejected by safety: {reason}")
            cmd_result["fix_status"] = "FIX NOT VERIFIED"
            continue

        # Re-run candidate command in the same venv
        print(f"[DocsPulse] Testing fix (attempt {attempt}/2): {candidate}")
        rerun_res = runner.run_raw(candidate)
        if rerun_res.get("exit_code") == 0:
            cmd_result["fix_status"] = "VERIFIED FIX"
            cmd_result["fix"] = candidate
            return cmd_result
        else:
            cmd_result["fix_status"] = "FIX NOT VERIFIED"
            stderr_tail = rerun_res.get("stderr_tail") or stderr_tail

    return cmd_result
