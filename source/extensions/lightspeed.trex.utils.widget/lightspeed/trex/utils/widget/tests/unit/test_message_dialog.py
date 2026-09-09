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

import asyncio
from unittest.mock import patch

from lightspeed.trex.utils.widget import MessageDialogResult, TrexMessageDialog
from lightspeed.trex.utils.widget import message_dialog as _message_dialog
from omni.kit.test import AsyncTestCase


class TestMessageDialog(AsyncTestCase):
    """Test awaitable message-dialog decisions."""

    async def test_prompt_async_middle_2_selection_returns_middle_2(self):
        """Selecting the second middle button resolves its distinct result."""

        # Arrange
        def prompt_button_info(label, handler):
            return label, handler

        with (
            patch.object(_message_dialog, "PromptButtonInfo", side_effect=prompt_button_info),
            patch.object(_message_dialog.PromptManager, "post_simple_prompt") as post_prompt,
        ):
            prompt_task = asyncio.create_task(
                TrexMessageDialog.prompt_async(
                    "Save changes?",
                    ok_label="Save",
                    middle_label="Save As",
                    middle_2_label="Discard",
                )
            )
            await asyncio.sleep(0)
            middle_2_handler = post_prompt.call_args.kwargs["middle_2_button_info"][1]

            # Act
            middle_2_handler()
            result = await prompt_task

        # Assert
        self.assertEqual(MessageDialogResult.MIDDLE_2, result)

    async def test_prompt_async_window_close_returns_cancel(self):
        """Closing the prompt without choosing a button resolves as cancellation."""

        # Arrange
        def prompt_button_info(label, handler):
            return label, handler

        with (
            patch.object(_message_dialog, "PromptButtonInfo", side_effect=prompt_button_info),
            patch.object(_message_dialog.PromptManager, "post_simple_prompt") as post_prompt,
        ):
            prompt_task = asyncio.create_task(TrexMessageDialog.prompt_async("Continue?"))
            await asyncio.sleep(0)
            close_handler = post_prompt.call_args.kwargs["on_window_closed_fn"]

            # Act
            close_handler()
            result = await prompt_task

        # Assert
        self.assertEqual(MessageDialogResult.CANCEL, result)
