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
from unittest.mock import Mock

import carb.input
import omni.kit.test
import omni.kit.ui_test as ui_test
from lightspeed.trex.contexts.extension import get_instance as get_context_manager
from lightspeed.trex.contexts.setup import Contexts
from lightspeed.trex.hotkeys.app import (
    HotkeyEvent,
    create_global_hotkey_manager,
    destroy_global_hotkey_manager,
    get_global_hotkey_manager,
)
from omni.kit.actions.core import get_action_registry
from omni.kit.hotkeys.core import KeyCombination, get_hotkey_context, get_hotkey_registry


class TestHotkeyEvent(HotkeyEvent):
    CTRL_T = KeyCombination(carb.input.KeyboardInput.T, modifiers=carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
    CTRL_F = KeyCombination(carb.input.KeyboardInput.F, modifiers=carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)


class TestTrigger(omni.kit.test.AsyncTestCase):
    """
    Test different hotkeys in various app contexts.
    """

    async def setUp(self):
        # clear default app registrations
        destroy_global_hotkey_manager()
        create_global_hotkey_manager()

        self._hotkey_registry = get_hotkey_registry()
        self._hotkey_context = get_hotkey_context()
        self._action_registry = get_action_registry()

        # Define Hotkey
        hotkey_manager = get_global_hotkey_manager()
        hotkey_manager.define_hotkey_event(TestHotkeyEvent.CTRL_T, "Test T Hotkey")
        hotkey_manager.define_hotkey_event(TestHotkeyEvent.CTRL_F, "Test F Hotkey")
        self.assertEqual(len(self._hotkey_registry.get_all_hotkeys()), 2)
        self.assertEqual(len(self._action_registry.get_all_actions_for_extension("lightspeed.trex.hotkeys")), 2)

        # Hookup Hotkey
        self._global_hotkey_mock = Mock()
        self._global_hotkey_sub = hotkey_manager.subscribe_hotkey_event(
            TestHotkeyEvent.CTRL_T, self._global_hotkey_mock, context=None, enable_fn=None
        )

        self._stagecraft_context_hotkey_mock = Mock()
        self._stagecraft_hotkey_sub = hotkey_manager.subscribe_hotkey_event(
            TestHotkeyEvent.CTRL_T, self._stagecraft_context_hotkey_mock, context=Contexts.STAGE_CRAFT, enable_fn=None
        )

        self._ingestcraft_context_hotkey_mock = Mock()
        self._ingestcraft_hotkey_sub = hotkey_manager.subscribe_hotkey_event(
            TestHotkeyEvent.CTRL_T, self._ingestcraft_context_hotkey_mock, context=Contexts.INGEST_CRAFT, enable_fn=None
        )

        # Sanity check:
        # All of AppHotkeys currently end up in the "global" hotkey context. So make sure
        # there's no conficting context set here that would block actions.
        self.assertIsNone(self._hotkey_context.get())

    async def tearDown(self):
        destroy_global_hotkey_manager()

    async def test_hotkey_subscriptions_trigger_in_correct_contexts(self):
        trex_context_manager = get_context_manager()
        trex_context_manager.set_current_context("Dummy")

        async def press_ctrl_t():
            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.T, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.human_delay()

        async def press_ctrl_f():
            await ui_test.emulate_keyboard_press(carb.input.KeyboardInput.F, carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
            await ui_test.human_delay()

        # test that global hotkey works
        await press_ctrl_t()
        self.assertEqual(self._global_hotkey_mock.call_count, 1)
        self.assertEqual(self._stagecraft_context_hotkey_mock.call_count, 0)
        self.assertEqual(self._ingestcraft_context_hotkey_mock.call_count, 0)

        # test that it works when a context is set...
        trex_context_manager.set_current_context(Contexts.STAGE_CRAFT)
        await press_ctrl_t()
        self.assertEqual(self._global_hotkey_mock.call_count, 1)
        self.assertEqual(self._stagecraft_context_hotkey_mock.call_count, 1)
        self.assertEqual(self._ingestcraft_context_hotkey_mock.call_count, 0)

        # and when another context is set...
        trex_context_manager.set_current_context(Contexts.INGEST_CRAFT)
        await press_ctrl_t()
        self.assertEqual(self._global_hotkey_mock.call_count, 1)
        self.assertEqual(self._stagecraft_context_hotkey_mock.call_count, 1)
        self.assertEqual(self._ingestcraft_context_hotkey_mock.call_count, 1)

        # make sure nothing is triggered if nothing has subscribed to the HotkeyEvent
        await press_ctrl_f()  # does nothing...
        self.assertEqual(self._global_hotkey_mock.call_count, 1)
        self.assertEqual(self._stagecraft_context_hotkey_mock.call_count, 1)
        self.assertEqual(self._ingestcraft_context_hotkey_mock.call_count, 1)
