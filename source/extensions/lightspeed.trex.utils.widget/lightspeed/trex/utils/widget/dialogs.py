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

__all__ = ["confirm_delete_prims", "confirm_remove_prim_overrides"]

from collections.abc import Callable
from functools import partial

import omni.kit.commands
import omni.kit.undo
from lightspeed.trex.asset_replacements.core.shared import Setup
from lightspeed.trex.utils.widget.message_dialog import TrexMessageDialog
from omni.flux.utils.common.path_utils import elide_path
from pxr import Sdf


MAX_PATH_CHAR_LENGTH = 45


def confirm_remove_prim_overrides(prim_paths: list[str | Sdf.Path], context: str = "") -> None:
    """
    Wraps the remove prim overrides operation in a confirmation message dialog.

    This function presents a user-friendly message box to confirm the removal of prim overrides
    before executing the operation. The removal operation is wrapped in an undo group, making
    it undoable if the user confirms the action.

    Args:
        prim_paths: List of prim paths (as strings or Sdf.Path objects) to remove overrides from
        context: Optional context string for the Setup instance
    """
    if not prim_paths:
        return

    lines = [
        "Are you sure that you want to reset these assets?\n\n",
        "Doing this will delete all your override(s):\n",
        "    -  Reference override(s)\n",
        "    -  Material override(s)\n",
        "    -  Transform\n",
        "    -  etc.",
    ]

    if len(prim_paths) == 1:
        lines[0] = "Are you sure that you want to reset this asset?\n\n"

    core = Setup(context)

    def restore_callback(prim_paths: list[str | Sdf.Path]):
        with omni.kit.undo.group():
            for prim_path in prim_paths:
                core.remove_prim_overrides(prim_path)

    message = "".join(lines)

    TrexMessageDialog(
        title="##restore",
        message=message,
        ok_handler=partial(restore_callback, prim_paths),
        ok_label="Reset",
        cancel_label="Cancel",
    )


def confirm_delete_prims(
    prim_paths: list[str | Sdf.Path],
    on_complete: Callable | None = None,
    context: str = "",
) -> None:
    """
    Wraps the delete prims operation in a confirmation message dialog.

    This function presents a user-friendly message box to confirm the deletion of prims
    before executing the operation. The deletion operation is wrapped in an undo group, making
    it undoable if the user confirms the action.

    Args:
        prim_paths: List of prim paths (as strings or Sdf.Path objects) to delete
        on_complete: Optional callback invoked after the deletion is executed
        context: Optional USD context name passed to DeletePrimsCommand
    """
    if not prim_paths:
        return

    path_strings = [str(p) for p in prim_paths]
    message = "Are you sure you want to delete these prims?\n\n"
    if len(prim_paths) == 1:
        message = "Are you sure you want to delete this prim?\n\n"

    for path in path_strings:
        clamp_text = elide_path(path, MAX_PATH_CHAR_LENGTH)
        message += f"- {clamp_text}\n"

    def delete_callback(paths: list[str]):
        with omni.kit.undo.group():
            omni.kit.commands.execute("DeletePrimsCommand", paths=paths, context_name=context)
        if on_complete:
            on_complete()

    TrexMessageDialog(
        title="##delete",
        message=message,
        ok_handler=partial(delete_callback, path_strings),
        ok_label="Delete",
        cancel_label="Cancel",
    )
