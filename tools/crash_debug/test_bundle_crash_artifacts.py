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

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("bundle_crash_artifacts.py")


class TestBundleCrashArtifacts(unittest.TestCase):
    def _run_bundle(self, *args):
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), *(str(arg) for arg in args)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_cli_collects_crash_evidence_and_refuses_run_reuse(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            case_root = root / "case"

            log_a = root / "inputs" / "first" / "kit.log"
            log_b = root / "inputs" / "second" / "kit.log"
            log_a.parent.mkdir(parents=True)
            log_b.parent.mkdir(parents=True)
            log_a.write_text("first", encoding="utf-8")
            log_b.write_text("second", encoding="utf-8")

            crash_folder = root / "inputs" / "crash-folder"
            crash_folder.mkdir()
            uuid = "11111111-2222-3333-4444-555555555555"
            (crash_folder / "metadata.txt").write_text(f"DumpId={uuid}", encoding="utf-8")
            (crash_folder / "example.nv-gpudmp").write_text("gpu dump", encoding="utf-8")

            result = self._run_bundle(
                "--case-root",
                case_root,
                "--run-id",
                "RUN-001",
                "--title",
                "crash switch",
                "--kit-log",
                log_a,
                "--kit-log",
                log_b,
                "--dump",
                crash_folder,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn(f"MinidumpIds={uuid}", result.stdout)
            self.assertIn("AftermathDumpCount=1", result.stdout)

            run_dir = next(case_root.iterdir())
            copied_logs = sorted((run_dir / "kit-logs").iterdir())
            self.assertEqual(["first", "second"], sorted(path.read_text(encoding="utf-8") for path in copied_logs))
            self.assertEqual(2, len(copied_logs))

            manifest = next((root / "case").iterdir()).joinpath("RUN_MANIFEST.md").read_text(encoding="utf-8")
            self.assertIn("Minidump UUIDs:", manifest)
            self.assertIn("Aftermath GPU dumps:", manifest)
            self.assertIn(str(Path("dumps") / "crash-folder"), manifest)

            later_log = root / "later.log"
            later_log.write_text("later", encoding="utf-8")
            duplicate_result = self._run_bundle(
                "--case-root", root / "case", "--run-id", "RUN-001", "--kit-log", later_log
            )

            self.assertEqual(1, duplicate_result.returncode)
            self.assertIn("run folder already exists", duplicate_result.stderr)
            manifest = (run_dir / "RUN_MANIFEST.md").read_text(encoding="utf-8")
            self.assertNotIn("later.log", manifest)


if __name__ == "__main__":
    unittest.main()
