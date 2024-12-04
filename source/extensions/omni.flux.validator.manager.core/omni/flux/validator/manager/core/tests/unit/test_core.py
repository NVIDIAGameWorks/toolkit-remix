# noqa PLC0302
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
import asyncio
import sys
from pathlib import Path
from typing import Any, Optional
from unittest.mock import call, patch

import omni.kit.app
from omni.flux.validator.factory import BaseValidatorRunMode as _BaseValidatorRunMode
from omni.flux.validator.factory import ResultorBase as _ResultorBase
from omni.flux.validator.factory import get_instance as _get_factory_instance
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.flux.validator.plugin.check.usd.example.print_prims import PrintPrims as _PrintPrims
from omni.flux.validator.plugin.context.usd_stage.current_stage import CurrentStage as _CurrentStage
from omni.flux.validator.plugin.selector.usd.all_prims import AllPrims as _AllPrims
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import arrange_windows, get_test_data_path, open_stage, wait_stage_loading
from pydantic import ValidationError


class FakeResultor(_ResultorBase):
    class Data(_ResultorBase.Data):
        pass

    name = "FakeResultor"
    tooltip = "FakeResultor"
    data_type = Data

    @omni.usd.handle_exception
    async def _result(self, schema_data: Data, schema):
        """
        Function that will be called to work on the result

        Args:
            schema_data: the data from the schema.
            schema: the whole schema ran by the manager

        Returns: True if ok + message
        """
        return True, "Ok"

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data):
        """
        Build the UI for the plugin
        """
        pass

    @omni.usd.handle_exception
    async def _on_crash(self, schema_data: Any, data: Any) -> None:
        pass


_get_factory_instance().register_plugins([FakeResultor])


def _create_good_schema():
    return _ManagerCore(
        {
            "name": "Test",
            "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
            "check_plugins": [
                {
                    "name": "PrintPrims",
                    "enabled": False,
                    "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    "selector_plugins": [{"name": "AllPrims", "data": {}}],
                    "data": {},
                    "pause_if_fix_failed": False,
                },
                {
                    "name": "PrintPrims",
                    "selector_plugins": [{"name": "AllPrims", "data": {}}],
                    "data": {},
                    "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    "pause_if_fix_failed": False,
                    "resultor_plugins": [{"name": "FakeResultor", "data": {}}, {"name": "FakeResultor", "data": {}}],
                },
                {
                    "name": "PrintPrims",
                    "selector_plugins": [{"name": "AllPrims", "data": {}}],
                    "data": {},
                    "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    "pause_if_fix_failed": False,
                },
            ],
            "resultor_plugins": [{"name": "FakeResultor", "data": {}}, {"name": "FakeResultor", "data": {}}],
        }
    )


class TestCore(AsyncTestCase):
    async def setUp(self):
        await arrange_windows()
        await open_stage(get_test_data_path(__name__, "usd/cubes.usda"))

    # After running each test
    async def tearDown(self):
        await wait_stage_loading()

    async def test_schemas(self):
        # test wrong schemas
        wrong_schemas = [
            {},
            {  # no check plugin
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
            },
            {  # no context plugin
                "name": "Test",
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "enabled": False,
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                ],
            },
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [  # no select plugin
                    {
                        "name": "PrintPrims",
                        "enabled": False,
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                ],
            },
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [  # no select plugin in list
                    {
                        "name": "PrintPrims",
                        "enabled": False,
                        "selector_plugins": [],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                ],
            },
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},  # no check plugins in list
                "check_plugins": [],
            },
            {  # context plugin that doesn't exist
                "name": "Test",
                "context_plugin": {"name": "TestPlugin", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "enabled": False,
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                ],
            },
            {  # check plugin that doesn't exist
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "TestPlugin",
                        "enabled": False,
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                ],
            },
            {  # wrong context data schema
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"bla": ""}},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "enabled": False,
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                ],
            },
            {  # missing context data schema
                "name": "Test",
                "context_plugin": {"name": "CurrentStage"},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "enabled": False,
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    },
                ],
            },
            {  # no sub context
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "enabled": False,
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                    },
                    {"name": "PrintPrims", "selector_plugins": [{"name": "AllPrims", "data": {}}], "data": {}},
                    {"name": "PrintPrims", "selector_plugins": [{"name": "AllPrims", "data": {}}], "data": {}},
                ],
            },
            {  # no check plugin
                "name": "Test",
                "context_plugin": {"name": "CurrentStage"},
                "check_plugins": [],
            },
            {  # no name
                "context_plugin": {"name": "CurrentStage"},
                "check_plugins": [],
            },
            {  # wrong data flow
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {"data_flows": [{"name": "RandomDataflow"}]},
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                    }
                ],
            },
        ]
        for wrong_schema in wrong_schemas:
            with self.assertRaises(ValidationError):
                _ManagerCore(wrong_schema)

    async def test_run_ok(self):
        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        def sub_progress_count_fn(_value):
            nonlocal sub_progress_count
            sub_progress_count.append(_value)

        def sub_started_count_fn():
            """Yes we can mock that. But this is to show an example"""
            nonlocal sub_started_count
            sub_started_count.append(True)

        core = _create_good_schema()

        sub_finished_count = []
        sub_progress_count = []
        sub_started_count = []

        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa
        _sub1 = core.subscribe_run_progress(sub_progress_count_fn)  # noqa
        _sub2 = core.subscribe_run_started(sub_started_count_fn)  # noqa
        # run, it should be ok
        await core.deferred_run()
        self.assertTrue(sub_finished_count[-1])
        self.assertTrue(sub_started_count[-1])
        self.assertEqual([0.0, 50, 62.5, 75.0, 78.125, 81.25, 87.5, 90.625, 93.75, 100], sub_progress_count)

    async def test_send_service_request_called_false(self):
        """Test if _send_service_request is not called when model data does not require it."""
        core = _create_good_schema()

        with patch.object(_ManagerCore, "_send_update_request") as m_mocked:
            await core.deferred_run()
            self.assertFalse(m_mocked.called)

    async def test_send_service_request_called_true(self):
        """Test if _send_service_request is called when model data requires it."""
        core = _create_good_schema()
        core.model.send_request = True

        with patch.object(_ManagerCore, "_send_update_request") as m_mocked:
            await core.deferred_run()
            self.assertTrue(m_mocked.called)

    async def test_run_stopped(self):
        def sub_stopped_count_fn():
            nonlocal sub_stopped_count
            sub_stopped_count.append(True)

        async def _custom_check(*args, **kwargs):
            """We slow down the check 3 frames"""
            for _ in range(3):
                await omni.kit.app.get_app().next_update_async()
            return True, "Ok", []

        async def do_stop(_core):
            """We slow down the stop 2 frame. So it will happen in the middle of the check"""
            for _ in range(2):
                await omni.kit.app.get_app().next_update_async()
            _core.stop()

        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "pause_if_fix_failed": False,
                    },
                ],
            }
        )

        sub_stopped_count = []
        _sub = core.subscribe_run_stopped(sub_stopped_count_fn)  # noqa

        # run, it should be ok
        with self.assertRaises(ValueError), patch.object(_PrintPrims, "_check", wraps=_custom_check):
            asyncio.ensure_future(do_stop(core))
            await core.deferred_run()
        self.assertTrue(sub_stopped_count[-1])

    async def test_run_paused(self):
        def sub_paused_count_fn(_value):
            nonlocal sub_paused_count
            sub_paused_count.append(_value)

        async def do_resume(_core):
            """We slow down the stop 2 frames. So it will happen in the middle of the check"""
            for _ in range(2):
                await omni.kit.app.get_app().next_update_async()
            _core.resume()

        core = _ManagerCore(
            {
                "name": "Test",
                "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                "check_plugins": [
                    {
                        "name": "PrintPrims",
                        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
                        "selector_plugins": [{"name": "AllPrims", "data": {}}],
                        "data": {},
                        "pause_if_fix_failed": True,
                    },
                ],
            }
        )

        sub_paused_count = []
        _sub = core.subscribe_run_paused(sub_paused_count_fn)  # noqa

        # run, it should be ok
        with patch.object(_PrintPrims, "_check") as m_mocked:
            asyncio.ensure_future(do_resume(core))
            v1 = (False, "Bad", ["1", "2", "3"])
            v2 = (False, "Bad", ["1", "2", "3"])
            v3 = (True, "Ok", ["1", "2", "3"])
            if sys.version_info.minor > 7:
                m_mocked.side_effect = [v1, v2, v3]
            else:
                f = asyncio.Future()
                f.set_result(v1)
                f1 = asyncio.Future()
                f1.set_result(v2)
                f2 = asyncio.Future()
                f2.set_result(v3)
                m_mocked.side_effect = [f, f1, f2]

            await core.deferred_run()
        # Because the check crashes, it pauses 1 time. And after we resume by hand.
        self.assertTrue(sub_paused_count == [True, False])

    async def test_run_mode_all(self):
        async def _custom_check(*args, **kwargs):
            return True, "Ok", []

        core = _create_good_schema()

        # run, it should be ok
        with (
            patch.object(
                _ManagerCore,
                "_ManagerCore__set_mode_base_all",
                side_effect=core._ManagerCore__set_mode_base_all,  # noqa
            ) as m_mocked,
            patch.object(_PrintPrims, "_check", wraps=_custom_check) as check_mocked,
        ):
            await core.deferred_run()
            self.assertTrue(m_mocked.call_count == 1)
            self.assertTrue(check_mocked.call_count == 2)

    async def test_run_mode_all_from_plugin(self):
        core = _create_good_schema()

        # run, it should be ok
        with patch.object(_ManagerCore, "run", side_effect=core.run) as m_mocked:
            check_instance = core.model.check_plugins[1].instance
            check_instance._on_validator_run([check_instance], _BaseValidatorRunMode.BASE_ALL)  # noqa
            self.assertTrue(m_mocked.call_count == 1)
            self.assertTrue(
                m_mocked.call_args
                == call(
                    instance_plugins=[check_instance], run_mode=_BaseValidatorRunMode.BASE_ALL, catch_exception=True
                )
            )

    async def test_run_mode_only_selected(self):
        async def _custom_check(*args, **kwargs):
            return True, "Ok", []

        core = _create_good_schema()

        # run, it should be ok
        with (
            patch.object(
                _ManagerCore,
                "_ManagerCore__set_mode_base_only_selected",
                side_effect=core._ManagerCore__set_mode_base_only_selected,  # noqa
            ) as m_mocked,
            patch.object(_PrintPrims, "_check", wraps=_custom_check) as check_mocked,
        ):
            await core.deferred_run(
                run_mode=_BaseValidatorRunMode.BASE_ONLY_SELECTED,
                instance_plugins=[core.model.check_plugins[1].instance],
            )
            self.assertTrue(m_mocked.call_count == 1)
            self.assertTrue(check_mocked.call_count == 1)

    async def test_run_mode_only_selected_from_plugin(self):
        core = _create_good_schema()

        # run, it should be ok
        with patch.object(_ManagerCore, "run", side_effect=core.run) as m_mocked:
            check_instance = core.model.check_plugins[1].instance
            check_instance._on_validator_run([check_instance], _BaseValidatorRunMode.BASE_ONLY_SELECTED)  # noqa
            self.assertTrue(m_mocked.call_count == 1)
            self.assertTrue(
                m_mocked.call_args
                == call(
                    instance_plugins=[check_instance],
                    run_mode=_BaseValidatorRunMode.BASE_ONLY_SELECTED,
                    catch_exception=True,
                )
            )

    async def test_run_mode_self_to_end(self):
        async def _custom_check(*args, **kwargs):
            return True, "Ok", []

        core = _create_good_schema()

        # run, it should be ok
        with (
            patch.object(
                _ManagerCore,
                "_ManagerCore__set_mode_base_self_to_end",
                side_effect=core._ManagerCore__set_mode_base_self_to_end,  # noqa
            ) as m_mocked,
            patch.object(_PrintPrims, "_check", wraps=_custom_check) as check_mocked,
        ):
            await core.deferred_run(
                run_mode=_BaseValidatorRunMode.BASE_SELF_TO_END, instance_plugins=[core.model.check_plugins[1].instance]
            )
            self.assertTrue(m_mocked.call_count == 1)
            self.assertTrue(check_mocked.call_count == 2)

    async def test_run_mode_self_to_end_from_plugin(self):
        core = _create_good_schema()

        # run, it should be ok
        with patch.object(_ManagerCore, "run", side_effect=core.run) as m_mocked:
            check_instance = core.model.check_plugins[1].instance
            check_instance._on_validator_run([check_instance], _BaseValidatorRunMode.BASE_SELF_TO_END)  # noqa
            self.assertTrue(m_mocked.call_count == 1)
            self.assertTrue(
                m_mocked.call_args
                == call(
                    instance_plugins=[check_instance],
                    run_mode=_BaseValidatorRunMode.BASE_SELF_TO_END,
                    catch_exception=True,
                )
            )

        # run, it should be ok
        with patch.object(_ManagerCore, "run", side_effect=core.run) as m_mocked:
            selector_instance = core.model.check_plugins[2].selector_plugins[0].instance
            selector_instance._on_validator_run([selector_instance], _BaseValidatorRunMode.BASE_SELF_TO_END)  # noqa
            self.assertTrue(m_mocked.call_count == 1)
            self.assertTrue(
                m_mocked.call_args
                == call(
                    instance_plugins=[selector_instance],
                    run_mode=_BaseValidatorRunMode.BASE_SELF_TO_END,
                    catch_exception=True,
                )
            )

        # run, it should be ok
        with patch.object(_ManagerCore, "run", side_effect=core.run) as m_mocked:
            context_instance = core.model.check_plugins[2].context_plugin.instance
            context_instance._on_validator_run([context_instance], _BaseValidatorRunMode.BASE_SELF_TO_END)  # noqa
            self.assertTrue(m_mocked.call_count == 1)
            self.assertTrue(
                m_mocked.call_args
                == call(
                    instance_plugins=[context_instance],
                    run_mode=_BaseValidatorRunMode.BASE_SELF_TO_END,
                    catch_exception=True,
                )
            )

        # run, it should crash because we can run only a resultor. We need at least 1 check
        with patch.object(_ManagerCore, "run", side_effect=core.run) as m_mocked:
            resultor_instance = core.model.resultor_plugins[0].instance
            with self.assertRaises(ValueError):
                resultor_instance._on_validator_run(  # noqa
                    [resultor_instance], _BaseValidatorRunMode.BASE_SELF_TO_END, catch_exception=False
                )
                await omni.kit.app.get_app().next_update_async()
                await asyncio.gather(core._last_run_task)  # noqa
            self.assertTrue(m_mocked.call_count == 1)
            self.assertTrue(
                m_mocked.call_args
                == call(
                    instance_plugins=[resultor_instance],
                    run_mode=_BaseValidatorRunMode.BASE_SELF_TO_END,
                    catch_exception=False,
                )
            )

    async def test_disable_run_from_plugin(self):
        async def _custom_check(*args, **kwargs):
            """We slow down the check 3 frames"""
            nonlocal check_count
            check_count.append(True)
            return True, "Ok", []

        check_count = []
        core = _create_good_schema()

        # run, it should be ok
        with patch.object(_PrintPrims, "_check", wraps=_custom_check):
            self.assertTrue(core.is_enabled())
            check_instance = core.model.check_plugins[1].instance
            check_instance._on_validator_enable(False)  # noqa
            self.assertFalse(core.is_enabled())

            await core.deferred_run()
            self.assertTrue(len(check_count) == 0)

            check_instance._on_validator_enable(True)  # noqa
            self.assertTrue(core.is_enabled())
            await core.deferred_run()
            self.assertTrue(len(check_count) == 2)

    async def test_run_fail_plugin_context_disabled(self):
        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa
        # first check plugin is disabled
        self.assertFalse(core.model.check_plugins[0].enabled)

        # disabling the context plugin will set an error
        core.model.context_plugin.enabled = False
        with self.assertRaises(ValueError):
            await core.deferred_run()
        self.assertFalse(sub_finished_count[-1])

        # put it back
        core.model.context_plugin.enabled = True
        await core.deferred_run()
        self.assertTrue(sub_finished_count[-1])

    async def test_run_fail_plugin_selector_disabled(self):
        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa

        # disabling the selector plugin will set an error
        core.model.check_plugins[1].selector_plugins[0].enabled = False
        with self.assertRaises(ValueError):
            await core.deferred_run()
        self.assertFalse(sub_finished_count[-1])
        # put it back
        core.model.check_plugins[1].selector_plugins[0].enabled = True

    async def test_run_fail_plugin_check_disabled(self):
        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa
        # disabling the second and third check will error, because we dont have any check plugin anymore
        core.model.check_plugins[1].enabled = False
        core.model.check_plugins[2].enabled = False
        with self.assertRaises(ValueError):
            await core.deferred_run()
        self.assertFalse(sub_finished_count[-1])
        # put it back
        core.model.check_plugins[1].enabled = True
        core.model.check_plugins[2].enabled = True

        await core.deferred_run()
        self.assertTrue(sub_finished_count[-1])

    async def test_run_fail_plugin_context_check_return_false(self):
        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa

        with patch.object(_CurrentStage, "_check") as m_mocked, patch.object(_CurrentStage, "_on_crash"):
            v1 = (False, "Failed")
            if sys.version_info.minor > 7:
                m_mocked.return_value = v1
            else:
                f = asyncio.Future()
                f.set_result(v1)
                m_mocked.return_value = f

            with self.assertRaises(ValueError):
                await core.deferred_run()
        self.assertFalse(sub_finished_count[-1])

        # put it back
        core.model.context_plugin.enabled = True
        await core.deferred_run()
        self.assertTrue(sub_finished_count[-1])

    async def test_run_fail_plugin_context_set_return_false(self):
        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa

        with patch.object(_CurrentStage, "_setup") as m_mocked, patch.object(_CurrentStage, "_on_crash"):
            v1 = (False, "Failed", None)
            if sys.version_info.minor > 7:
                m_mocked.return_value = v1
            else:
                f = asyncio.Future()
                f.set_result(v1)
                m_mocked.return_value = f

            with self.assertRaises(ValueError):
                await core.deferred_run()
            self.assertEqual(1, m_mocked.call_count)
        self.assertFalse(sub_finished_count[-1])

        # put it back
        await core.deferred_run()
        self.assertTrue(sub_finished_count[-1])

    async def test_run_fail_plugin_context_exit_return_false(self):
        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa

        with patch.object(_CurrentStage, "_on_exit") as m_mocked, patch.object(_CurrentStage, "_on_crash"):
            v1 = (False, "Failed")
            if sys.version_info.minor > 7:
                m_mocked.return_value = v1
            else:
                f = asyncio.Future()
                f.set_result(v1)
                m_mocked.return_value = f

            with self.assertRaises(ValueError):
                await core.deferred_run()
            self.assertEqual(1, m_mocked.call_count)
        self.assertFalse(sub_finished_count[-1])

        # put it back
        await core.deferred_run()
        self.assertTrue(sub_finished_count[-1])

    async def test_run_fail_plugin_select_select_return_false(self):
        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa

        with patch.object(_AllPrims, "_select") as m_mocked, patch.object(_AllPrims, "_on_crash"):
            v1 = (False, "Failed", None)
            if sys.version_info.minor > 7:
                m_mocked.return_value = v1
            else:
                f = asyncio.Future()
                f.set_result(v1)
                m_mocked.return_value = f

            with self.assertRaises(ValueError):
                await core.deferred_run()
        self.assertFalse(sub_finished_count[-1])

        # put it back
        core.model.context_plugin.enabled = True
        await core.deferred_run()
        self.assertTrue(sub_finished_count[-1])

    async def test_run_is_ready_to_run(self):
        core = _create_good_schema()

        core.model.check_plugins[0].instance._on_validation_is_ready_to_run(False)  # noqa PLW0212

        self.assertFalse(list(core.is_ready_to_run().values())[0])

        core.model.check_plugins[0].instance._on_validation_is_ready_to_run(True)  # noqa PLW0212
        self.assertTrue(list(core.is_ready_to_run().values())[0])

    async def test_run_ok_plugin_check_check_return_false(self):
        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa

        with patch.object(_PrintPrims, "_check") as m_mocked:
            v1 = (False, "Failed", None)
            if sys.version_info.minor > 7:
                m_mocked.return_value = v1
            else:
                f = asyncio.Future()
                f.set_result(v1)
                m_mocked.return_value = f

            await core.deferred_run()  # it will be ok because by default stop_if_fix_failed is False
            self.assertEqual(4, m_mocked.call_count)  # 2 plugins enabled, check -> fix -> check
        self.assertFalse(sub_finished_count[-1])

        # put it back
        core.model.context_plugin.enabled = True
        await core.deferred_run()
        self.assertTrue(sub_finished_count[-1])

    async def test_run_fail_plugin_check_check_return_false(self):
        """Here we set the stop_if_fix_failed to True for all check plugins"""

        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa

        for check_plugin in core.model.check_plugins:
            check_plugin.stop_if_fix_failed = True

        with patch.object(_PrintPrims, "_check") as m_mocked, patch.object(_PrintPrims, "_on_crash"):
            v1 = (False, "Failed", None)
            if sys.version_info.minor > 7:
                m_mocked.return_value = v1
            else:
                f = asyncio.Future()
                f.set_result(v1)
                m_mocked.return_value = f
            with self.assertRaises(ValueError):
                await core.deferred_run()  # it will be fail because by default stop_if_fix_failed is True
        self.assertFalse(sub_finished_count[-1])

        # put it back
        core.model.context_plugin.enabled = True
        await core.deferred_run()
        self.assertTrue(sub_finished_count[-1])

    async def test_run_ok_plugin_check_fix_return_false(self):
        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa

        with patch.object(_PrintPrims, "_check") as m_mocked, patch.object(_PrintPrims, "_fix") as m_mocked2:
            v1 = (False, "Failed", None)
            if sys.version_info.minor > 7:
                m_mocked.return_value = v1
            else:
                f = asyncio.Future()
                f.set_result(v1)
                m_mocked.return_value = f

            v2 = (False, "Failed", None)
            if sys.version_info.minor > 7:
                m_mocked2.return_value = v2
            else:
                f = asyncio.Future()
                f.set_result(v2)
                m_mocked2.return_value = f

            await core.deferred_run()  # it will be ok because by default stop_if_fix_failed is False
        self.assertFalse(sub_finished_count[-1])

        # put it back
        core.model.context_plugin.enabled = True
        await core.deferred_run()
        self.assertTrue(sub_finished_count[-1])

    async def test_run_fail_plugin_check_fix_return_false(self):
        """Here we set the stop_if_fix_failed to True for all check plugins"""

        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa

        for check_plugin in core.model.check_plugins:
            check_plugin.stop_if_fix_failed = True

        with (
            patch.object(_PrintPrims, "_check") as m_mocked,
            patch.object(_PrintPrims, "_fix") as m_mocked2,
            patch.object(_PrintPrims, "_on_crash"),
        ):
            v1 = (False, "Failed", None)
            if sys.version_info.minor > 7:
                m_mocked.return_value = v1
            else:
                f = asyncio.Future()
                f.set_result(v1)
                m_mocked.return_value = f

            v2 = (False, "Failed", None)
            if sys.version_info.minor > 7:
                m_mocked2.return_value = v2
            else:
                f = asyncio.Future()
                f.set_result(v2)
                m_mocked2.return_value = f

            with self.assertRaises(ValueError):
                await core.deferred_run()  # it will be fail because by default stop_if_fix_failed is True
        self.assertFalse(sub_finished_count[-1])

        # put it back
        core.model.context_plugin.enabled = True
        await core.deferred_run()
        self.assertTrue(sub_finished_count[-1])

    async def test_run_fail_plugin_context_disabled_with_set_attr(self):
        def sub_finished_count_fn(_value, message: Optional[str] = None):
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        core = _create_good_schema()
        sub_finished_count = []
        _sub = core.subscribe_run_finished(sub_finished_count_fn)  # noqa
        # set the enabled attribute using the _set_attribute private function
        core.model.context_plugin.instance._set_schema_attribute("enabled", False)  # noqa
        with self.assertRaises(ValueError):
            await core.deferred_run()
        self.assertFalse(sub_finished_count[-1])
        # put it back
        core.model.context_plugin.instance._set_schema_attribute("enabled", True)  # noqa

    async def test_run_ok_print_result(self):
        core = _create_good_schema()
        with patch("pprint.pprint") as pprint_mock:
            await core.deferred_run(print_result=True)
            self.assertEqual(2, pprint_mock.call_count)
            self.assertTrue(isinstance(pprint_mock.call_args[0][0], dict))

    async def test_run_ok_result_are_set(self):
        core = _create_good_schema()
        await core.deferred_run()
        self.assertTrue(core.model.context_plugin.data.last_check_result)
        self.assertIsNotNone(core.model.context_plugin.data.last_check_message)
        self.assertTrue(core.model.context_plugin.data.last_set_result)
        self.assertIsNotNone(core.model.context_plugin.data.last_set_message)

        # first check plugin is disabled
        self.assertIsNone(core.model.check_plugins[0].data.last_check_result)
        self.assertIsNone(core.model.check_plugins[0].data.last_check_message)
        self.assertIsNone(core.model.check_plugins[0].data.last_fix_result)
        self.assertIsNone(core.model.check_plugins[0].data.last_fix_message)

        self.assertTrue(core.model.check_plugins[1].data.last_check_result)
        self.assertIsNotNone(core.model.check_plugins[1].data.last_check_message)
        self.assertIsNone(core.model.check_plugins[1].data.last_fix_result)
        self.assertIsNone(core.model.check_plugins[1].data.last_fix_message)

        self.assertTrue(core.model.check_plugins[1].selector_plugins[0].data.last_select_result)
        self.assertIsNotNone(core.model.check_plugins[1].selector_plugins[0].data.last_select_message)

    async def test_packman_python_path(self):
        """Test for CLI"""
        root = Path(__file__)
        for _ in range(10):
            root = root.parent
        root_python = root.joinpath("dev", "tools", "packman")
        self.assertTrue(root_python.joinpath("python.bat").exists() or root_python.joinpath("python.sh").exists())
