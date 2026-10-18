"""
Unit tests for MODULE 5: cli.py
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docspulse.cli import parse_args, run_pipeline


class TestCli(unittest.TestCase):
    def test_parse_args_defaults(self):
        args = parse_args(["./README.md"])
        self.assertEqual(args.target, "./README.md")
        self.assertEqual(args.provider, "ollama")
        self.assertEqual(args.model, "qwen2.5:1.5b")
        self.assertEqual(args.timeout, 120)

    def test_parse_args_custom(self):
        args = parse_args([
            "https://github.com/foo/bar",
            "--provider", "gemini",
            "--model", "gemini-1.5-flash",
            "--timeout", "60",
        ])
        self.assertEqual(args.target, "https://github.com/foo/bar")
        self.assertEqual(args.provider, "gemini")
        self.assertEqual(args.model, "gemini-1.5-flash")
        self.assertEqual(args.timeout, 60)

    def test_run_pipeline_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            readme = Path(tmp_dir) / "README.md"
            readme.write_text("```bash\npython -c \"print('cli test')\"\n```", encoding="utf-8")

            report_file = Path("report.md")
            if report_file.exists():
                report_file.unlink()

            exit_code = run_pipeline(str(tmp_dir), provider="none", timeout=15)
            self.assertEqual(exit_code, 0)
            self.assertTrue(Path("report.md").exists())
            Path("report.md").unlink()


if __name__ == "__main__":
    unittest.main()
