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

import copy
from unittest.mock import patch

import carb
import carb.settings
from omni.flux.validator.manager.core import ValidationSchema as _ValidationSchema
from omni.flux.validator.mass.core import SCHEMA_PATH_SETTING as _SCHEMA_PATH_SETTING
from omni.flux.validator.mass.core import ManagerMassCore as _ManagerMassCore
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import get_test_data_path

from .fake_plugins import FakeCheck as _FakeCheck
from .fake_plugins import FakeContext as _FakeContext
from .fake_plugins import FakeSelector as _FakeSelector
from .fake_plugins import register_fake_plugins as _register_fake_plugins
from .fake_plugins import unregister_fake_plugins as _unregister_fake_plugins


def _get_fake_context_not_cook_template():
    return {
        "name": "Test",
        "context_plugin": {"name": "FakeContext", "data": {}},
        "check_plugins": [
            {
                "name": "FakeCheck",
                "enabled": False,
                "context_plugin": {"name": "FakeContext", "data": {}},
                "selector_plugins": [{"name": "FakeSelector", "data": {}}],
                "data": {},
                "pause_if_fix_failed": False,
            },
            {
                "name": "FakeCheck",
                "selector_plugins": [{"name": "FakeSelector", "data": {}}],
                "data": {},
                "context_plugin": {"name": "FakeContext", "data": {}},
                "pause_if_fix_failed": False,
            },
            {
                "name": "FakeCheck",
                "selector_plugins": [{"name": "FakeSelector", "data": {}}],
                "data": {},
                "context_plugin": {"name": "FakeContext", "data": {}},
                "pause_if_fix_failed": False,
            },
        ],
    }


class TestCore(AsyncTestCase):
    SCHEMAS = [
        get_test_data_path(__name__, "schemas/good_material_ingestion.json"),
        get_test_data_path(__name__, "schemas/good_model_ingestion.json"),
    ]

    async def setUp(self):
        _register_fake_plugins()

    # After running each test
    async def tearDown(self):
        _unregister_fake_plugins()

    async def test_init_schemas_no_error(self):
        test_runs = (
            {"name": "None schema", "value": None},
            {"name": "Empty list schema", "value": []},
            {"name": "One schema", "value": [self.SCHEMAS[0]]},
            {"name": "Multiple schemas", "value": self.SCHEMAS},
        )

        for run in test_runs:
            with self.subTest(name=run["name"]):
                # no error
                _ManagerMassCore(schema_paths=run["value"])

    async def test_init_schemas_error(self):
        test_runs = (
            {"name": "One schema don't exist", "value": ["bad_path.json"]},
            {"name": "Multiple schemas, one don't exist", "value": ["bad_path.json", self.SCHEMAS[0]]},
        )

        for run in test_runs:
            with self.subTest(name=run["name"]):
                # no error
                with self.assertRaises((FileNotFoundError, IOError)):
                    with patch.object(carb, "log_error"):
                        _ManagerMassCore(schema_paths=run["value"])

    async def test_init_no_schemas_added(self):
        core = _ManagerMassCore()
        core.add_schemas([])
        items = core.schema_model.get_item_children(None)
        self.assertEqual(len(items), 0)

    async def test_init_schemas_added(self):
        core = _ManagerMassCore(schema_paths=self.SCHEMAS)
        items = core.schema_model.get_item_children(None)
        self.assertEqual(len(items), 2)

        # adding schema doesn't create Manager core
        with patch.object(core, "_on_core_added") as subscribe_core_added_mock:
            core.add_schemas([items[0]._data])  # noqa
            self.assertEqual(subscribe_core_added_mock.call_count, 0)

    async def test_schemas_added_with_setting(self):
        value = ",".join(self.SCHEMAS)
        carb.settings.get_settings().set(_SCHEMA_PATH_SETTING, value)
        core = _ManagerMassCore()
        items = core.schema_model.get_item_children(None)
        self.assertEqual(len(items), 2)

        # adding schema doesn't create Manager core
        with patch.object(core, "_on_core_added") as subscribe_core_added_mock:
            core.add_schemas([items[0]._data])  # noqa
            self.assertEqual(subscribe_core_added_mock.call_count, 0)

        carb.settings.get_settings().destroy_item(_SCHEMA_PATH_SETTING)

    async def test_cook_templates_no_cook_mass_template(self):
        core = _ManagerMassCore()

        # schema with no "cook_mass_template" value should do nothing
        fake_schema = _get_fake_context_not_cook_template()
        core.add_schemas([fake_schema])
        items = core.schema_model.get_item_children(None)
        result = await items[0].cook_template()

        # because we didn't enabled "cook_mass_template" anywhere in the schema, the output is the same
        # than the input. Nothing changed.
        self.assertDictEqual(result[0], _ValidationSchema(**fake_schema).model_dump(serialize_as_any=True))

    async def test_cook_same_templates_context(self):
        for i in range(4):
            with self.subTest(name=f"Testing with {i} cooking output"):
                core = _ManagerMassCore()

                # schema with no "cook_mass_template" value should do nothing
                fake_schema = _get_fake_context_not_cook_template()
                fake_schema["context_plugin"]["data"]["cook_mass_template"] = True
                core.add_schemas([fake_schema])
                items = core.schema_model.get_item_children(None)

                with patch.object(_FakeContext, "mass_cook_template") as mass_cook_template_mock:
                    mass_cook_template_mock.return_value = (
                        True,
                        None,
                        [_FakeContext.data_type(**fake_schema["context_plugin"]["data"])]
                        * i,  # multiply the number of output here
                    )
                    result = await items[0].cook_template()

                    # schemas should match
                    for res in result:
                        self.assertDictEqual(
                            res, _ValidationSchema(**copy.deepcopy(fake_schema)).model_dump(serialize_as_any=True)
                        )

    async def test_mass_cook_template_failed_should_throw(self):
        core = _ManagerMassCore()

        fake_schema = _get_fake_context_not_cook_template()
        fake_schema["context_plugin"]["data"]["cook_mass_template"] = True
        core.add_schemas([fake_schema])
        items = core.schema_model.get_item_children(None)

        test_error = "Test Error Message"

        with patch.object(_FakeContext, "mass_cook_template") as mass_cook_template_mock:
            mass_fake_schema = copy.deepcopy(fake_schema["context_plugin"]["data"])
            mass_fake_schema["display_name_mass_template"] = "Test123456789"
            mass_cook_template_mock.return_value = (
                False,
                test_error,
                None,
            )

            with self.assertRaises(ValueError) as cm:
                await items[0].cook_template_no_exception()

        self.assertEqual(str(cm.exception), test_error)

    async def test_cook_change_display_templates_context(self):
        """We change the display name"""
        core = _ManagerMassCore()

        # schema with no "cook_mass_template" value should do nothing
        fake_schema = _get_fake_context_not_cook_template()
        fake_schema["context_plugin"]["data"]["cook_mass_template"] = True
        core.add_schemas([fake_schema])
        items = core.schema_model.get_item_children(None)

        with patch.object(_FakeContext, "mass_cook_template") as mass_cook_template_mock:
            mass_fake_schema = copy.deepcopy(fake_schema["context_plugin"]["data"])
            mass_fake_schema["display_name_mass_template"] = "Test123456789"
            mass_cook_template_mock.return_value = (
                True,
                None,
                [
                    _FakeContext.data_type(**mass_fake_schema),
                    _FakeContext.data_type(**fake_schema["context_plugin"]["data"]),
                ],
            )
            result = await items[0].cook_template()

            for res in result:
                self.assertEqual(res["name"], "Test123456789")

            # reverse order
            mass_cook_template_mock.return_value = (
                True,
                None,
                [
                    _FakeContext.data_type(**fake_schema["context_plugin"]["data"]),
                    _FakeContext.data_type(**mass_fake_schema),
                ],
            )
            result = await items[0].cook_template()

            self.assertListEqual([res["name"] for res in result], ["Test", "Test123456789"])

    async def test_cook_change_slow_down_value_templates_check_01(self):
        """We return 2 templates and change the last_check_message only on the first template and second plugin"""
        core = _ManagerMassCore()
        fake_schema = _get_fake_context_not_cook_template()

        # we only cook on the second plugin
        fake_schema["check_plugins"][1]["data"].update({"cook_mass_template": True})
        core.add_schemas([fake_schema])
        items = core.schema_model.get_item_children(None)

        def my_side_effect(schema_data_template):
            mass_fake_schema = schema_data_template.model_dump(serialize_as_any=True)
            mass_fake_schema.update({"last_check_message": "hello01"})
            return (
                True,
                None,
                [
                    _FakeCheck.data_type(**mass_fake_schema),
                    _FakeCheck.data_type(**schema_data_template.model_dump(serialize_as_any=True)),
                ],
            )

        with patch.object(_FakeCheck, "mass_cook_template", side_effect=my_side_effect):
            result = await items[0].cook_template()

            self.assertEqual(len(result), 2)
            default_values = _ValidationSchema(**fake_schema).model_dump(serialize_as_any=True)["check_plugins"][0][
                "data"
            ]["last_check_message"]

            # template result 01
            self.assertEqual(result[0]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[0]["check_plugins"][1]["data"]["last_check_message"], "hello01")
            self.assertEqual(result[0]["check_plugins"][2]["data"]["last_check_message"], default_values)

            # template result 02
            self.assertEqual(result[1]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[1]["check_plugins"][1]["data"]["last_check_message"], default_values)
            self.assertEqual(result[1]["check_plugins"][2]["data"]["last_check_message"], default_values)

    async def test_cook_change_slow_down_value_templates_check_02(self):
        """We return 2 templates and change the last_check_message on the two templates and second plugin"""
        core = _ManagerMassCore()
        fake_schema = _get_fake_context_not_cook_template()

        # we only cook on the second plugin
        fake_schema["check_plugins"][1]["data"].update({"cook_mass_template": True})
        core.add_schemas([fake_schema])
        items = core.schema_model.get_item_children(None)

        def my_side_effect(schema_data_template):
            mass_fake_schema = schema_data_template.model_dump(serialize_as_any=True)
            mass_fake_schema.update({"last_check_message": "hello01"})
            return (
                True,
                None,
                [
                    _FakeCheck.data_type(**mass_fake_schema),
                    _FakeCheck.data_type(**mass_fake_schema),
                ],
            )

        with patch.object(_FakeCheck, "mass_cook_template", side_effect=my_side_effect):
            result = await items[0].cook_template()

            self.assertEqual(len(result), 2)
            default_values = _ValidationSchema(**fake_schema).model_dump(serialize_as_any=True)["check_plugins"][0][
                "data"
            ]["last_check_message"]
            # template result 01
            self.assertEqual(result[0]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[0]["check_plugins"][1]["data"]["last_check_message"], "hello01")
            self.assertEqual(result[0]["check_plugins"][2]["data"]["last_check_message"], default_values)

            # template result 02
            self.assertEqual(result[1]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[1]["check_plugins"][1]["data"]["last_check_message"], "hello01")
            self.assertEqual(result[1]["check_plugins"][2]["data"]["last_check_message"], default_values)

    async def test_cook_change_slow_down_value_templates_check_03(self):
        """
        We enabled cooking on 2 check plugins that return 2 templates each, so we have 4 templates.

        Each cooking will change the value of last_check_message.
        For the first cooked template will have the last_check_message to "hello01"
        For the second cooked template will have the last_check_message to "hello02"

        As a result, we have 4 templates with:
            - template 1: default, "hello01", "hello01"
            - template 2: default, "hello01", "hello02"
            - template 3: default, "hello02", "hello01"
            - template 4: default, "hello02", "hello02"
        """
        core = _ManagerMassCore()
        fake_schema = _get_fake_context_not_cook_template()

        # we only cook on the second plugin
        fake_schema["check_plugins"][1]["data"].update({"cook_mass_template": True})
        fake_schema["check_plugins"][2]["data"].update({"cook_mass_template": True})
        core.add_schemas([fake_schema])
        items = core.schema_model.get_item_children(None)

        def my_side_effect(schema_data_template):
            mass_fake_schema = schema_data_template.model_dump(serialize_as_any=True)
            mass_fake_schema.update({"last_check_message": "hello01"})
            mass_fake_schem2 = schema_data_template.model_dump(serialize_as_any=True)
            mass_fake_schem2.update({"last_check_message": "hello02"})
            return (
                True,
                None,
                [
                    _FakeCheck.data_type(**mass_fake_schema),
                    _FakeCheck.data_type(**mass_fake_schem2),
                ],
            )

        with patch.object(_FakeCheck, "mass_cook_template", side_effect=my_side_effect):
            result = await items[0].cook_template()

            self.assertEqual(len(result), 4)
            default_values = _ValidationSchema(**fake_schema).model_dump(serialize_as_any=True)["check_plugins"][0][
                "data"
            ]["last_check_message"]
            # template result 01
            self.assertEqual(result[0]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[0]["check_plugins"][1]["data"]["last_check_message"], "hello01")
            self.assertEqual(result[0]["check_plugins"][2]["data"]["last_check_message"], "hello01")

            # template result 02
            self.assertEqual(result[1]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[1]["check_plugins"][1]["data"]["last_check_message"], "hello01")
            self.assertEqual(result[1]["check_plugins"][2]["data"]["last_check_message"], "hello02")

            # template result 03
            self.assertEqual(result[2]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[2]["check_plugins"][1]["data"]["last_check_message"], "hello02")
            self.assertEqual(result[2]["check_plugins"][2]["data"]["last_check_message"], "hello01")

            # template result 04
            self.assertEqual(result[3]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[3]["check_plugins"][1]["data"]["last_check_message"], "hello02")
            self.assertEqual(result[3]["check_plugins"][2]["data"]["last_check_message"], "hello02")

    async def test_cook_change_slow_down_value_templates_check_04(self):
        """
        We enabled cooking on 2 check plugins that return 3 templates each, so we have 9 templates.

        Each cooking will change the value of last_check_message.
        For the first cooked template will have the last_check_message to "hello01"
        For the second cooked template will have the last_check_message to "hello02"

        As a result, we have 4 templates with:
            - template 1: default, "hello01", "hello01"
            - template 2: default, "hello01", "hello02"
            - template 3: default, "hello02", "hello01"
            - template 4: default, "hello02", "hello02"
        """
        core = _ManagerMassCore()
        fake_schema = _get_fake_context_not_cook_template()

        # we only cook on the second plugin
        fake_schema["check_plugins"][1]["data"].update({"cook_mass_template": True})
        fake_schema["check_plugins"][2]["data"].update({"cook_mass_template": True})
        core.add_schemas([fake_schema])
        items = core.schema_model.get_item_children(None)

        def my_side_effect(schema_data_template):
            mass_fake_schema = schema_data_template.model_dump(serialize_as_any=True)
            mass_fake_schema.update({"last_check_message": "hello01"})
            mass_fake_schem2 = schema_data_template.model_dump(serialize_as_any=True)
            mass_fake_schem2.update({"last_check_message": "hello02"})
            mass_fake_schem3 = schema_data_template.model_dump(serialize_as_any=True)
            return (
                True,
                None,
                [
                    _FakeCheck.data_type(**mass_fake_schema),
                    _FakeCheck.data_type(**mass_fake_schem2),
                    _FakeCheck.data_type(**mass_fake_schem3),
                ],
            )

        with patch.object(_FakeCheck, "mass_cook_template", side_effect=my_side_effect):
            result = await items[0].cook_template()

            self.assertEqual(len(result), 9)
            default_values = _ValidationSchema(**fake_schema).model_dump(serialize_as_any=True)["check_plugins"][0][
                "data"
            ]["last_check_message"]
            # template result 01
            self.assertEqual(result[0]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[0]["check_plugins"][1]["data"]["last_check_message"], "hello01")
            self.assertEqual(result[0]["check_plugins"][2]["data"]["last_check_message"], "hello01")

            # template result 02
            self.assertEqual(result[1]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[1]["check_plugins"][1]["data"]["last_check_message"], "hello01")
            self.assertEqual(result[1]["check_plugins"][2]["data"]["last_check_message"], "hello02")

            # template result 03
            self.assertEqual(result[2]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[2]["check_plugins"][1]["data"]["last_check_message"], "hello01")
            self.assertEqual(result[2]["check_plugins"][2]["data"]["last_check_message"], default_values)

            # template result 04
            self.assertEqual(result[3]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[3]["check_plugins"][1]["data"]["last_check_message"], "hello02")
            self.assertEqual(result[3]["check_plugins"][2]["data"]["last_check_message"], "hello01")

            # template result 05
            self.assertEqual(result[4]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[4]["check_plugins"][1]["data"]["last_check_message"], "hello02")
            self.assertEqual(result[4]["check_plugins"][2]["data"]["last_check_message"], "hello02")

            # template result 06
            self.assertEqual(result[5]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[5]["check_plugins"][1]["data"]["last_check_message"], "hello02")
            self.assertEqual(result[5]["check_plugins"][2]["data"]["last_check_message"], default_values)

            # template result 07
            self.assertEqual(result[6]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[6]["check_plugins"][1]["data"]["last_check_message"], default_values)
            self.assertEqual(result[6]["check_plugins"][2]["data"]["last_check_message"], "hello01")

            # template result 08
            self.assertEqual(result[7]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[7]["check_plugins"][1]["data"]["last_check_message"], default_values)
            self.assertEqual(result[7]["check_plugins"][2]["data"]["last_check_message"], "hello02")

            # template result 09
            self.assertEqual(result[8]["check_plugins"][0]["data"]["last_check_message"], default_values)
            self.assertEqual(result[8]["check_plugins"][1]["data"]["last_check_message"], default_values)
            self.assertEqual(result[8]["check_plugins"][2]["data"]["last_check_message"], default_values)

    async def test_cook_change_slow_down_value_templates_select_01(self):
        """
        We enabled cooking on 2 select plugins that return 1 templates each, so we have 1 template.
        We change the value of last_select_message.
        """
        core = _ManagerMassCore()
        fake_schema = _get_fake_context_not_cook_template()

        # we only cook on the second plugin
        fake_schema["check_plugins"][1]["selector_plugins"][0]["data"].update({"cook_mass_template": True})
        fake_schema["check_plugins"][2]["selector_plugins"][0]["data"].update({"cook_mass_template": True})
        core.add_schemas([fake_schema])
        items = core.schema_model.get_item_children(None)

        def my_side_effect(schema_data_template):
            mass_fake_schema = schema_data_template.model_dump(serialize_as_any=True)
            mass_fake_schema.update({"last_select_message": "hello01"})
            return (
                True,
                None,
                [
                    _FakeSelector.data_type(**mass_fake_schema),
                ],
            )

        with patch.object(_FakeSelector, "mass_cook_template", side_effect=my_side_effect):
            result = await items[0].cook_template()

            self.assertEqual(len(result), 1)
            default_values = _ValidationSchema(**fake_schema).model_dump(serialize_as_any=True)["check_plugins"][0][
                "selector_plugins"
            ][0]["data"]["last_select_message"]
            # template result 01
            self.assertEqual(
                result[0]["check_plugins"][0]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[0]["check_plugins"][1]["selector_plugins"][0]["data"]["last_select_message"], "hello01"
            )
            self.assertEqual(
                result[0]["check_plugins"][2]["selector_plugins"][0]["data"]["last_select_message"], "hello01"
            )

    async def test_cook_change_slow_down_value_templates_select_02(self):
        """
        We enabled cooking on 2 select plugins that return 3 templates each, so we have 9 templates.

        Each cooking will change the value of last_select_message.
        For the first cooked template will have the last_select_message to "hello01"
        For the second cooked template will have the last_select_message to "hello02"

        As a result, we have 4 templates with:
            - template 1: default, "hello01", "hello01"
            - template 2: default, "hello01", "hello02"
            - template 3: default, "hello02", "hello01"
            - template 4: default, "hello02", "hello02"
        """
        core = _ManagerMassCore()
        fake_schema = _get_fake_context_not_cook_template()

        # we only cook on the second plugin
        fake_schema["check_plugins"][1]["selector_plugins"][0]["data"].update({"cook_mass_template": True})
        fake_schema["check_plugins"][2]["selector_plugins"][0]["data"].update({"cook_mass_template": True})
        core.add_schemas([fake_schema])
        items = core.schema_model.get_item_children(None)

        def my_side_effect(schema_data_template):
            mass_fake_schema = schema_data_template.model_dump(serialize_as_any=True)
            mass_fake_schema.update({"last_select_message": "hello01"})
            mass_fake_schem2 = schema_data_template.model_dump(serialize_as_any=True)
            mass_fake_schem2.update({"last_select_message": "hello02"})
            mass_fake_schem3 = schema_data_template.model_dump(serialize_as_any=True)
            return (
                True,
                None,
                [
                    _FakeSelector.data_type(**mass_fake_schema),
                    _FakeSelector.data_type(**mass_fake_schem2),
                    _FakeSelector.data_type(**mass_fake_schem3),
                ],
            )

        with patch.object(_FakeSelector, "mass_cook_template", side_effect=my_side_effect):
            result = await items[0].cook_template()

            self.assertEqual(len(result), 9)
            default_values = _ValidationSchema(**fake_schema).model_dump(serialize_as_any=True)["check_plugins"][0][
                "selector_plugins"
            ][0]["data"]["last_select_message"]
            # template result 01
            self.assertEqual(
                result[0]["check_plugins"][0]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[0]["check_plugins"][1]["selector_plugins"][0]["data"]["last_select_message"], "hello01"
            )
            self.assertEqual(
                result[0]["check_plugins"][2]["selector_plugins"][0]["data"]["last_select_message"], "hello01"
            )

            # template result 02
            self.assertEqual(
                result[1]["check_plugins"][0]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[1]["check_plugins"][1]["selector_plugins"][0]["data"]["last_select_message"], "hello01"
            )
            self.assertEqual(
                result[1]["check_plugins"][2]["selector_plugins"][0]["data"]["last_select_message"], "hello02"
            )

            # template result 03
            self.assertEqual(
                result[2]["check_plugins"][0]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[2]["check_plugins"][1]["selector_plugins"][0]["data"]["last_select_message"], "hello01"
            )
            self.assertEqual(
                result[2]["check_plugins"][2]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )

            # template result 04
            self.assertEqual(
                result[3]["check_plugins"][0]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[3]["check_plugins"][1]["selector_plugins"][0]["data"]["last_select_message"], "hello02"
            )
            self.assertEqual(
                result[3]["check_plugins"][2]["selector_plugins"][0]["data"]["last_select_message"], "hello01"
            )

            # template result 05
            self.assertEqual(
                result[4]["check_plugins"][0]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[4]["check_plugins"][1]["selector_plugins"][0]["data"]["last_select_message"], "hello02"
            )
            self.assertEqual(
                result[4]["check_plugins"][2]["selector_plugins"][0]["data"]["last_select_message"], "hello02"
            )

            # template result 06
            self.assertEqual(
                result[5]["check_plugins"][0]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[5]["check_plugins"][1]["selector_plugins"][0]["data"]["last_select_message"], "hello02"
            )
            self.assertEqual(
                result[5]["check_plugins"][2]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )

            # template result 07
            self.assertEqual(
                result[6]["check_plugins"][0]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[6]["check_plugins"][1]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[6]["check_plugins"][2]["selector_plugins"][0]["data"]["last_select_message"], "hello01"
            )

            # template result 08
            self.assertEqual(
                result[7]["check_plugins"][0]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[7]["check_plugins"][1]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[7]["check_plugins"][2]["selector_plugins"][0]["data"]["last_select_message"], "hello02"
            )

            # template result 09
            self.assertEqual(
                result[8]["check_plugins"][0]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[8]["check_plugins"][1]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
            self.assertEqual(
                result[8]["check_plugins"][2]["selector_plugins"][0]["data"]["last_select_message"], default_values
            )
