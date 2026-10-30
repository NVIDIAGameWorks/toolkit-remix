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

__all__ = ["AssetModifiersFactoryExtension", "get_instance"]

from omni.ext import IExt

from .factory import AssetModifierFactory

_INSTANCE: AssetModifierFactory | None = None


def get_instance() -> AssetModifierFactory:
    """Return the factory that providers register their modifiers with."""
    return _INSTANCE


class AssetModifiersFactoryExtension(IExt):
    """Create the asset modifier factory for the extension lifetime."""

    def on_startup(self, ext_id: str) -> None:
        """Create the factory before provider extensions register their modifiers."""
        global _INSTANCE
        _INSTANCE = AssetModifierFactory()

    def on_shutdown(self) -> None:
        """Release the factory and its registered modifiers."""
        global _INSTANCE
        if _INSTANCE is not None:
            _INSTANCE.destroy()
        _INSTANCE = None
