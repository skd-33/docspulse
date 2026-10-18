# DocsPulse

> Verify README install instructions by actually running them in an isolated virtual environment, and only label an AI-proposed fix **"verified"** if it passes when re-run.

[![Selftest](https://github.com/skd-33/docspulse/actions/workflows/selftest.yml/badge.svg)](https://github.com/skd-33/docspulse/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Zero-Install Usage

### 1. GitHub Action

Add DocsPulse to your CI workflow (e.g. `.github/workflows/docspulse.yml`):

```yaml
name: Verify README Instructions

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  verify-readme:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Verify README with DocsPulse
        uses: skd-33/docspulse@v1
        with:
          path: .
          provider: none  # or gemini
          # gemini-api-key: ${{ secrets.GEMINI_API_KEY }}
```

DocsPulse automatically creates a Markdown summary table and attaches it directly to your GitHub Action run summary (`$GITHUB_STEP_SUMMARY`).

### 2. Run via pipx (One-Liner)

No clone or manual install required:

```bash
pipx run --spec git+https://github.com/skd-33/docspulse docspulse .
```

You can also point DocsPulse directly at any local directory, specific README file, or public GitHub URL:

```bash
# Verify a remote repository
pipx run --spec git+https://github.com/skd-33/docspulse docspulse https://github.com/psf/requests
```

---

## The Problem

README install instructions frequently rot:
- Pinned dependency versions disappear from PyPI or conflict with newer Python releases.
- Required setup flags or environment steps are forgotten or changed.
- Contributors and end users hit confusing errors on their very first step.

Linters and static analyzers only check markdown syntax—they don't know whether `pip install foo` actually works. **DocsPulse bridges this gap by actually running your installation instructions and verifying the outcome.**

---

## How Verification Works

1. **Extraction**: Finds `README.md` (case-insensitive) or clones the target repository with `--depth 1`. Parses fenced code blocks (`bash`, `sh`, `console`, `python`, untagged), strips `$ ` prompts, joins multi-line `\` continuations, and filters comments.
2. **Safety Gate**: Inspects every candidate command against an executable allowlist and blocks dangerous tokens/shell operators before execution.
3. **Isolated Execution**: Spawns a clean, temporary Python virtual environment. Maps commands to the virtual environment's executables (`<venv python> -m pip ...`), captures the return code, and tracks the last 30 lines of output.
4. **AI-Powered Fix Verification**: If a command fails, DocsPulse can ask an LLM (Ollama or Gemini) for a single-line correction. The proposed fix is checked for safety and **re-run inside the same virtual environment**. A fix is labeled **"VERIFIED FIX"** if and only if it exits with code 0.
5. **Deterministic CI Exit**: Returns exit code `1` if any command failed without a verified fix, making it ideal for gating pull requests.

---

## Safety Model & Sandbox Limitations

DocsPulse adheres to a strict multi-layer security model:
- **Executable Allowlist**: Only commands starting with `pip`, `pip3`, `python`, `python3`, `pytest`, or `py` are executed.
- **Operator Blocking**: Chained commands (`&&`, `||`, `;`), subshells (`` ` ``, `$(`), pipes (`|`), redirections (`>`, `<`), and URLs piped into shells (`curl|sh`, `wget|sh`) are rejected.
- **Whole-Token Matching**: Dangerous commands like `rm`, `sudo`, `del`, `format`, and `shutdown` are matched strictly as whole words. Legitimate packages like `rmagick`, `pydelmar`, and `reformatter` are never blocked by naive substring matching.

> [!WARNING]
> **Important Sandbox Disclosure**:
> Commands run in a fresh virtual environment with an allowlist and timeout. However, **a Python virtual environment is not an OS-level sandbox** (e.g. `python script.py` can still execute arbitrary Python code). For untrusted third-party repositories, **always use the GitHub Action**, which executes inside GitHub's isolated, throwaway cloud runner.

---

## Model & Provider Configuration

DocsPulse supports multiple LLM providers:

```bash
# Default: Local Ollama (zero API cost, private)
docspulse . --provider ollama --model qwen2.5:1.5b

# Google Gemini (requires GEMINI_API_KEY environment variable)
export GEMINI_API_KEY="your-api-key"
docspulse . --provider gemini --model gemini-1.5-flash

# CI / Offline Mode (verification only, no AI fixes)
docspulse . --provider none
```

If the local Ollama daemon is not running or the Gemini API key is missing, DocsPulse prints an informative notice and continues verification without interrupting the run.

---

## Why There Is No Hosted Version

A hosted web service where users enter a repository URL would require executing untrusted, user-supplied command strings on server infrastructure. Providing true multi-tenant security for arbitrary code execution requires heavy microVM orchestration that adds unnecessary complexity and privacy risks.

Instead, DocsPulse is intentionally designed as a **lightweight, dependency-free CLI tool and GitHub Action** that runs locally on your machine or inside your own GitHub Actions runners.

---

## CLI Options

```text
usage: docspulse [-h] [--provider {ollama,gemini,none}] [--model MODEL]
                 [--timeout TIMEOUT]
                 target

Verify README install instructions by actually running them in an isolated environment.

positional arguments:
  target                Local repository/directory path, README file path, or GitHub URL.

options:
  -h, --help            show this help message and exit
  --provider {ollama,gemini,none}
                        LLM provider for generating proposed fixes (default: ollama).
  --model MODEL         LLM model name to query (default: qwen2.5:1.5b).
  --timeout TIMEOUT     Timeout in seconds for each command execution (default: 120).
```

---

## License

[MIT](LICENSE) © 2026 skd-33
