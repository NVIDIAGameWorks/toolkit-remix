# SPDX-FileCopyrightText: Copyright (c) 2021-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

import contextlib
import io
import os
import sys

import packmanapi
from repoman_bootstrapper import repoman_bootstrap

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "../.."))
REPO_DEPS_FILE = os.path.join(REPO_ROOT, "deps/repo-deps.packman.xml")
REPO_DEPS_INTERNAL_FILE = os.path.join(REPO_ROOT, "deps/repo-deps-internal.packman.xml")

def _repo_deps_files():
    deps_files = [REPO_DEPS_FILE]
    if os.path.exists(REPO_DEPS_INTERNAL_FILE):
        deps_files.append(REPO_DEPS_INTERNAL_FILE)
    return deps_files



def bootstrap():
    """Bootstrap repo_man without downloading private repo content at runtime."""
    with contextlib.redirect_stdout(io.StringIO()):
        for deps_file in _repo_deps_files():
            deps = packmanapi.pull(deps_file)
            for dep_path in deps.values():
                if dep_path not in sys.path:
                    sys.path.append(dep_path)


if __name__ == "__main__":
    repoman_bootstrap()
    bootstrap()
    import omni.repo.man

    omni.repo.man.main(REPO_ROOT)
