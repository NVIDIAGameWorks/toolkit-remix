"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0

Name model for USDAttributeEditGroupItem.
"""

from omni.flux.property_widget_builder.widget.tree.item_model import ItemValueModel


class EditGroupNameModel(ItemValueModel):
    """Read-only name model for edit group outlets (static display name + tooltip)."""

    def __init__(self, name: str, tooltip: str = ""):
        super().__init__()
        self._name = name
        self._tooltip = tooltip
        self._read_only = True

    def refresh(self):
        pass

    def get_tool_tip(self) -> str:
        return self._tooltip

    def get_value(self) -> str:
        return self._name

    def _get_value_as_string(self) -> str:
        return self._name

    def _get_value_as_float(self) -> float:
        return 0.0

    def _get_value_as_bool(self) -> bool:
        return False

    def _get_value_as_int(self) -> int:
        return 0

    def _set_value(self, value):
        pass

    def _on_dirty(self):
        pass
