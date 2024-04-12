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
import omni.ext
from omni.kit.widget.stage.stage_column_delegate_registry import StageColumnDelegateRegistry

from .nickname_delegate import NicknameStageColumnDelegate


class StageNicknameWidgetExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self._nickname_column_sub = StageColumnDelegateRegistry().register_column_delegate(
            "Nickname", NicknameStageColumnDelegate
        )

    def on_shutdown(self):
        self._nickname_column_sub = None
