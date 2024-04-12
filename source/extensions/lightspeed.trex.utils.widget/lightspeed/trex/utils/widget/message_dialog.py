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
from typing import Callable, Optional

from omni.kit.widget.prompt import PromptButtonInfo, PromptManager


class TrexMessageDialog:
    def __init__(
        self,
        message: str,
        title: str = "",
        ok_label: str = "Okay",
        middle_label: str = "No",
        middle_2_label: str = "Middle",
        cancel_label: str = "Cancel",
        disable_ok_button: bool = False,
        disable_middle_button: bool = True,
        disable_middle_2_button: bool = True,
        disable_cancel_button: bool = False,
        ok_handler: Optional[Callable] = None,
        middle_handler: Optional[Callable] = None,
        middle_2_handler: Optional[Callable] = None,
        cancel_handler: Optional[Callable] = None,
        on_window_closed_fn: Callable[[], None] = None,
    ):
        PromptManager.post_simple_prompt(
            title,
            message,
            ok_button_info=None if disable_ok_button else PromptButtonInfo(ok_label, ok_handler),
            middle_button_info=None if disable_middle_button else PromptButtonInfo(middle_label, middle_handler),
            middle_2_button_info=None
            if disable_middle_2_button
            else PromptButtonInfo(middle_2_label, middle_2_handler),
            cancel_button_info=None if disable_cancel_button else PromptButtonInfo(cancel_label, cancel_handler),
            modal=True,
            no_title_bar=not bool(title),
            on_window_closed_fn=on_window_closed_fn,
        )
