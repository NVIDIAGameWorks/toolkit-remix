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

from contextlib import nullcontext
from unittest.mock import patch

import omni.kit.test
from omni.flux.property_widget_builder.model.usd.grouped_keys_primvar import PropertyGroupedKeysModel
from omni.flux.property_widget_builder.model.usd.logical_group_constants import GRADIENT_LOGICAL_GROUP_DEFINITION
from pxr import Gf, Vt


class _FakeAttr:
    def __init__(self, value=None, valid=True):
        self._value = value
        self._valid = valid
        self.set_calls = []

    def IsValid(self):  # noqa: N802 - mimic USD API
        return self._valid

    def Get(self):  # noqa: N802 - mimic USD API
        if not self._valid:
            raise AssertionError("Invalid attrs should not be read")
        return self._value

    def Set(self, value):  # noqa: N802 - mimic USD API
        if not self._valid:
            raise AssertionError("Invalid attrs should not be written")
        self.set_calls.append(value)
        self._value = value


class _FakePrim:
    def __init__(self, attrs=None, valid=True, path="/FakePrim"):
        self._attrs = attrs or {}
        self._valid = valid
        self._path = path

    def IsValid(self):  # noqa: N802 - mimic USD API
        return self._valid

    def GetAttribute(self, attr_name):  # noqa: N802 - mimic USD API
        return self._attrs.get(attr_name, _FakeAttr(valid=False))

    def GetPath(self):  # noqa: N802 - mimic USD API
        return self._path


class _FakeStage:
    def __init__(self, prims):
        self._prims = prims

    def GetPrimAtPath(self, prim_path):  # noqa: N802 - mimic USD API
        return self._prims.get(prim_path, _FakePrim(valid=False))


class _FakeContext:
    def __init__(self, stage):
        self._stage = stage

    def get_stage(self):
        return self._stage


class TestGradientDirectWrites(omni.kit.test.AsyncTestCase):
    async def test_direct_write_normalizes_values_before_skipping_matching_attrs(self):
        base_name = "primvars:test"
        times_attr = _FakeAttr(Vt.DoubleArray([0.0, 1.0]))
        values_attr = _FakeAttr(Vt.Vec4fArray([Gf.Vec4f(1, 0, 0, 1), Gf.Vec4f(0, 0, 1, 1)]))
        stage = _FakeStage(
            {
                "/Gradient": _FakePrim(
                    {
                        f"{base_name}:times": times_attr,
                        f"{base_name}:values": values_attr,
                    },
                    path="/Gradient",
                )
            }
        )

        with (
            patch(
                "omni.flux.property_widget_builder.model.usd.grouped_keys_primvar.omni.usd.get_context",
                return_value=_FakeContext(stage),
            ),
            patch(
                "omni.flux.property_widget_builder.model.usd.commands.defer_usd_notices",
                return_value=nullcontext(),
            ),
            patch(
                "omni.flux.property_widget_builder.model.usd.grouped_keys_primvar.PropertyGroupedKeysModel._suppress_panel_listener",
                return_value=nullcontext(),
            ),
        ):
            model = PropertyGroupedKeysModel(
                prim_paths=["/Gradient"],
                group_ids=[base_name],
                logical_group_definition=GRADIENT_LOGICAL_GROUP_DEFINITION,
            )
            model.begin_edit(base_name)
            model.commit_payload(base_name, {"times": [0.0, 1.0], "values": [(1, 0, 0, 1), (0, 0, 1, 1)]})
            model.destroy()

        self.assertEqual(times_attr.set_calls, [])
        self.assertEqual(values_attr.set_calls, [])

    async def test_direct_write_skips_invalid_prims_and_attrs(self):
        base_name = "primvars:test"
        invalid_times = _FakeAttr(valid=False)
        invalid_values = _FakeAttr(valid=False)
        stage = _FakeStage(
            {
                "/InvalidAttrs": _FakePrim(
                    {
                        f"{base_name}:times": invalid_times,
                        f"{base_name}:values": invalid_values,
                    },
                    path="/InvalidAttrs",
                ),
                "/InvalidPrim": _FakePrim(valid=False, path="/InvalidPrim"),
            }
        )

        with (
            patch(
                "omni.flux.property_widget_builder.model.usd.grouped_keys_primvar.omni.usd.get_context",
                return_value=_FakeContext(stage),
            ),
            patch(
                "omni.flux.property_widget_builder.model.usd.commands.defer_usd_notices",
                return_value=nullcontext(),
            ),
            patch(
                "omni.flux.property_widget_builder.model.usd.grouped_keys_primvar.PropertyGroupedKeysModel._suppress_panel_listener",
                return_value=nullcontext(),
            ),
        ):
            model = PropertyGroupedKeysModel(
                prim_paths=["/InvalidPrim", "/InvalidAttrs"],
                group_ids=[base_name],
                logical_group_definition=GRADIENT_LOGICAL_GROUP_DEFINITION,
            )
            model.begin_edit(base_name)
            model.commit_payload(base_name, {"times": [0.0, 1.0], "values": [(1, 0, 0, 1), (0, 0, 1, 1)]})
            model.destroy()
