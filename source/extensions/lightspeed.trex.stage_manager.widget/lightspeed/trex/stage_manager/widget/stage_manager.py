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

from lightspeed.trex.utils.widget import WorkspaceWidget as _WorkspaceWidget
from omni.flux.stage_manager.widget import StageManagerWidget as _StageManagerWidget


class StageManagerWidget(_StageManagerWidget, _WorkspaceWidget):
    # This extension is only used to:
    # - Pull all the plugins required for the Lightspeed StageManager Widget
    # - Define the schema path in the settings

    def show(self, visible: bool):
        """Implements WorkspaceWidget interface."""
        pass

    def destroy(self):
        """Implements WorkspaceWidget interface."""
        pass
