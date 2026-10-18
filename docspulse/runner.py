"""
MODULE 3: runner.py
Executes commands in an isolated temporary virtual environment.
"""

import os
import shlex
import shutil
import subprocess
import tempfile
import venv
from pathlib import Path
from typing import Optional

from docspulse.safety import check_safety


def split_command(command: str) -> list[str]:
    """Split command string using shlex, handling Windows quote preservation."""
    tokens = shlex.split(command, posix=(os.name != "nt"))
    clean = []
    for t in tokens:
        if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'"):
            clean.append(t[1:-1])
        else:
            clean.append(t)
    return clean


def map_command(command: str, python_bin: Path) -> list[str]:
    """
    Map python/pip to the venv executables.
    Always runs pip as `<venv python> -m pip ...`.
    """
    tokens = split_command(command)
    if not tokens:
        return []

    first = tokens[0].lower()
    first_stem = Path(first).stem.lower()

    if first in ("pip", "pip3") or first_stem in ("pip", "pip3"):
        # Always run pip as `<venv python> -m pip ...`
        return [str(python_bin), "-m", "pip"] + tokens[1:]
    elif first in ("python", "python3", "py") or first_stem in ("python", "python3", "py"):
        return [str(python_bin)] + tokens[1:]
    elif first == "pytest" or first_stem == "pytest":
        return [str(python_bin), "-m", "pytest"] + tokens[1:]
    else:
        return [str(python_bin), "-m", tokens[0]] + tokens[1:]


def extract_error_line(stderr: str, stdout: str = "") -> str:
    """
    Extract the most informative error line.
    Prefer the last line starting with 'ERROR:' that is not 'Ignored the following yanked versions';
    otherwise the last non-empty stderr line (or stdout line if stderr is empty).
    """
    lines = [l.strip() for l in (stderr or "").splitlines() if l.strip()]
    if not lines and stdout:
        lines = [l.strip() for l in stdout.splitlines() if l.strip()]
    if not lines:
        return ""

    error_lines = [
        l for l in lines
        if l.startswith("ERROR:") and "Ignored the following yanked versions" not in l
    ]
    if error_lines:
        return error_lines[-1]

    return lines[-1]


class VenvRunner:
    """Manages execution of commands in an isolated temporary virtual environment."""

    def __init__(self, repo_dir: Path | str, timeout: int = 120):
        self.repo_dir = Path(repo_dir).resolve()
        self.timeout = timeout
        self.temp_venv_dir: Optional[Path] = None
        self.python_bin: Optional[Path] = None
        self.env: dict[str, str] = {}

    def setup(self) -> None:
        """Create a fresh virtual environment in a temporary directory."""
        temp_dir = tempfile.mkdtemp(prefix="docspulse_venv_")
        self.temp_venv_dir = Path(temp_dir)
        venv.EnvBuilder(with_pip=True).create(self.temp_venv_dir)

        if os.name == "nt":
            scripts_dir = self.temp_venv_dir / "Scripts"
            self.python_bin = scripts_dir / "python.exe"
        else:
            scripts_dir = self.temp_venv_dir / "bin"
            self.python_bin = scripts_dir / "python"

        self.env = os.environ.copy()
        self.env["VIRTUAL_ENV"] = str(self.temp_venv_dir)
        self.env["PATH"] = f"{scripts_dir}{os.pathsep}{self.env.get('PATH', '')}"
        self.env.pop("PYTHONHOME", None)

    def cleanup(self) -> None:
        """Remove the temporary virtual environment."""
        if self.temp_venv_dir and self.temp_venv_dir.exists():
            shutil.rmtree(self.temp_venv_dir, ignore_errors=True)

    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def run_raw(self, command: str, timeout: Optional[int] = None) -> dict:
        """Run a raw command string within the venv."""
        effective_timeout = timeout if timeout is not None else self.timeout
        print(f"[DocsPulse] Running: {command}")

        safety_status, reason = check_safety(command)
        if safety_status == "skipped":
            return {
                "status": "SKIPPED",
                "exit_code": None,
                "stdout": "",
                "stderr": reason,
                "stdout_tail": "",
                "stderr_tail": reason,
                "error_first_line": reason,
            }

        if not self.python_bin or not self.python_bin.exists():
            raise RuntimeError("Venv python executable is not initialized.")

        cmd_args = map_command(command, self.python_bin)
        try:
            proc = subprocess.run(
                cmd_args,
                cwd=self.repo_dir,
                timeout=effective_timeout,
                shell=False,
                capture_output=True,
                text=True,
                env=self.env,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            exit_code = proc.returncode
            status = "PASS" if exit_code == 0 else "FAIL"
        except subprocess.TimeoutExpired as exc:
            status = "TIMEOUT"
            exit_code = -1
            stdout = exc.stdout or "" if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr or "" if isinstance(exc.stderr, str) else ""

        stdout_lines = stdout.splitlines()
        stderr_lines = stderr.splitlines()
        stdout_tail = "\n".join(stdout_lines[-30:])
        stderr_tail = "\n".join(stderr_lines[-30:])

        error_first_line = ""
        if status == "FAIL":
            error_first_line = extract_error_line(stderr, stdout)
        elif status == "TIMEOUT":
            error_first_line = f"Timed out after {effective_timeout}s"

        return {
            "status": status,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "error_first_line": error_first_line,
        }

    def run_command(self, item: dict) -> dict:
        """Run a parsed command dictionary: {'line_no': int, 'command': str}."""
        line_no = item.get("line_no", 0)
        command = item.get("command", "")
        res = self.run_raw(command)
        res["line_no"] = line_no
        res["command"] = command
        res["fix"] = None
        res["fix_status"] = None
        return res


def run_all(commands: list[dict], repo_dir: Path | str, timeout: int = 120) -> list[dict]:
    """Execute a list of commands sequentially in a fresh venv."""
    results = []
    with VenvRunner(repo_dir=repo_dir, timeout=timeout) as runner:
        for item in commands:
            res = runner.run_command(item)
            results.append(res)
    return results
