"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0

Value model for USDAttributeEditGroupItem.
"""

from omni.flux.property_widget_builder.widget.tree.item_model import ItemValueModel


class EditGroupValueModel(ItemValueModel):
    """Inert value model for edit group outlets.

    Satisfies the delegate's value column interface (override indicators,
    edit subscriptions) without backing a real USD attribute.
    """

    is_overriden = False
    is_default = True

    def __init__(self):
        super().__init__()
        self._read_only = True

    def refresh(self):
        pass

    def get_value(self):
        return ""

    def _get_value_as_string(self) -> str:
        return ""

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
