"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Callable, Optional

from omni.kit.widget.prompt import PromptButtonInfo, PromptManager


class TrexMessageDialog:
    def __init__(
        self,
        message: str,
        title: str = "",
        ok_label: str = "Okay",
        cancel_label: str = "Cancel",
        middle_label: str = "Middle",
        middle_2_label: str = "Middle_2",
        disable_ok_button: bool = False,
        disable_cancel_button: bool = False,
        disable_middle_button: bool = True,
        disable_middle_2_button: bool = True,
        ok_handler: Optional[Callable] = None,
        cancel_handler: Optional[Callable] = None,
        middle_handler: Optional[Callable] = None,
        middle_2_handler: Optional[Callable] = None,
        on_window_closed_fn: Callable[[], None] = None,
    ):
        PromptManager.post_simple_prompt(
            title,
            message,
            ok_button_info=None if disable_ok_button else PromptButtonInfo(ok_label, ok_handler),
            cancel_button_info=None if disable_cancel_button else PromptButtonInfo(cancel_label, cancel_handler),
            middle_button_info=None if disable_middle_button else PromptButtonInfo(middle_label, middle_handler),
            middle_2_button_info=None
            if disable_middle_2_button
            else PromptButtonInfo(middle_2_label, middle_2_handler),
            modal=True,
            no_title_bar=not bool(title),
            on_window_closed_fn=on_window_closed_fn,
        )
