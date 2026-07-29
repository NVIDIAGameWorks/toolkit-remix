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
from contextlib import asynccontextmanager

import omni.ui as ui
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardInput
from lightspeed.common.constants import INGESTION_SCHEMAS
from omni.flux.utils.common.os_drop_router import WidgetDropRouter
from omni.flux.validator.mass.widget import ValidatorMassWidget
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows


class TestMassIngestion(AsyncTestCase):
    """Exercise the production ingestion schemas through the mass-ingestion UI."""

    async def setUp(self):
        """Arrange Kit windows before each workflow."""
        await arrange_windows()

    async def _wait_for_widgets(self, query: str, count: int):
        """Wait for asynchronously built widget content to reach an expected count."""
        widgets = []
        for _ in range(600):
            widgets = ui_test.find_all(query)
            if len(widgets) == count:
                return widgets
            await ui_test.human_delay()
        self.fail(f"Expected {count} widgets for {query!r}, found {len(widgets)}.")
        return widgets

    @asynccontextmanager
    async def _setup_widget(self, name: str):
        """Create a mass widget backed by the production ingestion schemas.

        Args:
            name: Unique suffix for the test window title.

        Yields:
            The window and mass widget under test.
        """
        window = ui.Window(f"TestMassIngestion_{name}", height=900, width=1100)
        with window.frame:
            widget = ValidatorMassWidget(
                schema_paths=[schema["path"] for schema in INGESTION_SCHEMAS],
                use_global_style=False,
            )

        await ui_test.human_delay(human_delay_speed=1)
        try:
            yield window, widget
        finally:
            widget.destroy()
            window.frame.clear()
            window.destroy()
            await ui_test.human_delay(human_delay_speed=1)

    async def test_edit_shared_conversion_limit_in_each_ingestion_tab_updates_both_converters(self):
        """Editing each shared field updates both converter schemas."""
        async with self._setup_widget("shared_conversion_limit") as (window, widget):
            items = widget.core.schema_model.get_item_children(None)
            tab_labels = ui_test.find_all(f"{window.title}//Frame/**/VStack[*].identifier=='TabLabel'")
            shared_fields = await self._wait_for_widgets(
                f"{window.title}//Frame/**/IntField[*].identifier=='MaxConcurrentTextureConversionsField'",
                2,
            )
            shared_labels = ui_test.find_all(
                f"{window.title}//Frame/**/Label[*].text=='Max Concurrent Texture Conversions'"
            )
            converter_fields = ui_test.find_all(f"{window.title}//Frame/**/IntField[*].identifier=='MaxWorkersField'")

            self.assertEqual(["Model(s)", "Material(s)"], [item.title for item in items])
            self.assertEqual(2, len(tab_labels))
            self.assertEqual(2, len(shared_fields))
            self.assertEqual(2, len(shared_labels))
            self.assertEqual(0, len(converter_fields))
            self.assertTrue(all(len(item.shared_int_fields) == 1 for item in items))

            for index, item in enumerate(items):
                with self.subTest(schema=item.title):
                    if index:
                        await tab_labels[index].click()
                        await ui_test.human_delay()

                    await shared_fields[index].click()
                    await ui_test.human_delay()
                    await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
                    await ui_test.human_delay()
                    await ui_test.emulate_keyboard_press(KeyboardInput.DEL)
                    await ui_test.human_delay()
                    await shared_fields[index].input("3", end_key=KeyboardInput.ENTER)
                    await ui_test.human_delay()

                    target_plugins = {
                        plugin.name: plugin.data
                        for plugin in item.model.model.check_plugins
                        if plugin.name in {"ConvertToDDS", "ConvertToOctahedral"}
                    }
                    self.assertEqual({"ConvertToDDS", "ConvertToOctahedral"}, set(target_plugins))
                    self.assertEqual(3, shared_fields[index].widget.model.get_value_as_int())
                    self.assertTrue(all(plugin.max_workers == 3 for plugin in target_plugins.values()))

    async def test_destroy_during_initial_build_stops_pending_build(self):
        """Destroying the production widget stops its active asynchronous UI build."""
        # Arrange
        registered_widgets_before = set(WidgetDropRouter._registered_widgets)
        window = ui.Window("TestMassIngestion_destroy_pending_build", height=900, width=1100)
        widget = None

        try:
            with window.frame:
                widget = ValidatorMassWidget(
                    schema_paths=[schema["path"] for schema in INGESTION_SCHEMAS],
                    use_global_style=False,
                )
            pending_build = widget._build_mass_ui_task
            core = widget.core
            items = core.schema_model.get_item_children(None)
            manager_cores = [item.model for item in items]
            provisional_pages = set()
            for _ in range(60):
                provisional_pages = set(WidgetDropRouter._registered_widgets) - registered_widgets_before
                if provisional_pages:
                    break
                await ui_test.human_delay()

            self.assertTrue(provisional_pages)
            self.assertFalse(pending_build.done())

            # Act
            widget.destroy()

            # Assert
            self.assertIsNone(widget._build_mass_ui_task)
            self.assertIsNone(widget.core)
            self.assertEqual(items, core.schema_model.get_item_children(None))
            self.assertTrue(all(manager_core.model is not None for manager_core in manager_cores))
            build_result = await asyncio.gather(pending_build, return_exceptions=True)
            await ui_test.human_delay()
            self.assertTrue(pending_build.done())
            self.assertTrue(build_result[0] is None or isinstance(build_result[0], asyncio.CancelledError))
            self.assertTrue(all(manager_core.model is None for manager_core in manager_cores))
            self.assertEqual([], core.schema_model.get_item_children(None))
            self.assertEqual([], core.schema_model._Model__subs_mass_cook_template)
            self.assertEqual(registered_widgets_before, WidgetDropRouter._registered_widgets)
        finally:
            if widget:
                widget.destroy()
            window.frame.clear()
            window.destroy()
            await ui_test.human_delay(human_delay_speed=1)
