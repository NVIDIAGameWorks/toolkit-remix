"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import argparse
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.utils.repo_check_test_file_location import setup_repo_tool


def _run_repo_tool(config, files):
    """Create `files` (relpath -> content) in a temp dir, run the tool, return (exit_code, output)."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for rel, content in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        previous = os.getcwd()
        os.chdir(directory)
        try:
            parser = argparse.ArgumentParser()
            run = setup_repo_tool(parser, config)
            output = StringIO()
            with redirect_stdout(output):
                try:
                    run(argparse.Namespace(), config)
                    return 0, output.getvalue()
                except SystemExit as exc:
                    return 1, output.getvalue() + str(exc.code)
        finally:
            os.chdir(previous)


class TestRepoCheckTestFileLocation(unittest.TestCase):
    def _config(self, include=None, exclude=None, allow_paths=None):
        return {
            "repo_check_test_file_location": {
                "files": {
                    "include": include if include is not None else ["**/tests/**/test_*.py"],
                    "exclude": exclude if exclude is not None else [],
                },
                "rule": {
                    "allow_paths": allow_paths if allow_paths is not None else ["**/tests/unit/**/*.py"],
                },
            }
        }

    def test_test_file_in_allowed_location_exits_zero(self):
        code, _output = _run_repo_tool(
            self._config(),
            {"proj/tests/unit/test_foo.py": "def test_foo():\n    pass\n"},
        )
        self.assertEqual(code, 0)

    def test_test_file_in_disallowed_location_is_flagged(self):
        code, output = _run_repo_tool(
            self._config(),
            {"proj/tests/test_bar.py": "def test_bar():\n    pass\n"},
        )
        self.assertEqual(code, 1)
        self.assertIn("test_bar.py", output)
        self.assertIn("rule.allow_paths", output)

    def test_test_file_in_e2e_location_is_flagged_when_not_allowed(self):
        code, output = _run_repo_tool(
            self._config(),
            {"proj/tests/e2e/test_baz.py": "def test_baz():\n    pass\n"},
        )
        self.assertEqual(code, 1)
        self.assertIn("test_baz.py", output)

    def test_excluded_files_are_ignored(self):
        code, _output = _run_repo_tool(
            self._config(exclude=["**/tests/test_bar.py"]),
            {
                "proj/tests/unit/test_foo.py": "def test_foo():\n    pass\n",
                "proj/tests/test_bar.py": "def test_bar():\n    pass\n",
            },
        )
        self.assertEqual(code, 0)

    def test_no_test_files_exits_zero(self):
        code, _output = _run_repo_tool(
            self._config(),
            {"proj/src/main.py": "x = 1\n"},
        )
        self.assertEqual(code, 0)

    def test_missing_config_section_does_not_crash(self):
        # When the whole section is absent the tool must not raise AttributeError.
        code, output = _run_repo_tool(
            {},
            {"proj/tests/test_bar.py": "def test_bar():\n    pass\n"},
        )
        self.assertEqual(code, 0)
        self.assertEqual(output, "")

    def test_missing_files_key_uses_default_include(self):
        # When the `files` key is absent entirely, the default include glob
        # (`**/source/**/tests/*.py`) should still be applied rather than crashing.
        config = {
            "repo_check_test_file_location": {
                "rule": {"allow_paths": ["**/tests/unit/**/*.py"]},
            }
        }
        code, output = _run_repo_tool(
            config,
            {"source/tests/test_bar.py": "def test_bar():\n    pass\n"},
        )
        self.assertEqual(code, 1)
        self.assertIn("test_bar.py", output)

    def test_missing_rule_key_uses_default_allow_paths(self):
        # When the `rule` key is absent, the default allow_paths
        # (`**/source/**/tests/__init__.py`) is used, so a normal test file is
        # flagged rather than accepted.
        config = {
            "repo_check_test_file_location": {
                "files": {"include": ["**/tests/**/test_*.py"], "exclude": []},
            }
        }
        code, output = _run_repo_tool(
            config,
            {"proj/tests/unit/test_foo.py": "def test_foo():\n    pass\n"},
        )
        self.assertEqual(code, 1)
        self.assertIn("test_foo.py", output)


if __name__ == "__main__":
    unittest.main()