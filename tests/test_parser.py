"""
Unit tests for MODULE 1: parser.py
"""

import tempfile
import unittest
from pathlib import Path

from docspulse.parser import (
    find_readme_in_dir,
    is_git_url,
    parse_readme_content,
    resolve_target,
)


class TestParser(unittest.TestCase):
    def test_parse_sample_readme_string(self):
        readme_sample = """# Awesome Project

A sample project to test README parsing.

## Installation

```bash
# Update pip first
$ pip install --upgrade pip

$ pip install \\
    requests \\
    urllib3
```

## Usage

Here is how you use it:

```console
$ python main.py
Hello, World!
$ pytest tests/
===== 10 passed in 0.20s =====
```

## Configuration

This json block should be ignored:

```json
{
  "setting": true
}
```

## Untagged block

```
python -m docspulse .
```
"""
        commands = parse_readme_content(readme_sample)
        expected = [
            {"line_no": 9, "command": "pip install --upgrade pip"},
            {"line_no": 11, "command": "pip install requests urllib3"},
            {"line_no": 21, "command": "python main.py"},
            {"line_no": 23, "command": "pytest tests/"},
            {"line_no": 40, "command": "python -m docspulse ."},
        ]
        self.assertEqual(commands, expected)

    def test_strip_prompts_and_ignore_output(self):
        content = """```shell
$ pip install rmagick
Collecting rmagick
  Downloading rmagick.tar.gz
Successfully installed rmagick-1.0
$ python app.py
Starting server...
```"""
        commands = parse_readme_content(content)
        self.assertEqual(
            commands,
            [
                {"line_no": 2, "command": "pip install rmagick"},
                {"line_no": 6, "command": "python app.py"},
            ],
        )

    def test_line_continuation_without_prompts(self):
        content = """```bash
pip install \\
    flake8 \\
    black
python setup.py build
```"""
        commands = parse_readme_content(content)
        self.assertEqual(
            commands,
            [
                {"line_no": 2, "command": "pip install flake8 black"},
                {"line_no": 5, "command": "python setup.py build"},
            ],
        )

    def test_ignore_comments_and_empty_lines(self):
        content = """```python
# First comment
# Second comment

python run.py
```"""
        commands = parse_readme_content(content)
        self.assertEqual(commands, [{"line_no": 5, "command": "python run.py"}])

    def test_allowed_tags_filter(self):
        content = """```bash
pip install a
```
```sh
pip install b
```
```python
python test.py
```
```py
python test2.py
```
```javascript
npm install
```
```yaml
key: value
```
```
python default.py
```"""
        commands = parse_readme_content(content)
        expected = [
            {"line_no": 2, "command": "pip install a"},
            {"line_no": 5, "command": "pip install b"},
            {"line_no": 8, "command": "python test.py"},
            {"line_no": 11, "command": "python test2.py"},
            {"line_no": 20, "command": "python default.py"},
        ]
        self.assertEqual(commands, expected)

    def test_find_readme_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            readme = tmp_path / "Readme.Md"
            readme.write_text("# Test", encoding="utf-8")

            found = find_readme_in_dir(tmp_path)
            self.assertEqual(found, readme)

    def test_resolve_target_dir_and_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            readme = tmp_path / "README.md"
            readme.write_text("# Hello", encoding="utf-8")

            # Test dir resolution
            rm_path, repo_dir, temp_dir = resolve_target(tmp_path)
            self.assertEqual(rm_path, readme)
            self.assertEqual(repo_dir, tmp_path)
            self.assertIsNone(temp_dir)

            # Test file resolution
            rm_path2, repo_dir2, temp_dir2 = resolve_target(readme)
            self.assertEqual(rm_path2, readme)
            self.assertEqual(repo_dir2, tmp_path)
            self.assertIsNone(temp_dir2)

    def test_is_git_url(self):
        self.assertTrue(is_git_url("https://github.com/skd-33/docspulse"))
        self.assertTrue(is_git_url("https://github.com/skd-33/docspulse.git"))
        self.assertTrue(is_git_url("git@github.com:skd-33/docspulse.git"))
        self.assertFalse(is_git_url("./demo/broken-repo"))
        self.assertFalse(is_git_url("README.md"))


if __name__ == "__main__":
    unittest.main()
