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

import carb
import carb.settings
import omni.kit.menu.utils
import omni.usd

from .session import LockXformSession


class LockXformCore:
    """Core functionality + meta data + state manager for lightspeed.lock_xform extension"""

    def __init__(self):
        self._enabled = True
        self._add_toggle_to_edit_menu()
        self._sessions = {}
        # Create stage event subscriptions so we know when to manage sessions
        self._stage_event = (
            omni.usd.get_context()
            .get_stage_event_stream()
            .create_subscription_to_pop(self._on_stage_event, name="[lightspeed.lock_xform] Stage Event")
        )
        self._reason_for_lock = carb.settings.get_settings().get_as_string(
            "/exts/lightspeed.lock_xform/reason_for_lock"
        )
        # Retrieve prim filter setting
        self._prim_filter = carb.settings.get_settings().get_as_string("/exts/lightspeed.lock_xform/prim_filter")

    def unsubscribe_from_events(self):
        self._stage_event.unsubscribe()

    def _on_stage_event(self, event):
        usd_context = omni.usd.get_context()
        if event.type == int(omni.usd.StageEventType.OPENED):
            # On stage open, create new session
            stage = usd_context.get_stage()
            self._sessions[usd_context.get_stage_id()] = LockXformSession(
                usd_context.get_stage_id(), stage, self._display_dialog
            )
        elif event.type == int(omni.usd.StageEventType.CLOSED):
            # On stage close, delete session
            if usd_context.get_stage_id() in self._sessions:
                del self._sessions[usd_context.get_stage_id()]
        elif event.type == int(omni.usd.StageEventType.SELECTION_CHANGED):
            # On prim selection, cache the transform attributes that we want to lock
            stage = usd_context.get_stage()
            selected_prim_paths = usd_context.get_selection().get_selected_prim_paths()
            if self._prim_filter == "":
                self._sessions[usd_context.get_stage_id()].lock_prims(stage, selected_prim_paths)
            else:
                # Filter based on prim names
                filtered_prim_paths = []
                for selected_prim_path in selected_prim_paths:
                    if self._prim_filter in selected_prim_path:
                        filtered_prim_paths.append(selected_prim_path)
                self._sessions[usd_context.get_stage_id()].lock_prims(stage, filtered_prim_paths)

    def _add_toggle_to_edit_menu(self):
        self._tools_manager_menus = [
            omni.kit.menu.utils.MenuItemDescription(name=""),  # Create divider
            omni.kit.menu.utils.MenuItemDescription(
                name="Xform Lock",
                glyph="none.svg",
                enabled=True,
                onclick_fn=self._toggle_enablement,
                ticked_fn=self._ticked_menu_eval,
            ),
        ]
        omni.kit.menu.utils.add_menu_items(self._tools_manager_menus, "Edit")

    def _toggle_enablement(self):
        self._enabled = not self._enabled
        for _, session in self._sessions.items():
            session.set_enablement(self._enabled)

    def _ticked_menu_eval(self):
        return self._enabled

    def _display_dialog(self):
        def _hide_dialog(d):
            d.hide()

        # Title
        title = "[lightspeed.lock_xform]"
        # First message chunk
        common_msg = "We noticed you tried to modify a locked transform."
        # If a reason has been specified by an extension or Kit app, indicate here
        reason_msg = '\n\nReason for lock: "' + self._reason_for_lock + '"' if (self._reason_for_lock != "") else ""
        # If a prim filter has been specified by an extension or Kit app, indicate here
        prim_filter_msg = '\n\nFilter found: "' + self._prim_filter + '"' if (self._prim_filter != "") else ""
        # Inform how to disable
        disable_msg = "\n\nYou can disable this functionality in the menu: (Edit) -> (Xform Lock)."
        # Inform this will only appear once per session
        display_once_msg = "\n\n" + "!! This message will not display again, except on new stage !!"

        msg = common_msg + reason_msg + prim_filter_msg + disable_msg + display_once_msg
        dialog = omni.kit.window.popup_dialog.MessageDialog(
            title=title, message=msg, disable_cancel_button=True, ok_handler=_hide_dialog
        )
        dialog.show()
