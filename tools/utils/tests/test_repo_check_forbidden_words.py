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

from tools.utils.repo_check_forbidden_words import setup_repo_tool


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
                    # sys.exit(message) -> exit code 1 with the message as the argument
                    return 1, output.getvalue() + str(exc.code)
        finally:
            os.chdir(previous)


class TestRepoCheckForbiddenWords(unittest.TestCase):
    def _config(self, words=None, include=None):
        return {
            "repo_check_forbidden_words": {
                "files": {"include": include if include is not None else ["**/*.py"]},
                "words": {"exclude": words if words is not None else ["lightspeed", "trex"]},
            }
        }

    def test_no_forbidden_words_exits_zero(self):
        code, _output = _run_repo_tool(
            self._config(),
            {"src/main.py": "import os\nprint('hello')\n"},
        )
        self.assertEqual(code, 0)

    def test_forbidden_word_detected(self):
        code, output = _run_repo_tool(
            self._config(),
            {"src/main.py": "import lightspeed\n"},
        )
        self.assertEqual(code, 1)
        self.assertIn("src/main.py", output)
        self.assertIn("lightspeed", output)

    def test_second_forbidden_word_detected(self):
        code, output = _run_repo_tool(
            self._config(),
            {"src/main.py": "x = 'trex'\n"},
        )
        self.assertEqual(code, 1)
        self.assertIn("src/main.py", output)
        self.assertIn("trex", output)

    def test_word_as_substring_in_other_word_is_still_flagged(self):
        # 'trex' is a substring of 'trexology' - the tool matches substrings on purpose,
        # so this is expected to be flagged.
        code, output = _run_repo_tool(
            self._config(),
            {"src/main.py": "import trexology\n"},
        )
        self.assertEqual(code, 1)
        self.assertIn("trex", output)

    def test_multiple_files_only_flags_offending_ones(self):
        code, output = _run_repo_tool(
            self._config(),
            {
                "src/clean.py": "import os\n",
                "src/dirty.py": "import trex\n",
                "src/also_clean.py": "print('ok')\n",
            },
        )
        self.assertEqual(code, 1)
        self.assertIn("dirty.py", output)
        self.assertNotIn("clean.py", output)
        self.assertNotIn("also_clean.py", output)

    def test_empty_include_glob_matches_nothing_exits_zero(self):
        code, _output = _run_repo_tool(
            self._config(include=["**/nonexistent/**/*.py"]),
            {"src/main.py": "import trex\n"},
        )
        self.assertEqual(code, 0)

    def test_default_words_when_config_section_missing(self):
        # When the whole section is absent, the tool should treat words/include as empty
        # rather than crashing with AttributeError.
        code, output = _run_repo_tool(
            {},
            {"src/main.py": "import lightspeed\n"},
        )
        self.assertEqual(code, 0)
        self.assertEqual(output, "")

    def test_custom_forbidden_word_list_is_used(self):
        code, _output = _run_repo_tool(
            self._config(words=["lightspeed"]),
            {"src/main.py": "import lightspeed\n"},
        )
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()