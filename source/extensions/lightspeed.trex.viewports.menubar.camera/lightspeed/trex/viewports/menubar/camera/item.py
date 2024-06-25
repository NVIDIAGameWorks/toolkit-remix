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

from typing import Any, Callable

from omni.kit.viewport.menubar.camera import SingleCameraMenuItemBase


def lss_single_camera_menu_item(*args, lss_option_clicked: Callable[[str], Any] = None, **kwargs):
    class LssSingleCameraMenuItem(SingleCameraMenuItemBase):
        def _option_clicked(self):
            lss_option_clicked(self.camera_path.pathString)

    return LssSingleCameraMenuItem(*args, **kwargs)
