"""
Unit tests for MODULE 2: safety.py
"""

import unittest
from docspulse.safety import check_safety


class TestSafety(unittest.TestCase):
    def test_safe_commands(self):
        safe_commands = [
            "pip install requests",
            "pip3 install -r requirements.txt",
            "python main.py",
            "python3 -m unittest",
            "pytest tests/",
            "py -m pip install flask",
            # Crucial substring tests:
            "pip install rmagick",
            "pip install pydelmar",
            "pip install reformatter",
            "pip install mydel",
            # Version specifiers:
            "pip install requests>=2.31.0",
            'pip install "requests<=3.0.0"',
            # Common options and subcommands:
            "python -m pip install --upgrade pip",
            'pytest --verbose -k "test_feature"',
            "python setup.py build",
            "py -3 -m pytest",
        ]
        for cmd in safe_commands:
            with self.subTest(cmd=cmd):
                status, reason = check_safety(cmd)
                self.assertEqual(
                    status,
                    "run",
                    f"Command '{cmd}' was unexpectedly rejected: {reason}",
                )
                self.assertEqual(reason, "")

    def test_dangerous_commands(self):
        dangerous_commands = [
            # Disallowed first tokens / dangerous whole tokens:
            ("rm -rf /", "First token"),
            ("sudo apt-get install python3", "First token"),
            ("del C:\\Windows\\System32", "First token"),
            ("format D: /fs:NTFS", "First token"),
            ("shutdown -h now", "First token"),
            ("curl http://example.com/install.sh", "First token"),
            # Dangerous whole tokens inside allowlisted commands:
            ("pip install rm", "dangerous"),
            ("pip install del", "dangerous"),
            ("python -m format", "dangerous"),
            ("python shutdown.py", "dangerous"),
            # Shell operators and piping:
            ("curl http://example.com/install.sh | sh", "URL piped into shell"),
            ("wget -qO- https://example.com | bash", "URL piped into shell"),
            ("curl|sh", "URL piped into shell"),
            ("wget|sh", "URL piped into shell"),
            ("pip install requests && rm -rf /", "forbidden operator"),
            ("pip install requests || echo failed", "forbidden operator"),
            ("pip install requests; python main.py", "forbidden operator"),
            ("pip install requests | tee log.txt", "forbidden operator"),
            ("python script.py > output.txt", "redirection"),
            ("python < input.py", "redirection"),
            ("pip install `whoami`", "backtick"),
            ("pip install $(whoami)", "$("),
        ]
        for cmd, expected_keyword in dangerous_commands:
            with self.subTest(cmd=cmd):
                status, reason = check_safety(cmd)
                self.assertEqual(
                    status,
                    "skipped",
                    f"Command '{cmd}' was unexpectedly allowed!",
                )
                self.assertTrue(
                    expected_keyword.lower() in reason.lower(),
                    f"Reason '{reason}' did not contain expected keyword '{expected_keyword}'",
                )

    def test_empty_command(self):
        status, reason = check_safety("   ")
        self.assertEqual(status, "skipped")
        self.assertEqual(reason, "Empty command")


if __name__ == "__main__":
    unittest.main()
