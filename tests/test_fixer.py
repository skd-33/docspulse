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
    get_heuristic_pip_fixes,
)


class TestFixer(unittest.TestCase):
    def test_get_heuristic_pip_fixes_with_versions(self):
        stderr = "ERROR: Could not find a version that satisfies the requirement requests==99.0.0 (from versions: 0.1.0, 2.31.0, 2.32.3)\nERROR: No matching distribution found for requests==99.0.0"
        fixes = get_heuristic_pip_fixes("pip install requests==99.0.0", stderr)
        self.assertEqual(
            fixes,
            ["pip install requests==2.32.3", "pip install requests"],
        )

    def test_get_heuristic_pip_fixes_without_versions(self):
        stderr = "ERROR: Could not find a version that satisfies the requirement fake-pkg==1.0 (from versions: none)\nERROR: No matching distribution found for fake-pkg==1.0"
        fixes = get_heuristic_pip_fixes("pip install fake-pkg==1.0", stderr)
        self.assertEqual(fixes, ["pip install fake-pkg"])

    def test_attempt_fix_deterministic_heuristic_works_with_provider_none(self):
        mock_runner = MagicMock()
        mock_runner.run_raw.return_value = {"exit_code": 0, "status": "PASS"}

        cmd_result = {
            "status": "FAIL",
            "command": "pip install requests==99.0.0",
            "stderr": "ERROR: Could not find a version that satisfies the requirement requests==99.0.0 (from versions: 2.32.3)\nERROR: No matching distribution found",
            "stdout": "",
            "stderr_tail": "ERROR: No matching distribution found",
            "fix": None,
            "fix_status": None,
            "fix_source": None,
        }

        # Must work even with provider="none"!
        res = attempt_fix(cmd_result, mock_runner, provider="none")
        self.assertEqual(res["fix_status"], "VERIFIED FIX")
        self.assertEqual(res["fix_source"], "heuristic")
        self.assertEqual(res["fix"], "pip install requests==2.32.3")
        mock_runner.run_raw.assert_called_once_with("pip install requests==2.32.3")
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

    def test_build_fix_prompt_attempt_1(self):
        prompt = build_fix_prompt(
            "pip install requests==99.0.0",
            "ERROR: No matching distribution found",
            attempt=1,
        )
        self.assertIn("pip install requests==99.0.0", prompt)
        self.assertIn("ERROR: No matching distribution found", prompt)
        self.assertIn("ONLY one corrected command", prompt)

    def test_build_fix_prompt_attempt_2(self):
        prompt = build_fix_prompt(
            "pip install requests==99.0.0",
            "ERROR: No matching distribution found",
            attempt=2,
            previous_fix="pip install requests==98.0.0",
            previous_error="ERROR: 98.0.0 not found either",
        )
        self.assertIn("Previous attempt that FAILED: pip install requests==98.0.0", prompt)
        self.assertIn("Error from previous fix:\nERROR: 98.0.0 not found either", prompt)
        self.assertIn("Do NOT repeat the previous failed command", prompt)
        self.assertIn("ONLY one DIFFERENT corrected command", prompt)

    def test_attempt_fix_skips_identical_candidate(self):
        mock_runner = MagicMock()
        mock_runner.run_raw.return_value = {
            "exit_code": 1,
            "status": "FAIL",
            "stderr_tail": "still broken",
        }

        cmd_result = {
            "status": "FAIL",
            "command": "pip install foo==1.0",
            "stderr_tail": "ERROR: not found",
            "fix": None,
            "fix_status": None,
        }

        # Mock LLM returns the exact same candidate on attempt 2 as attempt 1:
        with patch("docspulse.fixer.ask_llm", side_effect=["pip install foo==2.0", "pip install foo==2.0"]):
            res = attempt_fix(cmd_result, mock_runner, provider="ollama")

        self.assertEqual(res["fix_status"], "FIX NOT VERIFIED")
        # Runner must ONLY have been called ONCE because attempt 2 was identical!
        self.assertEqual(mock_runner.run_raw.call_count, 1)

    def test_attempt_fix_skips_original_failed_command(self):
        mock_runner = MagicMock()

        cmd_result = {
            "status": "FAIL",
            "command": "pip install foo",
            "stderr_tail": "ERROR: not found",
            "fix": None,
            "fix_status": None,
        }

        # Mock LLM returns the original failed command:
        with patch("docspulse.fixer.ask_llm", return_value="pip install foo"):
            res = attempt_fix(cmd_result, mock_runner, provider="ollama")

        self.assertEqual(res["fix_status"], "FIX NOT VERIFIED")
        # Runner should never be called to re-run the same failing command!
        mock_runner.run_raw.assert_not_called()

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
            "command": "python script.py --wrong-flag",
            "stderr": "unrecognized arguments: --wrong-flag",
            "stdout": "",
            "stderr_tail": "unrecognized arguments: --wrong-flag",
            "fix": None,
            "fix_status": None,
            "fix_source": None,
        }

        with patch("docspulse.fixer.ask_llm", return_value="python script.py"):
            res = attempt_fix(cmd_result, mock_runner, provider="ollama")

        self.assertEqual(res["fix"], "python script.py")
        self.assertEqual(res["fix_status"], "VERIFIED FIX")
        self.assertEqual(res["fix_source"], "llm")
        mock_runner.run_raw.assert_called_once_with("python script.py")

    def test_attempt_fix_unsafe_candidate(self):
        mock_runner = MagicMock()

        cmd_result = {
            "status": "FAIL",
            "command": "python script.py",
            "stderr": "some error",
            "stdout": "",
            "stderr_tail": "some error",
            "fix": None,
            "fix_status": None,
            "fix_source": None,
        }

        # Mock LLM returns dangerous command
        with patch("docspulse.fixer.ask_llm", return_value="rm -rf /"):
            res = attempt_fix(cmd_result, mock_runner, provider="ollama")

        self.assertEqual(res["fix_status"], "FIX NOT VERIFIED")
        # Ensure runner was NEVER called for the unsafe candidate!
        mock_runner.run_raw.assert_not_called()

    def test_attempt_fix_not_verified_after_max_candidates(self):
        mock_runner = MagicMock()
        mock_runner.run_raw.return_value = {
            "exit_code": 1,
            "status": "FAIL",
            "stderr_tail": "still broken",
        }

        cmd_result = {
            "status": "FAIL",
            "command": "python test.py",
            "stderr": "syntax error",
            "stdout": "",
            "stderr_tail": "syntax error",
            "fix": None,
            "fix_status": None,
            "fix_source": None,
        }

        with patch(
            "docspulse.fixer.ask_llm",
            side_effect=["python test1.py", "python test2.py", "python test3.py"],
        ):
            res = attempt_fix(cmd_result, mock_runner, provider="ollama")

        self.assertEqual(res["fix_status"], "FIX NOT VERIFIED")
        self.assertEqual(mock_runner.run_raw.call_count, 3)


if __name__ == "__main__":
    unittest.main()
