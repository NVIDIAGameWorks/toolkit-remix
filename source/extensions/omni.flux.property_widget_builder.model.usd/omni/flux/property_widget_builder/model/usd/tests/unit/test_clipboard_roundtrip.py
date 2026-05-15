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

__all__ = ("TestClipboardRoundtrip",)

import contextlib
import json
from unittest import mock

import omni.kit.clipboard
import omni.kit.test
import omni.usd
from omni.flux.property_widget_builder.model.usd import USDAttributeItem
from omni.flux.property_widget_builder.widget.tree import clipboard
from pxr import Gf, Sdf, Usd


class _StubClipboard:
    """Per-test stub of omni.kit.clipboard so tests don't race on the system clipboard."""

    def __init__(self):
        self._data = None
        self._stack = contextlib.ExitStack()

    def __enter__(self):
        self._stack.enter_context(mock.patch("omni.kit.clipboard.copy", autospec=True, side_effect=self._copy))
        self._stack.enter_context(mock.patch("omni.kit.clipboard.paste", autospec=True, side_effect=self._paste))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stack.close()

    def _copy(self, data):
        self._data = data

    def _paste(self):
        return self._data

    @property
    def raw(self):
        return self._data


def _make_vec_item(stage, prim_path: str, attr_name: str, type_name: Sdf.ValueTypeName, value):
    """Create a prim attribute with the given value and wrap it in a USDAttributeItem."""
    prim = stage.DefinePrim(prim_path)
    attr = prim.CreateAttribute(attr_name, type_name)
    attr.Set(value)
    return USDAttributeItem(
        context_name="",
        attribute_paths=[Sdf.Path(f"{prim_path}.{attr_name}")],
    )


def _make_asset_item(stage, prim_path: str, attr_name: str, value: Sdf.AssetPath):
    prim = stage.DefinePrim(prim_path)
    attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Asset)
    attr.Set(value)
    return USDAttributeItem(
        context_name="",
        attribute_paths=[Sdf.Path(f"{prim_path}.{attr_name}")],
    )


def _read_attr(stage, prim_path: str, attr_name: str):
    return stage.GetPrimAtPath(prim_path).GetAttribute(attr_name).Get()


class TestClipboardRoundtrip(omni.kit.test.AsyncTestCase):
    """Regression tests for the JIRA bug 'Properties Do Not Copy/Paste Correctly'.

    Symptoms covered:
      - Transform values (size/position/rotation) differ on the target prim after paste.
      - Asset path attributes (e.g. material textures) fail to paste.
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

    async def test_translate_xformop_pastes_to_target_prim(self):
        # Arrange
        source = _make_vec_item(
            self.stage,
            "/Source",
            "xformOp:translate",
            Sdf.ValueTypeNames.Double3,
            Gf.Vec3d(1.0, 2.0, 3.0),
        )
        target = _make_vec_item(
            self.stage,
            "/Target",
            "xformOp:translate",
            Sdf.ValueTypeNames.Double3,
            Gf.Vec3d(0.0, 0.0, 0.0),
        )

        # Act
        with _StubClipboard():
            clipboard.copy([source])
            clipboard.paste([target])

        # Assert
        self.assertEqual(_read_attr(self.stage, "/Target", "xformOp:translate"), Gf.Vec3d(1.0, 2.0, 3.0))

    async def test_rotate_xyz_xformop_pastes_to_target_prim(self):
        # Arrange
        source = _make_vec_item(
            self.stage,
            "/Source",
            "xformOp:rotateXYZ",
            Sdf.ValueTypeNames.Float3,
            Gf.Vec3f(45.0, 90.0, 180.0),
        )
        target = _make_vec_item(
            self.stage,
            "/Target",
            "xformOp:rotateXYZ",
            Sdf.ValueTypeNames.Float3,
            Gf.Vec3f(0.0, 0.0, 0.0),
        )

        # Act
        with _StubClipboard():
            clipboard.copy([source])
            clipboard.paste([target])

        # Assert
        self.assertEqual(_read_attr(self.stage, "/Target", "xformOp:rotateXYZ"), Gf.Vec3f(45.0, 90.0, 180.0))

    async def test_scale_xformop_pastes_to_target_prim(self):
        # Arrange
        source = _make_vec_item(
            self.stage,
            "/Source",
            "xformOp:scale",
            Sdf.ValueTypeNames.Float3,
            Gf.Vec3f(2.0, 2.0, 2.0),
        )
        target = _make_vec_item(
            self.stage,
            "/Target",
            "xformOp:scale",
            Sdf.ValueTypeNames.Float3,
            Gf.Vec3f(1.0, 1.0, 1.0),
        )

        # Act
        with _StubClipboard():
            clipboard.copy([source])
            clipboard.paste([target])

        # Assert
        self.assertEqual(_read_attr(self.stage, "/Target", "xformOp:scale"), Gf.Vec3f(2.0, 2.0, 2.0))

    async def test_asset_path_attribute_pastes_resolved_path_to_target(self):
        # Arrange
        source_path = "/tmp/source_texture.png"
        source = _make_asset_item(
            self.stage,
            "/SourceMat",
            "inputs:diffuse_texture",
            Sdf.AssetPath(source_path),
        )
        target = _make_asset_item(
            self.stage,
            "/TargetMat",
            "inputs:diffuse_texture",
            Sdf.AssetPath(""),
        )

        # Act
        with _StubClipboard():
            clipboard.copy([source])
            clipboard.paste([target])

        # Assert
        pasted = _read_attr(self.stage, "/TargetMat", "inputs:diffuse_texture")
        self.assertIsNotNone(pasted, "asset path attribute was not pasted onto target")
        # The path should round-trip to the same texture (potentially via a relative form).
        self.assertNotEqual(pasted.path, "", "asset path round-trip lost the texture path")

    async def test_relative_asset_path_pastes_to_target(self):
        # Regression cover for relative texture paths authored against the edit target.
        # resolvedPath is typically empty here so the serializer must use the authored
        # path; otherwise paste loses it. Covers both POSIX-style "./blah.png" and
        # the Windows-style ".\blah.png" form that Remix users actually author.
        for relative_path in ("./blah.png", ".\\blah.png"):
            with self.subTest(relative_path=relative_path):
                source_prim = f"/SourceMatRel_{abs(hash(relative_path))}"
                target_prim = f"/TargetMatRel_{abs(hash(relative_path))}"
                source = _make_asset_item(
                    self.stage,
                    source_prim,
                    "inputs:diffuse_texture",
                    Sdf.AssetPath(relative_path),
                )
                target = _make_asset_item(
                    self.stage,
                    target_prim,
                    "inputs:diffuse_texture",
                    Sdf.AssetPath(""),
                )

                with _StubClipboard():
                    clipboard.copy([source])
                    clipboard.paste([target])

                pasted = _read_attr(self.stage, target_prim, "inputs:diffuse_texture")
                self.assertIsNotNone(pasted, "relative asset path was not pasted onto target")
                self.assertNotEqual(pasted.path, "", "relative asset path round-trip lost the texture path")
                self.assertIn("blah.png", pasted.path, "pasted relative path does not point at the original file")
                # Serializer normalizes backslashes to forward slashes — the pasted form
                # should never carry Windows separators regardless of input shape.
                self.assertNotIn("\\", pasted.path, "pasted path retained Windows-style separators")

    async def test_clipboard_copy_serializes_vec3_components_per_channel(self):
        # Arrange
        source = _make_vec_item(
            self.stage,
            "/SourceVec",
            "xformOp:translate",
            Sdf.ValueTypeNames.Float3,
            Gf.Vec3f(1.0, 2.0, 3.0),
        )

        # Act
        with _StubClipboard() as cb:
            clipboard.copy([source])
            raw = cb.raw

        # Assert
        # Multichannel USDAttributeItems split a Vec3 into one value-model per channel,
        # so the serialized payload carries three floats, not a single Gf.Vec.
        decoded = json.loads(raw)
        self.assertIsInstance(decoded, list)
        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0]["values"], [1.0, 2.0, 3.0])

    async def test_clipboard_copy_serializes_unresolved_asset_path(self):
        # Directly asserts the serializer fallback: an unresolved asset path
        # (resolvedPath empty) must serialize as the authored path, not as "".
        # The roundtrip test catches this indirectly via the paste result; this
        # one catches it at the source side before the target is involved, so
        # a regression here points the finger at the serializer specifically.
        source_path = "/tmp/unresolved_for_serialize.png"
        source = _make_asset_item(
            self.stage,
            "/SourceMatSerialize",
            "inputs:diffuse_texture",
            Sdf.AssetPath(source_path),
        )

        with _StubClipboard() as cb:
            clipboard.copy([source])
            raw = cb.raw

        self.assertIsNotNone(raw, "clipboard was not written to")
        self.assertIn(source_path, raw, "authored asset path was lost during serialization")

    async def test_translate_paste_survives_save_and_reload(self):
        # Simulates the QA reload workflow: paste, save mod.usda, close project,
        # reopen, look at the target. Failure here means the value is wrong
        # *after* the full USD serializer/parser cycle — even if that turns out
        # to be a USD bug rather than ours, we want to know about it.
        source = _make_vec_item(
            self.stage,
            "/SourceSave",
            "xformOp:translate",
            Sdf.ValueTypeNames.Double3,
            Gf.Vec3d(1.0, 2.0, 3.0),
        )
        target = _make_vec_item(
            self.stage,
            "/TargetSave",
            "xformOp:translate",
            Sdf.ValueTypeNames.Double3,
            Gf.Vec3d(0.0, 0.0, 0.0),
        )

        with _StubClipboard():
            clipboard.copy([source])
            clipboard.paste([target])

        # Serialize the root layer to USDA text (what would land in mod.usda),
        # then parse it back into a fresh stage with no in-memory carryover.
        layer_text = self.stage.GetRootLayer().ExportToString()
        reloaded_layer = Sdf.Layer.CreateAnonymous(".usda")
        self.assertTrue(reloaded_layer.ImportFromString(layer_text), "failed to re-parse exported layer")
        reloaded_stage = Usd.Stage.Open(reloaded_layer)

        pasted = reloaded_stage.GetPrimAtPath("/TargetSave").GetAttribute("xformOp:translate").Get()
        self.assertEqual(pasted, Gf.Vec3d(1.0, 2.0, 3.0))

    async def test_clipboard_paste_with_mismatched_attr_name_does_not_modify_target(self):
        # Arrange
        source = _make_vec_item(
            self.stage,
            "/Source",
            "xformOp:translate",
            Sdf.ValueTypeNames.Double3,
            Gf.Vec3d(7.0, 8.0, 9.0),
        )
        target = _make_vec_item(
            self.stage,
            "/Target",
            "xformOp:scale",
            Sdf.ValueTypeNames.Double3,
            Gf.Vec3d(1.0, 1.0, 1.0),
        )

        # Act
        with _StubClipboard():
            clipboard.copy([source])
            clipboard.paste([target])

        # Assert
        self.assertEqual(_read_attr(self.stage, "/Target", "xformOp:scale"), Gf.Vec3d(1.0, 1.0, 1.0))
