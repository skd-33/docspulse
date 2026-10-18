"""
Unit tests for MODULE 5: report.py
"""

import tempfile
import unittest
from pathlib import Path

from docspulse.report import (
    escape_markdown,
    generate_counts,
    generate_markdown_report,
    has_unfixed_failures,
    write_report_file,
)


class TestReport(unittest.TestCase):
    def test_generate_counts(self):
        results = [
            {"status": "PASS", "fix_status": None},
            {"status": "FAIL", "fix_status": "VERIFIED FIX"},
            {"status": "FAIL", "fix_status": "FIX NOT VERIFIED"},
            {"status": "SKIPPED", "fix_status": None},
        ]
        counts = generate_counts(results)
        self.assertEqual(counts["total"], 4)
        self.assertEqual(counts["passed"], 1)
        self.assertEqual(counts["failed"], 2)
        self.assertEqual(counts["skipped"], 1)
        self.assertEqual(counts["verified_fixes"], 1)
        self.assertEqual(counts["unverified_fixes"], 1)

    def test_has_unfixed_failures(self):
        # All pass
        self.assertFalse(has_unfixed_failures([{"status": "PASS"}]))

        # Pass and skipped
        self.assertFalse(has_unfixed_failures([{"status": "PASS"}, {"status": "SKIPPED"}]))

        # Failed with verified fix -> passes
        self.assertFalse(
            has_unfixed_failures([{"status": "FAIL", "fix_status": "VERIFIED FIX"}])
        )

        # Failed without fix -> fails
        self.assertTrue(
            has_unfixed_failures([{"status": "FAIL", "fix_status": None}])
        )

        # Failed with unverified fix -> fails
        self.assertTrue(
            has_unfixed_failures([{"status": "FAIL", "fix_status": "FIX NOT VERIFIED"}])
        )

    def test_markdown_report_formatting(self):
        results = [
            {
                "line_no": 2,
                "command": "pip install requests",
                "status": "PASS",
                "error_first_line": "",
                "fix": None,
                "fix_status": None,
            },
            {
                "line_no": 5,
                "command": "pip install broken_pkg",
                "status": "FAIL",
                "error_first_line": "ERROR: Not found | details",
                "fix": "pip install fixed_pkg",
                "fix_status": "VERIFIED FIX",
            },
        ]
        report = generate_markdown_report(results)
        self.assertIn("# DocsPulse Verification Report", report)
        self.assertIn("- **Total Commands:** 2", report)
        self.assertIn("- **Passed:** 1", report)
        self.assertIn("- **Verified Fixes:** 1", report)
        self.assertIn("| 2 | `pip install requests` | **PASS** | - | - |", report)
        self.assertIn("| 5 | `pip install broken_pkg` | **FAIL** | ERROR: Not found \\| details | `pip install fixed_pkg` *(VERIFIED)* |", report)

    def test_escape_pipe_in_table_cells(self):
        results = [
            {
                "line_no": 8,
                "command": "curl http://x | sh",
                "status": "SKIPPED",
                "error_first_line": "Pipe | is forbidden",
                "fix": "echo a | echo b",
                "fix_status": "FIX NOT VERIFIED",
            }
        ]
        report = generate_markdown_report(results)
        # Verify that | is escaped as \| in command, error, and fix
        self.assertIn("`curl http://x \\| sh`", report)
        self.assertIn("Pipe \\| is forbidden", report)
        self.assertIn("`echo a \\| echo b` *(NOT VERIFIED)*", report)

    def test_write_report_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "test_report.md"
            results = [{"status": "PASS", "line_no": 1, "command": "pip install requests"}]
            written = write_report_file(results, out_file)
            self.assertTrue(written.exists())
            self.assertIn("# DocsPulse Verification Report", written.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
