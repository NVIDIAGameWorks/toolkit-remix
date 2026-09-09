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
from collections.abc import Callable
from pathlib import Path

import omni.kit.app
from omni.flux.utils.common.path_utils import open_file_using_os_default

from .message_dialog import MessageDialogResult as _MessageDialogResult
from .message_dialog import TrexMessageDialog as _TrexMessageDialog


async def confirm_invalid_deps_rebuild(deps_directory: Path) -> bool:
    """Ask whether an invalid dependencies directory should be rebuilt."""
    result = await _TrexMessageDialog.prompt_async(
        title="Invalid Project Dependencies",
        message=(
            'The "deps" folder in this project is not a valid symlink and must be rebuilt before the '
            "project can finish opening.\n\n"
            'The existing "deps" folder will be deleted and all contents will be lost.\n\n'
            'Select "Reveal in Explorer" to inspect it, or select "Rebuild" to choose an RTX Remix directory '
            'and rebuild "deps".'
        ),
        ok_label="Rebuild",
        middle_label="Reveal in Explorer",
    )
    if result == _MessageDialogResult.MIDDLE:
        open_file_using_os_default(str(deps_directory), highlight=True)
        return False
    if result != _MessageDialogResult.OK:
        return False

    # Let the prompt close before centering the wizard in the settled window.
    await omni.kit.app.get_app().next_update_async()
    return True


def show_invalid_deps_rebuild_dialog(deps_directory: Path, rebuild_handler: Callable[[], None]):
    """Show the legacy callback-based invalid dependencies prompt."""

    async def confirm_rebuild():
        if await confirm_invalid_deps_rebuild(deps_directory):
            rebuild_handler()

    asyncio.ensure_future(confirm_rebuild())
