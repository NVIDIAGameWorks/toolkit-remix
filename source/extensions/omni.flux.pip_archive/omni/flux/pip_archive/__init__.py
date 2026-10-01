"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import importlib.util
import os
import sys

if (spec := importlib.util.find_spec("pygit2")) and spec.origin:
    # Fix pygit2 DLL loading on Windows Python 3.8+
    if sys.platform == "win32":
        os.add_dll_directory(os.path.dirname(spec.origin))
    # Kit's importer matches dist-info folders by exact spelling, so `version("email-validator")` misses
    # `email_validator-*.dist-info` and pydantic's EmailStr check fails. The stdlib finder normalizes names;
    # imports still resolve through Kit's importer first.
    _prebundle = os.path.dirname(os.path.dirname(spec.origin))
    if _prebundle not in sys.path:
        sys.path.append(_prebundle)
