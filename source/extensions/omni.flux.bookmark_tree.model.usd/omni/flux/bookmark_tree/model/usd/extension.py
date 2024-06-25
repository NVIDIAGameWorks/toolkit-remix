"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from typing import Optional

import carb
import omni.ext

from .listener import USDListener as _USDListener

_USD_LISTENER_INSTANCE = None


def get_usd_listener_instance() -> Optional[_USDListener]:
    return _USD_LISTENER_INSTANCE


class UsdBookmarkCollectionWidgetExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        global _USD_LISTENER_INSTANCE
        carb.log_info("[omni.flux.bookmark_tree.model.usd] Startup")
        _USD_LISTENER_INSTANCE = _USDListener()

    def on_shutdown(self):
        global _USD_LISTENER_INSTANCE
        carb.log_info("[omni.flux.bookmark_tree.model.usd] Shutdown")
        _USD_LISTENER_INSTANCE.destroy()
        _USD_LISTENER_INSTANCE = None
