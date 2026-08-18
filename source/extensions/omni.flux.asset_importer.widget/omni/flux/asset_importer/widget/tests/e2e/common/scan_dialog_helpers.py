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

from omni.kit import ui_test
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardInput

from omni.flux.asset_importer.widget.scan_folder.dialog import destroy_scanner_dialog


async def replace_field_text(field, value: str, end_key: KeyboardInput | None = None) -> None:
    """Replace a visible text field through keyboard input.

    Args:
        field: UI-test reference to the visible field.
        value: Complete replacement value.
        end_key: Optional key sent after the replacement text.
    """
    await field.click()
    await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
    if end_key is None:
        await field.input(value)
    else:
        await field.input(value, end_key=end_key)
    await ui_test.human_delay()


async def destroy_scan_dialog_owner(owner, window) -> None:
    """Destroy the widget that owns the process-global scan dialog and flush UI teardown."""
    try:
        if owner:
            owner.destroy()
    finally:
        try:
            destroy_scanner_dialog()
        finally:
            try:
                if window:
                    window.destroy()
            finally:
                await ui_test.human_delay()


async def ensure_scan_dialog_input_folder(input_folder_field, base_path) -> None:
    """Populate the scan dialog's editable directory field through visible UI input.

    Args:
        input_folder_field: Scan dialog field populated by the directory picker.
        base_path: Directory the test requested from the picker.
    """
    expected_path = str(base_path)
    expected_path_normalized = expected_path.replace("\\", "/").rstrip("/").lower()
    await replace_field_text(input_folder_field, expected_path, KeyboardInput.ENTER)
    selected_path = input_folder_field.model.get_value_as_string().replace("\\", "/").rstrip("/").lower()
    if selected_path != expected_path_normalized:
        raise AssertionError(f"Scan dialog contains {selected_path!r}; expected {expected_path_normalized!r}")
