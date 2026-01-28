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
* See the License for the specific governing permissions and
* limitations under the License.
"""

"""
Run ruff format using the same ruff installation as repo_lint.

Temporary: Remove this when repo_format is updated to support ruff.
"""

import os
import subprocess
import sys
from pathlib import Path

# Bootstrap repo tools
REPO_ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../..")
sys.path.insert(0, os.path.join(REPO_ROOT, "tools", "repoman"))

import repoman  # noqa: E402

repoman.bootstrap()

# Now we can import from repo_lint
from omni.repo.lint import vendor_directory  # noqa: E402
from omni.repo.man.guidelines import is_windows  # noqa: E402


def main():
    ruff_bin_path = str(Path(vendor_directory, "bin", "ruff"))
    if is_windows():
        ruff_bin_path = f"{ruff_bin_path}.exe"

    # Print ruff version for debugging
    version_result = subprocess.run([ruff_bin_path, "--version"], capture_output=True, text=True)
    print(f"Using: {version_result.stdout.strip()}")

    config_file = os.path.join(REPO_ROOT, ".ruff.toml")
    default_path = os.path.join(REPO_ROOT, "source", "extensions")

    # Build command
    args = [ruff_bin_path, "format"]
    if os.path.exists(config_file):
        args.extend(["--config", config_file])

    # Process arguments: convert --verify to --check, detect if path was provided
    has_path = False
    for arg in sys.argv[1:]:
        if arg == "--verify":
            args.append("--check")
        elif not arg.startswith("-"):
            args.append(arg)
            has_path = True
        else:
            args.append(arg)

    # Always add default path if no path was explicitly provided
    if not has_path:
        args.append(default_path)

    print(f"Running: {' '.join(args)}")
    result = subprocess.run(args)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
