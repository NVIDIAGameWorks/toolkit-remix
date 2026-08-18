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

__all__ = ["type_key"]

# One namespace for every ComfyUI factory and persistence key. Keys are derived from the class
# name so no registry ever carries a hand-written string that can drift from the type it identifies.
_KEY_PREFIX = "comfyui."


def type_key(registered_type: type) -> str:
    """Return the stable factory and persistence key derived from a type's name.

    Args:
        registered_type: Class whose stable identifier is derived.

    Returns:
        The namespaced key that identifies the type across the factory and persistence registries.
    """
    return f"{_KEY_PREFIX}{registered_type.__name__}"
