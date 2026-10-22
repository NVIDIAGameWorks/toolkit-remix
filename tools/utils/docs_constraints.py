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

Print the pip constraints for the docs build: the app pins from deps/pip_flux.toml that autodoc depends on.
"""

import tomllib
from pathlib import Path

_PACKAGES = ("pydantic",)
_PIP_FLUX = Path(__file__).resolve().parents[2] / "deps" / "pip_flux.toml"

pins = [
    pin
    for dependency in tomllib.loads(_PIP_FLUX.read_text(encoding="utf-8"))["dependency"]
    for pin in dependency["packages"]
    if pin.split("==")[0] in _PACKAGES
]
missing = set(_PACKAGES) - {pin.split("==")[0] for pin in pins}
if missing:
    raise SystemExit(f"No pin in {_PIP_FLUX} for: {', '.join(sorted(missing))}")
print("\n".join(pins))
