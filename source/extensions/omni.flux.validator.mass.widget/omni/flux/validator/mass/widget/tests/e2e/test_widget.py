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

import os
from unittest.mock import PropertyMock, patch

import omni.ui as ui
from omni.flux.validator.mass.widget import ValidatorMassWidget as _ValidatorMassWidget
from omni.kit import ui_test
from omni.kit.test.async_unittest import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path

from .fake_plugins import register_fake_plugins as _register_fake_plugins
from .fake_plugins import unregister_fake_plugins as _unregister_fake_plugins


class TestMassWidget(AsyncTestCase):
    # Before running each test

    SCHEMAS = [
        get_test_data_path(__name__, "schemas/good_material_ingestion.json"),
        get_test_data_path(__name__, "schemas/good_model_ingestion.json"),
    ]

    async def setUp(self):
        _register_fake_plugins()
        await arrange_windows()

    # After running each test
    async def tearDown(self):
        _unregister_fake_plugins()

    async def __setup_widget(self, name: str):
        window = ui.Window(f"TestMassValidationUI{name}", height=800, width=1000)
        with window.frame:
            wid = _ValidatorMassWidget(schema_paths=self.SCHEMAS, use_global_style=False)

        await ui_test.human_delay(human_delay_speed=1)

        return window, wid

    async def __destroy_setup(self, window, wid):
        await ui_test.human_delay(human_delay_speed=1)
        wid.destroy()
        window.frame.clear()
        window.destroy()
        #
        await ui_test.human_delay(human_delay_speed=1)

    async def test_expose_mass_ui(self):
        # setup
        window, _wid = await self.__setup_widget("test_expose_mass_ui")  # Keep in memory during test

        # grab the buttons
        context_buttons = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='FakeContextMassBuildUI'")
        selector_buttons = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='FakeSelectorMassBuildUI'")
        check_buttons = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='FakeCheckMassBuildUI'")

        self.assertEqual(len(context_buttons), 3)
        self.assertEqual(len(selector_buttons), 1)
        self.assertEqual(len(check_buttons), 2)

        await self.__destroy_setup(window, _wid)

    async def test_add_to_queue(self):
        # setup
        window, _wid = await self.__setup_widget("test_add_to_queue")  # Keep in memory during test

        # grab the buttons
        add_to_queue_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='AddToQueue'")

        self.assertIsNotNone(add_to_queue_button)

        # click on it
        await add_to_queue_button.click()

        # we should have 3 job labels, 3 context action buttons, 3 check action buttons
        job_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='QueueJobLabel'")
        action_context_buttons = ui_test.find_all(
            f"{window.title}//Frame/**/Button[*].identifier=='FakeContextMassActionUI'"
        )
        action_check_buttons = ui_test.find_all(
            f"{window.title}//Frame/**/Button[*].identifier=='FakeCheckMassActionUI'"
        )
        self.assertEqual(len(job_labels), 3)
        self.assertEqual(len(action_context_buttons), 3)
        self.assertEqual(len(action_check_buttons), 3)

        await self.__destroy_setup(window, _wid)

    async def test_toggle_validation_widget(self):
        # setup
        window, _wid = await self.__setup_widget("test_toggle_validation_widget")  # Keep in memory during test

        # grab the buttons
        add_to_queue_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='AddToQueue'")

        self.assertIsNotNone(add_to_queue_button)

        # click on it
        await add_to_queue_button.click()

        # we should have 3 job labels, 3 context action buttons, 3 check action buttons
        toggle_in_validation_tab = ui_test.find_all(
            f"{window.title}//Frame/**/ToolButton[*].identifier=='ToggleInValidationTab'"
        )
        self.assertEqual(len(toggle_in_validation_tab), 3)

        # click on the first one
        validation_frame = ui_test.find(f"{window.title}//Frame/**/Frame[*].identifier=='ValidationWidgetFrame'")
        self.assertFalse(validation_frame.widget.visible)

        await toggle_in_validation_tab[0].click()
        self.assertTrue(validation_frame.widget.visible)
        await toggle_in_validation_tab[0].click()
        self.assertFalse(validation_frame.widget.visible)
        await toggle_in_validation_tab[0].click()
        self.assertTrue(validation_frame.widget.visible)
        await toggle_in_validation_tab[1].click()
        self.assertTrue(validation_frame.widget.visible)
        await toggle_in_validation_tab[1].click()
        self.assertFalse(validation_frame.widget.visible)

        await self.__destroy_setup(window, _wid)

    async def test_remove_from_queue(self):
        # setup
        window, _wid = await self.__setup_widget("test_remove_from_queue")  # Keep in memory during test

        # grab the buttons
        add_to_queue_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='AddToQueue'")

        self.assertIsNotNone(add_to_queue_button)

        # click on it
        await add_to_queue_button.click()

        job_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='QueueJobLabel'")
        await job_labels[0].click()

        remove_job_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='RemoveSelection'")
        await remove_job_button.click()

        job_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='QueueJobLabel'")
        self.assertEqual(len(job_labels), 2)

        await self.__destroy_setup(window, _wid)

    async def test_run_should_crash(self):
        # setup
        window, _wid = await self.__setup_widget("test_run_should_crash")  # Keep in memory during test

        # grab the buttons
        add_to_queue_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='AddToQueue'")

        self.assertIsNotNone(add_to_queue_button)

        items = _wid.core.schema_model.get_item_children(None)

        with patch.object(
            items[0].model.model.check_plugins[0].data.Config, "validate_assignment", new_callable=PropertyMock
        ) as mock:
            mock.return_value = False
            items[0].model.model.check_plugins[0].data.fake_data = "Crash"

        # click on it
        await add_to_queue_button.click()

        modal_button = ui_test.find("An Error Occurred//Frame/**/Button[*].text=='Okay'")
        self.assertIsNotNone(modal_button)

        await modal_button.click()

        await self.__destroy_setup(window, _wid)

    async def test_update_context_after_cooking(self):
        # setup
        window, _wid = await self.__setup_widget("test_update_context_after_cooking")  # Keep in memory during test

        # grab the buttons
        add_to_queue_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='AddToQueue'")

        self.assertIsNotNone(add_to_queue_button)

        # click on it
        await add_to_queue_button.click()

        # we should have 3 job labels, 3 context action buttons, 3 check action buttons
        job_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='QueueJobLabel'")
        self.assertEqual(len(job_labels), 3)

        # Remove Job #1
        remove_buttons = ui_test.find_all(f"{window.title}//Frame/**/Button[*].identifier=='RemoveContextItemMassUI'")
        self.assertEqual(len(remove_buttons), 6)
        await remove_buttons[0].click()

        # Remove Job #3
        remove_buttons = ui_test.find_all(f"{window.title}//Frame/**/Button[*].identifier=='RemoveContextItemMassUI'")
        self.assertEqual(len(remove_buttons), 5)
        await remove_buttons[1].click()

        # Should only add Job #2
        await add_to_queue_button.click()

        job_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='QueueJobLabel'")
        self.assertEqual(len(job_labels), 4)

        await self.__destroy_setup(window, _wid)

    async def test_add_no_cooked_template_should_have_no_item_in_queue(self):
        # setup
        window = ui.Window("TestMassValidationUI_add_no_cooked_template", height=800, width=800)
        with window.frame:
            _wid = _ValidatorMassWidget(schema_paths=[], use_global_style=False)

        await ui_test.human_delay(human_delay_speed=1)

        # grab the buttons
        add_to_queue_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='AddToQueue'")

        # by default if there is no template, there is no queue!
        self.assertIsNone(add_to_queue_button)

        await self.__destroy_setup(window, _wid)

    async def test_add_cooked_template_failed_should_have_no_item_in_queue(self):
        # setup
        window = ui.Window("TestMassValidationUI_add_cooked_template_failed", height=800, width=800)
        with window.frame:
            _wid = _ValidatorMassWidget(
                schema_paths=[get_test_data_path(__name__, "schemas/fail_cook_template.json")], use_global_style=False
            )

        await ui_test.human_delay(human_delay_speed=1)

        # grab the buttons
        add_to_queue_button = ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='AddToQueue'")

        self.assertIsNotNone(add_to_queue_button)

        # click on it
        await add_to_queue_button.click()

        modal_button = ui_test.find("An Error Occurred//Frame/**/Button[*].text=='Okay'")
        self.assertIsNotNone(modal_button)
        await modal_button.click()

        job_labels = ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='QueueJobLabel'")
        action_context_buttons = ui_test.find_all(
            f"{window.title}//Frame/**/Button[*].identifier=='FakeContextMassActionUI'"
        )
        action_check_buttons = ui_test.find_all(
            f"{window.title}//Frame/**/Button[*].identifier=='FakeCheckMassActionUI'"
        )
        self.assertEqual(len(job_labels), 0)
        self.assertEqual(len(action_context_buttons), 0)
        self.assertEqual(len(action_check_buttons), 0)

        await self.__destroy_setup(window, _wid)

    async def test_adjust_processor_count(self):
        # setup
        window, _wid = await self.__setup_widget("test_add_to_queue")  # Keep in memory during test

        # grab the combo boxes
        executors_cb = ui_test.find(f"{window.title}//Frame/**/ComboBox[*].identifier=='executors_combo_box'")
        processors_cb = ui_test.find(
            f"{window.title}//Frame/**/ComboBox[*].identifier=='external_processors_count_combo_box'"
        )
        self.assertIsNotNone(executors_cb)
        self.assertIsNotNone(processors_cb)

        # make sure the processor count combo box has the expected amount of cores
        self.assertEqual(len(processors_cb.widget.model.get_item_children()), os.cpu_count())

        # select a different processor count
        await processors_cb.click()
        await ui_test.emulate_mouse_move_and_click(processors_cb.position + ui_test.Vec2(30, 95))
        await ui_test.human_delay()
        self.assertNotEqual(processors_cb.model.get_item_value_model().get_value_as_int() + 1, 1)

        # switch to current process executor
        await executors_cb.click()
        await ui_test.emulate_mouse_move_and_click(executors_cb.position + ui_test.Vec2(30, 25))
        await ui_test.human_delay()

        # ensure the combo box for the process count is no longer visible
        processors_cb = ui_test.find(
            f"{window.title}//Frame/**/ComboBox[*].identifier=='external_processors_count_combo_box'"
        )
        self.assertIsNone(processors_cb)

        # switch back to process executor
        await executors_cb.click()
        await ui_test.emulate_mouse_move_and_click(executors_cb.position + ui_test.Vec2(30, 45))
        await ui_test.human_delay()

        # ensure the box for the process count is visible again
        processors_cb = ui_test.find(
            f"{window.title}//Frame/**/ComboBox[*].identifier=='external_processors_count_combo_box'"
        )
        self.assertIsNotNone(processors_cb)

        # select a different processor count
        await processors_cb.click()
        await ui_test.emulate_mouse_move_and_click(processors_cb.position + ui_test.Vec2(30, 135))
        await ui_test.human_delay()
        self.assertNotEqual(processors_cb.model.get_item_value_model().get_value_as_int() + 1, 1)

        await self.__destroy_setup(window, _wid)

    async def test_add_failed_mass_template_cook_should_have_no_item_in_queue(self):
        pass
