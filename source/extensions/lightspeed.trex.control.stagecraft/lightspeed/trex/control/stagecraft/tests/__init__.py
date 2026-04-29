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

from .e2e.test_capture_swap_undo import TestCaptureSwapUndo
from .e2e.test_hotkeys import TestHotkeys
from .e2e.test_stage_manager import TestStageManagerPropertiesInteraction
from .unit.test_check_capture_on_open import TestCheckCaptureOnOpen
from .unit.test_commands import TestCommands
from .unit.test_setup import TestSetup as TestSetupUnit

__all__ = [
    "TestCaptureSwapUndo",
    "TestCheckCaptureOnOpen",
    "TestCommands",
    "TestHotkeys",
    "TestSetupUnit",
    "TestStageManagerPropertiesInteraction",
]
