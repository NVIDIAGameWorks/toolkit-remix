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

from typing import Any
from unittest.mock import MagicMock, patch

from omni.kit.test import AsyncTestCase
from pxr import Gf, Sdf, Usd

from omni.flux.properties_pane.properties.usd.widget import setup_ui as _setup_ui
from omni.flux.properties_pane.properties.usd.widget.setup_ui import PropertyWidget


class TestPropertyWidget(AsyncTestCase):
    """Test property item construction performed by refresh."""

    @staticmethod
    def __make_widget(
        stage: Usd.Stage, lookup_table: dict[str, dict[str, Any]], optional_attributes=None
    ) -> PropertyWidget:
        widget = PropertyWidget.__new__(PropertyWidget)
        widget._root_frame = MagicMock(visible=True)
        widget._context = MagicMock(get_stage=MagicMock(return_value=stage))
        widget._context_name = ""
        widget._paths = [Sdf.Path("/TestPrim")]
        widget._lookup_table = lookup_table
        widget._specific_attributes = None
        widget._optional_attributes = optional_attributes
        widget._property_model = MagicMock()
        widget._PropertyWidget__usd_listener_instance = MagicMock()
        widget._PropertyWidget__refresh_done = MagicMock()
        return widget

    async def test_refresh_configured_tooltip_names_forwards_to_authored_item(self):
        """Configured channel names should reach authored attribute items."""
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim = stage.DefinePrim("/TestPrim")
        prim.CreateAttribute("clippingRange", Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(1.0, 1000.0))
        widget = self.__make_widget(
            stage,
            {"clippingRange": {"name": "Clipping Range", "tooltip_channel_names": ["Near", "Far"]}},
        )

        # Act
        with patch.object(_setup_ui, "_USDAttributeItem") as item_type:
            widget.refresh()

        # Assert
        self.assertEqual(item_type.call_args.kwargs["tooltip_channel_names"], ["Near", "Far"])

    async def test_refresh_configured_tooltip_names_forwards_to_virtual_item(self):
        """Configured channel names should reach virtual attribute items."""
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        stage.DefinePrim("/TestPrim")
        widget = self.__make_widget(
            stage,
            {"clippingRange": {"name": "Clipping Range", "tooltip_channel_names": ["Near", "Far"]}},
            optional_attributes=[
                (
                    lambda _prim: True,
                    {
                        "token": "clippingRange",
                        "type": Sdf.ValueTypeNames.Float2,
                        "default_value": Gf.Vec2f(1.0, 1000.0),
                    },
                )
            ],
        )

        # Act
        with patch.object(_setup_ui, "_VirtualUSDAttributeItem") as item_type:
            widget.refresh()

        # Assert
        self.assertEqual(item_type.call_args.kwargs["tooltip_channel_names"], ["Near", "Far"])

    async def test_refresh_missing_tooltip_names_forwards_default_to_authored_item(self):
        """Missing channel-name metadata should preserve the item default."""
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim = stage.DefinePrim("/TestPrim")
        prim.CreateAttribute("clippingRange", Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(1.0, 1000.0))
        widget = self.__make_widget(stage, {"clippingRange": {"name": "Clipping Range"}})

        # Act
        with patch.object(_setup_ui, "_USDAttributeItem") as item_type:
            widget.refresh()

        # Assert
        self.assertIsNone(item_type.call_args.kwargs["tooltip_channel_names"])
