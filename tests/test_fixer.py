"""
Unit tests for MODULE 4: fixer.py
"""

import unittest
from unittest.mock import MagicMock, patch

from docspulse.fixer import (
    ask_llm,
    attempt_fix,
    build_fix_prompt,
    clean_llm_response,
)


class TestFixer(unittest.TestCase):
    def test_clean_llm_response(self):
        # Code fence with bash
        self.assertEqual(
            clean_llm_response("```bash\npip install requests\n```"),
            "pip install requests",
        )
        # Inline backticks
        self.assertEqual(
            clean_llm_response("`pip install requests`"),
            "pip install requests",
        )
        # Leading prompt
        self.assertEqual(
            clean_llm_response("$ pip install requests"),
            "pip install requests",
        )
        # Explanatory multiline text
        text = "pip install requests\nThis will install the latest version."
        self.assertEqual(clean_llm_response(text), "pip install requests")

    def test_build_fix_prompt(self):
        prompt = build_fix_prompt(
            "pip install requests==99.0.0",
            "ERROR: No matching distribution found",
        )
        self.assertIn("pip install requests==99.0.0", prompt)
        self.assertIn("ERROR: No matching distribution found", prompt)
        self.assertIn("ONLY one corrected command", prompt)

    def test_ask_llm_none_provider(self):
        self.assertEqual(ask_llm("test", provider="none"), "")

    def test_ask_llm_gemini_without_key(self):
        with patch.dict("os.environ", {}, clear=True):
            res = ask_llm("test", provider="gemini")
            self.assertEqual(res, "")

    def test_ask_llm_ollama_not_running(self):
        # Test error handling when Ollama cannot be reached
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            res = ask_llm("test", provider="ollama")
            self.assertEqual(res, "")

    def test_attempt_fix_verified_fix(self):
        mock_runner = MagicMock()
        mock_runner.run_raw.return_value = {"exit_code": 0, "status": "PASS"}

        cmd_result = {
            "status": "FAIL",
            "command": "pip install requests==99.0.0",
            "stderr_tail": "ERROR: Could not find a version",
            "fix": None,
            "fix_status": None,
        }

        with patch("docspulse.fixer.ask_llm", return_value="pip install requests"):
            res = attempt_fix(cmd_result, mock_runner, provider="ollama")

        self.assertEqual(res["fix"], "pip install requests")
        self.assertEqual(res["fix_status"], "VERIFIED FIX")
        mock_runner.run_raw.assert_called_once_with("pip install requests")

    def test_attempt_fix_unsafe_candidate(self):
        mock_runner = MagicMock()

        cmd_result = {
            "status": "FAIL",
            "command": "pip install requests==99.0.0",
            "stderr_tail": "ERROR",
            "fix": None,
            "fix_status": None,
        }

        # Mock LLM returns dangerous command
        with patch("docspulse.fixer.ask_llm", return_value="rm -rf /"):
            res = attempt_fix(cmd_result, mock_runner, provider="ollama")

        self.assertEqual(res["fix_status"], "FIX NOT VERIFIED")
        # Ensure runner was NEVER called for the unsafe candidate!
        mock_runner.run_raw.assert_not_called()

    def test_attempt_fix_not_verified_after_2_attempts(self):
        mock_runner = MagicMock()
        mock_runner.run_raw.return_value = {
            "exit_code": 1,
            "status": "FAIL",
            "stderr_tail": "still broken",
        }

        cmd_result = {
            "status": "FAIL",
            "command": "pip install foo",
            "stderr_tail": "ERROR: not found",
            "fix": None,
            "fix_status": None,
        }

        with patch("docspulse.fixer.ask_llm", return_value="pip install foo-fixed"):
            res = attempt_fix(cmd_result, mock_runner, provider="ollama")

        self.assertEqual(res["fix_status"], "FIX NOT VERIFIED")
        self.assertEqual(mock_runner.run_raw.call_count, 2)


if __name__ == "__main__":
    unittest.main()
