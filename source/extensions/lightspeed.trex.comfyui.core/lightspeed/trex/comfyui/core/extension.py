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

__all__ = ["get_comfyui_instance", "ComfyUICoreExtension"]

from typing import Optional

import carb
import omni.ext

from .core import ComfyUICore

_instance: Optional[ComfyUICore] = None


def get_comfyui_instance() -> ComfyUICore:
    return _instance


class ComfyUICoreExtension(omni.ext.IExt):
    def on_startup(self, _ext_id):
        carb.log_info("[lightspeed.trex.comfyui.core] Startup")

        global _instance
        _instance = ComfyUICore()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.comfyui.core] Shutdown")

        global _instance
        _instance = None
