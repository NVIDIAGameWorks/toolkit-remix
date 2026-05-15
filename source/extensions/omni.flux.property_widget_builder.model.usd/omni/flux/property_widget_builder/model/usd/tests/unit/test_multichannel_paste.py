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

__all__ = ("TestMultichannelPaste",)

import omni.kit.test
import omni.usd
from omni.flux.property_widget_builder.model.usd.item_model.attr_value import UsdAttributeValueModel
from pxr import Gf, Sdf


def _make_vec3_model(stage, prim_path: str, attr_name: str, channel_index: int, initial: Gf.Vec3f):
    prim = stage.DefinePrim(prim_path)
    attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Float3)
    attr.Set(initial)
    return UsdAttributeValueModel(
        context_name="",
        attribute_paths=[Sdf.Path(f"{prim_path}.{attr_name}")],
        channel_index=channel_index,
    )


def _make_float_model(stage, prim_path: str, attr_name: str, value: float):
    prim = stage.DefinePrim(prim_path)
    attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Float)
    attr.Set(value)
    return UsdAttributeValueModel(
        context_name="",
        attribute_paths=[Sdf.Path(f"{prim_path}.{attr_name}")],
        channel_index=0,
    )


def _read_attr(stage, prim_path: str, attr_name: str):
    return stage.GetPrimAtPath(prim_path).GetAttribute(attr_name).Get()


class TestMultichannelPaste(omni.kit.test.AsyncTestCase):
    """Regression tests for ``UsdAttributeValueModel.begin_paste``.

    ``Item.apply_serialized_data`` walks channels back-to-back; each channel's
    ``_write_value_to_usd`` writes the entire multichannel tuple (Sdf has no
    per-component write). The USD listener that would normally keep
    ``self._value`` in sync coalesces ``Usd.Notice.ObjectsChanged`` during
    interactive operations, so by the time channel N writes its tuple the
    cached sibling channels are stale and clobber the values that channel
    N-1 just wrote. ``begin_paste`` re-reads USD before each channel's
    deserialize to break that race; these tests pin that contract.
    """

    async def setUp(self):
        self.context = omni.usd.get_context()
        await self.context.new_stage_async()
        self.stage = self.context.get_stage()

    async def tearDown(self):
        if self.context:
            await self.context.close_stage_async()
        self.context = None
        self.stage = None

    async def test_begin_paste_syncs_multichannel_cache_to_usd(self):
        # Arrange: cached _value matches USD, then USD is mutated externally to
        # mimic a sibling channel's write that the coalesced listener hasn't
        # delivered yet. Use only values that round-trip exactly through float32
        # so the assertion can compare Gf.Vec3f for equality.
        model = _make_vec3_model(
            self.stage,
            "/Prim",
            "customVec",
            channel_index=1,
            initial=Gf.Vec3f(1.0, 2.0, 3.0),
        )
        self.assertTrue(model._is_multichannel, "Float3 should be flagged multichannel")
        self.stage.GetPrimAtPath("/Prim").GetAttribute("customVec").Set(Gf.Vec3f(7.0, 8.0, 9.0))
        # Pretend the listener was throttled and the cache stayed at the old vector.
        model._value = Gf.Vec3f(1.0, 2.0, 3.0)

        # Act
        model.begin_paste()

        # Assert: USD value pulled into the cache so the next _write_value_to_usd
        # won't write a stale tuple over a sibling's freshly-written channel.
        self.assertEqual(model._value, Gf.Vec3f(7.0, 8.0, 9.0))

    async def test_begin_paste_is_noop_for_single_channel_models(self):
        # Arrange: single-channel models never share a tuple with siblings, so
        # begin_paste should skip the refresh entirely.
        model = _make_float_model(self.stage, "/PrimF", "intensity", value=0.5)
        self.assertFalse(model._is_multichannel, "Float should not be flagged multichannel")
        model._value = 999.0  # deliberately wrong vs USD

        # Act
        model.begin_paste()

        # Assert: untouched. If begin_paste fell through to _read_value_from_usd
        # it would have replaced 999.0 with the on-stage 0.5.
        self.assertEqual(model._value, 999.0)

    async def test_simulated_paste_flow_preserves_all_channels(self):
        # Arrange: three sibling channel models pointing at the same Float3
        # attribute. The pre-paste value is (1, 2, 3); the paste payload is
        # (10, 20, 30). Without begin_paste, only the last channel survives.
        # A generic attribute name avoids any USD xformable/schema validation.
        prim = self.stage.DefinePrim("/Target")
        attr = prim.CreateAttribute("customVec", Sdf.ValueTypeNames.Float3)
        attr.Set(Gf.Vec3f(1.0, 2.0, 3.0))
        attr_path = Sdf.Path("/Target.customVec")
        models = [
            UsdAttributeValueModel(context_name="", attribute_paths=[attr_path], channel_index=i) for i in range(3)
        ]

        # Act: mirror Item.apply_serialized_data's begin_paste/deserialize/end_paste loop.
        for model, value in zip(models, [10.0, 20.0, 30.0]):
            model.begin_paste()
            try:
                model.set_value(value)
            finally:
                model.end_paste()

        # Assert: all three channels round-trip; none clobbered by stale sibling caches.
        self.assertEqual(_read_attr(self.stage, "/Target", "customVec"), Gf.Vec3f(10.0, 20.0, 30.0))
