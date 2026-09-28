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

import sys
from pathlib import Path
from subprocess import run

import omni.kit.test
from carb.tokens import get_tokens_interface


class TestPipArchiveE2E(omni.kit.test.AsyncTestCase):
    async def test_import_requests_in_fresh_process_uses_consistent_prebundle(self):
        """Check that requests and charset-normalizer load together from the packaged archive."""
        # Arrange
        extension_path = get_tokens_interface().resolve("${omni.flux.pip_archive}")
        prebundle_path = (Path(extension_path) / "flux_pip_prebundle").resolve()
        python_path = Path(sys.base_prefix) / ("python.exe" if sys.platform == "win32" else "bin/python3")
        script = """
import pathlib
import sys

sys.path.insert(0, sys.argv[1])

import requests
import charset_normalizer

charset_normalizer.from_bytes(b"RTX Remix").best()
print(pathlib.Path(requests.__file__).resolve())
print(pathlib.Path(charset_normalizer.__file__).resolve())
"""

        # Act
        result = run([python_path, "-I", "-c", script, prebundle_path], capture_output=True, check=False, text=True)

        # Assert
        self.assertEqual(result.returncode, 0, result.stderr)
        requests_path, charset_normalizer_path = (Path(path) for path in result.stdout.splitlines())
        self.assertTrue(requests_path.is_relative_to(prebundle_path), requests_path)
        self.assertTrue(charset_normalizer_path.is_relative_to(prebundle_path), charset_normalizer_path)
