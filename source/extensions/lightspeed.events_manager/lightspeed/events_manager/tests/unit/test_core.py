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

from unittest.mock import Mock, call, patch

import carb
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.events_manager import get_instance as _get_instance
from lightspeed.events_manager.core import EventsManagerCore as _EventsManagerCore
from omni.kit.test import AsyncTestCase


class _FakeEvent(_ILSSEvent):
    @property
    def name(self) -> str:
        """Name of the event"""
        return "FakeTestEvent"

    def _install(self):
        """Function that will create the behavior"""
        pass

    def _uninstall(self):
        """Function that will delete the behavior"""
        pass


class _FakeEvent2(_ILSSEvent):
    @property
    def name(self) -> str:
        """Name of the event"""
        return "FakeTestEvent2"

    def _install(self):
        """Function that will create the behavior"""
        pass

    def _uninstall(self):
        """Function that will delete the behavior"""
        pass


class TestCore(AsyncTestCase):
    async def setUp(self):
        pass

    async def tearDown(self):
        pass

    async def __register_global_events(self, core, show_warning=False):
        core.register_global_custom_event("testEvent01", show_warning=show_warning)
        core.register_global_custom_event("testEvent02", show_warning=show_warning)
        core.register_global_custom_event("testEvent03", show_warning=show_warning)

    async def test_register_global_events(self):
        mock = Mock()
        core = _EventsManagerCore()
        _ = core.subscribe_global_custom_event_register(mock)

        await self.__register_global_events(core)
        self.assertEqual(len(core.get_registered_global_event_names()), 3)
        self.assertTrue(mock.called)
        self.assertEqual(mock.call_args_list, [call("testEvent01"), call("testEvent02"), call("testEvent03")])

        # register same events
        with patch.object(carb, "log_warn") as mock_warn:
            await self.__register_global_events(core, show_warning=True)
            self.assertTrue(mock_warn.called)

    async def test_unregister_global_events(self):
        mock = Mock()
        core = _EventsManagerCore()
        _ = core.subscribe_global_custom_event_unregister(mock)
        await self.__register_global_events(core)
        core.unregister_global_custom_event("testEvent02")
        self.assertEqual(len(core.get_registered_global_event_names()), 2)
        self.assertTrue(mock.called)
        self.assertEqual(mock.call_args_list, [call("testEvent02")])

    async def test_unregister_global_events_dont_exist(self):
        mock = Mock()
        core = _EventsManagerCore()
        _ = core.subscribe_global_custom_event_unregister(mock)
        await self.__register_global_events(core)
        core.unregister_global_custom_event("hello")
        self.assertEqual(len(core.get_registered_global_event_names()), 3)
        self.assertFalse(mock.called)

    async def test_subscribe_global_events(self):
        core = _EventsManagerCore()
        await self.__register_global_events(core)
        mock01 = Mock()
        mock02 = Mock()
        _1 = core.subscribe_global_custom_event("testEvent01", mock01)
        _2 = core.subscribe_global_custom_event("testEvent02", mock02)

        core.call_global_custom_event("testEvent01", "1", "2", hello=3)
        self.assertTrue(mock01.called)
        self.assertEqual(mock01.call_args, call("1", "2", hello=3))
        core.call_global_custom_event("testEvent02", "1", "2", hello=3)
        self.assertTrue(mock02.called)
        self.assertEqual(mock02.call_args, call("1", "2", hello=3))

    async def test_subscribe_global_events_dont_exist(self):
        core = _EventsManagerCore()
        await self.__register_global_events(core)
        mock01 = Mock()
        with self.assertRaises(ValueError), patch.object(carb, "log_error") as mock_error:
            _ = core.subscribe_global_custom_event("123456789", mock01)
            self.assertFalse(mock01.called)
            self.assertTrue(mock_error.called)

    async def test_call_global_events_dont_exist(self):
        core = _EventsManagerCore()
        await self.__register_global_events(core)
        mock01 = Mock()
        with self.assertRaises(ValueError), patch.object(carb, "log_error") as mock_error:
            core.call_global_custom_event("123456789", "1", "2", hello=3)
            self.assertFalse(mock01.called)
            self.assertTrue(mock_error.called)

    async def __register_events(self, core, events):
        for event in events:
            core.register_event(event)

    async def test_register_events(self):
        mock = Mock()
        core = _EventsManagerCore()
        _ = core.subscribe_event_registered(mock)

        e1 = _FakeEvent()
        e2 = _FakeEvent2()
        await self.__register_events(core, [e1, e2])
        self.assertEqual(len(core.get_registered_events()), 2)
        self.assertTrue(mock.called)
        self.assertEqual(mock.call_args_list, [call(e1), call(e2)])

        # test register the same event which is ok
        await self.__register_events(core, [e1, e2])
        self.assertEqual(mock.call_args_list, [call(e1), call(e2), call(e1), call(e2)])

    async def test_get_registered_event(self):
        mock = Mock()
        core = _EventsManagerCore()
        _ = core.subscribe_event_registered(mock)

        e1 = _FakeEvent()
        e2 = _FakeEvent2()
        await self.__register_events(core, [e1, e2])
        self.assertEqual(len(core.get_registered_events()), 2)
        self.assertTrue(mock.called)
        self.assertEqual(mock.call_args_list, [call(e1), call(e2)])

        self.assertIsNone(core.get_registered_event("123456789"))
        self.assertEqual(core.get_registered_event("FakeTestEvent2"), e2)

    async def test_unregister_events(self):
        mock = Mock()
        core = _EventsManagerCore()
        _ = core.subscribe_event_unregistered(mock)

        e1 = _FakeEvent()
        e2 = _FakeEvent2()
        await self.__register_events(core, [e1, e2])
        core.unregister_event(e1)
        self.assertEqual(len(core.get_registered_events()), 1)
        self.assertTrue(mock.called)
        self.assertEqual(mock.call_args, call(e1))

    async def test_unregister_events_doesnt_exist(self):
        mock = Mock()
        core = _EventsManagerCore()
        _ = core.subscribe_event_unregistered(mock)

        e1 = _FakeEvent()
        e2 = _FakeEvent2()
        e3 = _FakeEvent2()
        await self.__register_events(core, [e1, e2])
        with patch.object(carb, "log_warn") as mock_warn:
            core.unregister_event(e3)
            self.assertEqual(len(core.get_registered_events()), 2)
            self.assertFalse(mock.called)
            self.assertTrue(mock_warn.called)

    async def test_destroy(self):
        core = _EventsManagerCore()
        await self.__register_global_events(core)
        e1 = _FakeEvent()
        e2 = _FakeEvent2()
        await self.__register_events(core, [e1, e2])

        core.destroy()

        self.assertFalse(core.get_registered_global_event_names())
        self.assertFalse(core.get_registered_events())

    async def test_get_instance(self):
        inst = _get_instance()

        self.assertIsNotNone(inst)
