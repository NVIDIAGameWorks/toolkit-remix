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

import json
import shutil
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import carb.settings
import carb.tokens
import omni.kit.clipboard
import omni.kit.test
import omni.kit.undo
import omni.ui as ui
import omni.usd
from carb.input import KeyboardInput
from omni.flux.curve_editor.widget.payload import curve_to_payload
from omni.flux.fcurve.widget import FCurve, FCurveKey
from omni.flux.property_widget_builder.model.usd import (
    USDAttributeItem,
    USDAttributeXformItem,
    USDDelegate,
    USDLogicalGroupOutletItem,
    USDModel,
    USDPropertyWidget,
    VirtualUSDAttributeItem,
)
from omni.kit import ui_test
from pxr import Gf, Sdf, Usd, UsdGeom, Vt

__all__ = ["TestRowClipboard"]

_WINDOW_WIDTH = ui.Pixel(640)
_WINDOW_HEIGHT = ui.Pixel(360)
_SOURCE = "/Source"
_TARGETS = ("/TargetA", "/TargetB")


class TestRowClipboard(omni.kit.test.AsyncTestCase):
    """Exercise the shared row setter through real property context menus."""

    async def setUp(self):
        """Restore the operating-system clipboard after each workflow."""
        self.addCleanup(omni.kit.clipboard.copy, omni.kit.clipboard.paste() or "")

    async def test_paste_normal_rows_across_destinations_undo_redo_together(self):
        """Paste several ordinary rows across a selection as one undo action."""
        settings = carb.settings.get_settings()
        setting_path = "/persistent/app/material/dragDropMaterialPath"
        original_path_policy = settings.get(setting_path)
        if original_path_policy is None:
            self.addCleanup(settings.destroy_item, setting_path)
        else:
            self.addCleanup(settings.set, setting_path, original_path_policy)
        settings.set_string(setting_path, "relative")
        async with self.__fixture() as directory:
            (directory / "edits").mkdir()
            edit_layer = Sdf.Layer.CreateNew(str(directory / "edits" / "overrides.usda"))
            self._stage.GetRootLayer().subLayerPaths.append("./edits/overrides.usda")
            self._stage.SetEditTarget(edit_layer)
            texture_directory = directory / "textures"
            texture_directory.mkdir()
            definitions = (
                ("speed", Sdf.ValueTypeNames.Float, 7.0),
                ("count", Sdf.ValueTypeNames.Int, 12),
                ("direction", Sdf.ValueTypeNames.Float3, Gf.Vec3f(1, 2, 3)),
            )
            defaults = {"defaultScalar": 9.0, "defaultVector": Gf.Vec3f(4, 5, 6)}
            asset_values = {
                "assetPosix": Sdf.AssetPath("./blah.png"),
                "assetWindows": Sdf.AssetPath(r".\blah.png"),
                "assetMissing": Sdf.AssetPath((texture_directory / "missing.png").as_posix()),
            }
            texture_paths = [(texture_directory / f"{name}.png").as_posix() for name in ("preview", "icon")]
            for name, path in zip(("preview", "icon"), texture_paths):
                shutil.copyfile(
                    carb.tokens.get_tokens_interface().resolve(f"${{omni.flux.utils.tests}}/data/{name}.png"), path
                )
            for index, path in enumerate((_SOURCE, *_TARGETS)):
                prim = self._stage.DefinePrim(path, "Xform")
                for name, value_type, source_value in definitions:
                    value = source_value if index == 0 else type(source_value)(index + 3)
                    prim.CreateAttribute(name, value_type).Set(value)
                for name, value in defaults.items():
                    attribute = prim.CreateAttribute(
                        name, Sdf.ValueTypeNames.Float3 if isinstance(value, Gf.Vec3f) else Sdf.ValueTypeNames.Float
                    )
                    if index:
                        attribute.Set(type(value)(index + 10))
                for name, source_value in asset_values.items():
                    prim.CreateAttribute(name, Sdf.ValueTypeNames.Asset).Set(
                        source_value if index == 0 else Sdf.AssetPath()
                    )
                prim.CreateAttribute("texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(texture_paths[bool(index)]))
                prim.CreateAttribute("untouched", Sdf.ValueTypeNames.Int).Set(99 if index == 0 else 30 + index)
            names = [*[entry[0] for entry in definitions], *defaults, *asset_values, "texture", "untouched"]
            originals = self.__values(_TARGETS, names)
            source_values = self.__values((_SOURCE,), names)
            original_layer = edit_layer.ExportToString()
            for name in asset_values:
                self.assertEqual(source_values[_SOURCE][name].resolvedPath, "")
            source_rows = [
                USDAttributeItem("", [Sdf.Path(_SOURCE).AppendProperty(name)], default_value=defaults.get(name))
                for name in names
            ]
            target_rows = [
                USDAttributeItem(
                    "", [Sdf.Path(path).AppendProperty(name) for path in _TARGETS], read_only=name == "untouched"
                )
                for name in names
            ]
            for name, source_row, target_row in zip(names, source_rows, target_rows):
                source_row.hidden = target_row.hidden = name in asset_values

            # Copy the source panel, then paste into both destination prims through the same menu action.
            await self.__show(source_rows)
            self.assertEqual(self._model.get_all_items(), [row for row in source_rows if not row.hidden])
            self.assertEqual(self._model.get_all_items(include_hidden=True), source_rows)
            await self.__menu(source_rows[0], "Copy All")
            self.assertTrue(omni.kit.clipboard.paste())
            self.assertEqual(edit_layer.ExportToString(), original_layer)
            await self.__show(target_rows)
            self.assertEqual(self._model.get_all_items(), [row for row in target_rows if not row.hidden])
            self.assertEqual(self._model.get_all_items(include_hidden=True), target_rows)
            texture_model = target_rows[names.index("texture")].value_models[0]
            fields = ui_test.find_all(
                f"{self._window.title}//Frame/**/StringField[*].identifier=='file_texture_string_field'"
            )
            self.assertTrue(any(field.widget.model is texture_model for field in fields))
            omni.kit.undo.clear_stack()
            await self.__menu(target_rows[0], "Paste All")

            copied = {name: value for name, _, value in definitions}
            copied.update(defaults)
            copied.update({name: Sdf.AssetPath("./blah.png") for name in asset_values})
            copied["assetMissing"] = Sdf.AssetPath("../textures/missing.png")
            copied["texture"] = Sdf.AssetPath("../textures/preview.png", str(Path(texture_paths[0])))
            expected = {path: {**originals[path], **copied} for path in _TARGETS}
            self.assertEqual(self.__values(_TARGETS, names), expected)
            self.assertFalse(texture_model.is_set_value_blocked())
            await self.__undo_redo(names, originals, expected)
            self.assertFalse(texture_model.is_set_value_blocked())
            self.assertEqual(self.__values((_SOURCE,), names), source_values)
            for name in defaults:
                self.assertFalse(
                    self._stage.GetAttributeAtPath(Sdf.Path(_SOURCE).AppendProperty(name)).HasAuthoredValue()
                )

    async def test_paste_virtual_vector_without_authored_value_preserves_channel_defaults(self):
        """Copy virtual vector defaults and paste distinct channels without authoring the source."""
        for has_attribute_spec in (False, True):
            with self.subTest(title=f"has_attribute_spec={has_attribute_spec}"):
                async with self.__fixture():
                    name = "scale"
                    default_value = Gf.Vec2f(1, 2)
                    source_prim = self._stage.DefinePrim(_SOURCE, "Xform")
                    if has_attribute_spec:
                        source_prim.CreateAttribute(name, Sdf.ValueTypeNames.Float2)
                    for index, path in enumerate(_TARGETS):
                        prim = self._stage.DefinePrim(path, "Xform")
                        prim.CreateAttribute(name, Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(7 + index, 9 + index))
                    source = VirtualUSDAttributeItem(
                        "",
                        [Sdf.Path(_SOURCE).AppendProperty(name)],
                        value_type_name=Sdf.ValueTypeNames.Float2,
                        default_value=default_value,
                        display_attr_names=["Scale"],
                    )
                    target = USDAttributeItem(
                        "", [Sdf.Path(path).AppendProperty(name) for path in _TARGETS], display_attr_names=["Scale"]
                    )
                    originals = self.__values(_TARGETS, [name])
                    expected = {path: {name: default_value} for path in _TARGETS}
                    original_layer = self._stage.GetRootLayer().ExportToString()

                    # Copy the missing or value-less source through the real row menu.
                    await self.__show([source])
                    await self.__menu(source, "Copy Selected")
                    self.assertEqual(
                        json.loads(omni.kit.clipboard.paste()),
                        [{"properties": [{"name": name, "value": [1, 2]}]}],
                    )
                    self.assertEqual(self._stage.GetRootLayer().ExportToString(), original_layer)

                    # Paste each scalar channel into both destinations, then restore and reapply the values.
                    await self.__show([target])
                    omni.kit.undo.clear_stack()
                    await self.__menu(target, "Paste Selected")
                    self.assertEqual(self.__values(_TARGETS, [name]), expected)
                    await self.__undo_redo([name], originals, expected)
                    source_attribute = source_prim.GetAttribute(name)
                    self.assertEqual(source_attribute.IsValid(), has_attribute_spec)
                    if has_attribute_spec:
                        self.assertFalse(source_attribute.HasAuthoredValue())
                        self.assertIsNone(source_attribute.Get())

    async def test_paste_logical_rows_preserves_groups_and_legacy_values(self):
        """Paste curves, gradients, and button-only outlets without opening editors."""
        for kind in ("curve", "gradient", "outlet"):
            with self.subTest(kind=kind):
                async with self.__fixture():
                    root_layer = self._stage.GetRootLayer()
                    weak_layer = Sdf.Layer.CreateAnonymous("inherited.usda")
                    root_layer.subLayerPaths.append(weak_layer.identifier)
                    bases = ("primvars:motion:x", "primvars:motion:y") if kind == "outlet" else ("primvars:motion",)
                    legacy_names = ("legacySpawn", "legacyTarget")
                    names = []
                    for index, path in enumerate((_SOURCE, *_TARGETS)):
                        self._stage.SetEditTarget(root_layer)
                        self._stage.OverridePrim(path)
                        self._stage.SetEditTarget(root_layer if index == 0 else weak_layer)
                        prim = self._stage.DefinePrim(path, "Xform")
                        for group_index, base in enumerate(bases):
                            if kind == "gradient":
                                payload = {
                                    "times": Vt.DoubleArray([0.0, 0.25, 1.0]),
                                    "values": Vt.Vec4fArray(
                                        [Gf.Vec4f(index, 0, 1, 0.5), Gf.Vec4f(1, index, 0, 1), Gf.Vec4f(0, 1, index, 1)]
                                    ),
                                }
                            else:
                                payload = curve_to_payload(
                                    FCurve(
                                        id=base,
                                        keys=[
                                            FCurveKey(time=0.0, value=1 + index + group_index),
                                            FCurveKey(time=0.25, value=4 + index + group_index),
                                            FCurveKey(time=1.0, value=2 + index + group_index),
                                        ],
                                    )
                                )
                            for suffix, value in payload.items():
                                if kind == "gradient" and suffix == "values":
                                    value_type = Sdf.ValueTypeNames.Color4fArray
                                elif suffix in {"inTangentTypes", "outTangentTypes"}:
                                    value_type = Sdf.ValueTypeNames.TokenArray
                                elif suffix == "tangentBrokens":
                                    value_type = Sdf.ValueTypeNames.BoolArray
                                elif suffix in {"preInfinity", "postInfinity"}:
                                    value_type = Sdf.ValueTypeNames.Token
                                else:
                                    value_type = Sdf.ValueTypeNames.DoubleArray
                                name = f"{base}:{suffix}"
                                prim.CreateAttribute(name, value_type).Set(value)
                                if index == 0:
                                    names.append(name)
                        for offset, name in enumerate(legacy_names):
                            prim.CreateAttribute(name, Sdf.ValueTypeNames.Float).Set(10.0 + index + offset)
                        prim.CreateAttribute("untouched", Sdf.ValueTypeNames.Int).Set(30 + index)
                    self._stage.SetEditTarget(root_layer)
                    stronger_attribute = self._stage.GetAttributeAtPath(
                        Sdf.Path(_TARGETS[1]).AppendProperty(f"{bases[0]}:values")
                    )
                    stronger_attribute.Set(stronger_attribute.Get())
                    stronger_attribute.SetCustomDataByKey("preserved", "existing metadata")
                    original_layer = root_layer.ExportToString()
                    original_weak_layer = weak_layer.ExportToString()
                    originals = self.__values(_TARGETS, [*names, *legacy_names, "untouched"])
                    source_values = self.__values((_SOURCE,), [*names, *legacy_names, "untouched"])
                    panels = []
                    for paths in ((_SOURCE,), _TARGETS):
                        if kind == "outlet":
                            primary = USDLogicalGroupOutletItem(
                                {"display_name": "Motion", "curve_map": {base: base for base in bases}},
                                "",
                                list(paths),
                            )
                            rows = [primary]
                            self.assertEqual(primary.value_models, [])
                        else:
                            rows = [
                                USDAttributeItem("", [Sdf.Path(path).AppendProperty(name) for path in paths])
                                for name in names
                            ]
                            primary = rows[names.index(f"{bases[0]}:values")]
                        primary.logical_group_extra_attribute_names = legacy_names
                        panels.append((rows, primary))

                    # Claimed companions remain part of the primary row even though the menu exposes only that row.
                    await self.__show(panels[0][0])
                    await self.__menu(panels[0][1], "Copy Selected")
                    self.assertEqual(root_layer.ExportToString(), original_layer)
                    await self.__show(panels[1][0])
                    omni.kit.undo.clear_stack()
                    await self.__menu(panels[1][1], "Paste Selected")

                    copied = {name: source_values[_SOURCE][name] for name in (*names, *legacy_names)}
                    expected = {path: {**originals[path], **copied} for path in _TARGETS}
                    self.assertEqual(self.__values(_TARGETS, [*names, *legacy_names, "untouched"]), expected)
                    for path in _TARGETS:
                        self.assertIsNone(
                            root_layer.GetAttributeAtPath(Sdf.Path(path).AppendProperty(f"{bases[0]}:times"))
                        )
                    pasted_layer = root_layer.ExportToString()
                    self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)

                    # Undo must remove pasted opinions so later edits to an inherited value remain visible.
                    omni.kit.undo.undo()
                    await ui_test.human_delay()
                    self.assertEqual(root_layer.ExportToString(), original_layer)
                    self.assertEqual(weak_layer.ExportToString(), original_weak_layer)
                    self.assertEqual(self.__values(_TARGETS, [*names, *legacy_names, "untouched"]), originals)
                    self.assertEqual(list(omni.kit.undo.get_undo_stack()), [])
                    inherited_attribute = self._stage.GetAttributeAtPath(
                        Sdf.Path(_TARGETS[0]).AppendProperty(f"{bases[0]}:values")
                    )
                    inherited_value = inherited_attribute.Get()
                    inherited_value[0] = Gf.Vec4f(0.5, 0.5, 0.5, 0.5) if kind == "gradient" else 20.0
                    with Usd.EditContext(self._stage, weak_layer):
                        inherited_attribute.Set(inherited_value)
                    self.assertEqual(inherited_attribute.Get(), inherited_value)
                    omni.kit.undo.redo()
                    await ui_test.human_delay()
                    self.assertEqual(root_layer.ExportToString(), pasted_layer)
                    self.assertEqual(self.__values(_TARGETS, [*names, *legacy_names, "untouched"]), expected)
                    self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)
                    self.assertEqual(self.__values((_SOURCE,), [*names, *legacy_names, "untouched"]), source_values)

    async def test_paste_linked_position_unlinks_without_broadcasting_components(self):
        """Paste distinct XYZ components, then edit X independently and restore the paste."""
        async with self.__fixture():
            name = "xformOp:translate"
            for path, value in zip((_SOURCE, *_TARGETS), ((1, 2, 3), (5, 5, 5), (8, 8, 8))):
                UsdGeom.Xform.Define(self._stage, path).AddTranslateOp().Set(value)
            source = USDAttributeXformItem(
                "", [Sdf.Path(_SOURCE).AppendProperty(name)], display_attr_names=["Position"]
            )
            target = USDAttributeXformItem(
                "", [Sdf.Path(path).AppendProperty(name) for path in _TARGETS], display_attr_names=["Position"]
            )
            originals = self.__values(_TARGETS, [name])
            expected = {path: {name: Gf.Vec3d(1, 2, 3)} for path in _TARGETS}

            # Enable linking through its real control before pasting distinct copied components.
            await self.__show([source])
            await self.__menu(source, "Copy Selected")
            await self.__show([target])
            links = ui_test.find_all(
                f"{self._window.title}//Frame/**/Image[*].identifier=='linked_drag_field_link_Position'"
            )
            self.assertEqual(len(links), 2)
            await links[0].click()
            await ui_test.human_delay()
            await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
            await ui_test.human_delay()
            self.assertTrue(target.linked_edit_enabled)
            omni.kit.undo.clear_stack()
            await self.__menu(target, "Paste Selected")
            self.assertFalse(target.linked_edit_enabled)
            self.assertEqual(self.__values(_TARGETS, [name]), expected)
            await self.__undo_redo([name], originals, expected)
            self.assertFalse(target.linked_edit_enabled)

            # A subsequent X field edit changes neither Y nor Z on either destination.
            fields = ui_test.find_all(f"{self._window.title}//Frame/**/FloatBoundedDrag[*]")
            field = next(field for field in fields if field.widget.model is target.value_models[0])
            await field.drag_and_drop(field.center + ui_test.Vec2(40, 0))
            await ui_test.human_delay()
            edited_values = self.__values(_TARGETS, [name])
            edited_x = edited_values[_TARGETS[0]][name][0]
            self.assertNotEqual(edited_x, 1.0)
            self.assertEqual(edited_values, {path: {name: Gf.Vec3d(edited_x, 2, 3)} for path in _TARGETS})
            self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 2)
            omni.kit.undo.undo()
            await ui_test.human_delay()
            self.assertEqual(self.__values(_TARGETS, [name]), expected)
            self.assertFalse(target.linked_edit_enabled)

    @asynccontextmanager
    async def __fixture(self):
        async with AsyncExitStack() as cleanup:
            directory = Path(cleanup.enter_context(TemporaryDirectory()))
            root_layer = Sdf.Layer.CreateNew(str(directory / "scene.usda"))
            context = omni.usd.get_context("")
            cleanup.push_async_callback(context.close_stage_async)
            cleanup.callback(omni.kit.undo.clear_stack)
            await context.open_stage_async(root_layer.identifier)
            self._stage = context.get_stage()
            self._model = USDModel(context_name="")
            cleanup.callback(self._model.destroy)
            self._delegate = USDDelegate()
            self._window = ui.Window(f"Row Clipboard {id(self._model)}", width=_WINDOW_WIDTH, height=_WINDOW_HEIGHT)
            cleanup.callback(self._window.destroy)
            with self._window.frame:
                widget = USDPropertyWidget(context_name="", model=self._model, delegate=self._delegate)
                cleanup.callback(widget.destroy)
            yield directory

    async def __show(self, rows):
        self._model.set_items(rows)
        await ui_test.human_delay()

    async def __menu(self, row, action):
        text = row.name_models[0].get_value_as_string()
        label = await ui_test.find_with_retry(f"{self._window.title}//Frame/**/Label[*].text=='{text}'")
        self.assertIsNotNone(label)
        await label.click(right_click=True)
        await ui_test.human_delay()
        await ui_test.menu.select_context_menu(action, offset=ui_test.Vec2(10, 10))
        await ui_test.human_delay()

    def __values(self, paths, names):
        return {
            path: {name: self._stage.GetPrimAtPath(path).GetAttribute(name).Get() for name in names} for path in paths
        }

    async def __undo_redo(self, names, originals, expected):
        self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)
        omni.kit.undo.undo()
        await ui_test.human_delay()
        self.assertEqual(self.__values(_TARGETS, names), originals)
        self.assertFalse(
            any(
                model.is_set_value_blocked()
                for row in self._model.get_all_items(include_hidden=True)
                for model in row.value_models
            )
        )
        self.assertEqual(list(omni.kit.undo.get_undo_stack()), [])
        omni.kit.undo.redo()
        await ui_test.human_delay()
        self.assertEqual(self.__values(_TARGETS, names), expected)
        self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)
