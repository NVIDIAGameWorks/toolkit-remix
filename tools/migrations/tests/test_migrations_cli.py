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
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.migrations import migrations_cli
from tools.migrations.migrations_cli import validate_args


class TestMigrationsCli(unittest.TestCase):
    def test_validate_args_uppercase_usd_file_suffix_accepts_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "LIGHT.USDA"
            path.write_text("#usda 1.0", encoding="utf-8")

            validate_args(argparse.Namespace(file=path, directory=None, recursive=False))

    def test_confirm_migration_prints_in_place_update_warning(self):
        output = io.StringIO()
        args = argparse.Namespace(file=Path("project.usda"), directory=None, recursive=False)

        with redirect_stdout(output), patch("builtins.input", return_value="q"), self.assertRaises(SystemExit):
            getattr(migrations_cli, "__confirm_migration")(args)

        self.assertIn("This migration updates files in place.", output.getvalue())
        self.assertIn("Save your project first or run it on a copy.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
