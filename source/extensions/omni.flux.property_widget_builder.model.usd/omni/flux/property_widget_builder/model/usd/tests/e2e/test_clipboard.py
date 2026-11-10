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
import omni.kit.commands
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
    USDAttrListItem,
    USDDelegate,
    USDLogicalGroupOutletItem,
    USDModel,
    USDPropertyWidget,
    VirtualUSDAttributeItem,
    VirtualUSDAttrListItem,
)
from omni.flux.property_widget_builder.model.usd.bounds_adapter import BoundsAdapter
from omni.kit import ui_test
from omni.kit.notification_manager import NotificationStatus, destroy_all_notifications, get_all_notifications
from omni.flux.property_widget_builder.widget.tree.clipboard import AttributeCopyPasteHelper
from pxr import Gf, Sdf, Usd, UsdGeom, Vt

__all__ = ["TestRowClipboard"]

_WINDOW_WIDTH = ui.Pixel(640)
_WINDOW_HEIGHT = ui.Pixel(360)
_SOURCE = "/Source"
_TARGETS = ("/TargetA", "/TargetB")


class TestRowClipboard(omni.kit.test.AsyncTestCase):
    """Exercise the public clipboard API with real USD models, editors, and commands."""

    async def setUp(self):
        """Restore the operating-system clipboard after each workflow."""
        self.addCleanup(omni.kit.clipboard.copy, omni.kit.clipboard.paste() or "")
        self.addCleanup(destroy_all_notifications)
        omni.kit.clipboard.copy("")
        destroy_all_notifications()

    async def test_paste_different_name_numeric_values_preserves_bounds_shape_and_undo(self):
        """Remap one native numeric attribute through the destination editor and grouped undo."""
        for label, value_type, copied, original, soft_min, soft_max, hard_min, hard_max, expected_value in (
            ("float_upper", Sdf.ValueTypeNames.Float, 2.0, 0.25, None, None, 0.0, 1.0, 1.0),
            ("float_lower", Sdf.ValueTypeNames.Float, -2.0, 0.25, None, None, 0.0, 1.0, 0.0),
            ("float_inside", Sdf.ValueTypeNames.Float, 0.75, 0.25, None, None, 0.0, 1.0, 0.75),
            ("float_soft_only", Sdf.ValueTypeNames.Float, 2.0, 0.25, 0.0, 1.0, None, None, 2.0),
            ("integer", Sdf.ValueTypeNames.Int, 5, 2, 0, 10, 1.2, 3.8, 3),
            (
                "vector",
                Sdf.ValueTypeNames.Float3,
                Gf.Vec3f(-2, 0.5, 7),
                Gf.Vec3f(0.25),
                None,
                None,
                [0.0, 0.0, 0.0],
                [1.0, 2.0, 3.0],
                Gf.Vec3f(0, 0.5, 3),
            ),
            (
                "color",
                Sdf.ValueTypeNames.Color3f,
                Gf.Vec3f(1, 0.5, 0.75),
                Gf.Vec3f(0.25),
                None,
                None,
                None,
                None,
                Gf.Vec3f(1, 0.5, 0.75),
            ),
        ):
            with self.subTest(case=label, value_type=str(value_type), hard_min=hard_min, hard_max=hard_max):
                async with self.__fixture():
                    # Give both destination prims the same type under a different property name.
                    attribute = self._stage.DefinePrim(_SOURCE).CreateAttribute("source", value_type)
                    attribute.Set(copied)
                    for path in _TARGETS:
                        self._stage.DefinePrim(path).CreateAttribute("destination", value_type).Set(original)
                    source = USDAttributeItem("", [attribute.GetPath()], display_attr_names=["Source"])
                    target = USDAttributeItem(
                        "",
                        [Sdf.Path(path).AppendProperty("destination") for path in _TARGETS],
                        display_attr_names=["Destination"],
                        bounds_adapter=BoundsAdapter(
                            normalized_data={
                                "soft_min": soft_min,
                                "soft_max": soft_max,
                                "hard_min": hard_min,
                                "hard_max": hard_max,
                                "step": None,
                            }
                        ),
                    )
                    originals = self.__values(_TARGETS, ["destination"])

                    # Only explicit selected-type matching can use the differently named source.
                    await self.__show([source])
                    AttributeCopyPasteHelper.copy(source_rows=[source])
                    await self.__show([target])
                    self.assertFalse(AttributeCopyPasteHelper.can_paste(target_rows=[target]))
                    self.assertTrue(AttributeCopyPasteHelper.can_paste(target_rows=[target], allow_name_mismatch=True))
                    omni.kit.undo.clear_stack()
                    report = AttributeCopyPasteHelper.paste(target_rows=[target], allow_name_mismatch=True)

                    # Hard limits affect values, soft limits do not; native shapes and undo remain intact.
                    expected = {path: {"destination": expected_value} for path in _TARGETS}
                    self.assertEqual(self.__values(_TARGETS, ["destination"]), expected)
                    self.assertEqual(report.submitted_count, 1)
                    if value_type == Sdf.ValueTypeNames.Float:
                        if copied != expected_value:
                            self.assertEqual(len(report.adjustments), 1)
                            self.assertIn(f"{copied} -> {expected_value}", report.adjustments[0])
                        else:
                            self.assertEqual(report.adjustments, [])
                    await self.__undo_redo(["destination"], originals, expected)

    async def test_paste_integer_skips_label_backed_dropdown_and_applies_later_numeric_destination(self):
        """Reject a raw index for a label-backed field without aborting later compatible rows."""
        async with self.__fixture():
            # The dropdown stores an integer in USD but its editor accepts option labels.
            source_attribute = self._stage.DefinePrim(_SOURCE).CreateAttribute("source", Sdf.ValueTypeNames.Int)
            source_attribute.Set(1)
            dropdown_attribute = self._stage.DefinePrim(_TARGETS[0]).CreateAttribute("choice", Sdf.ValueTypeNames.Int)
            dropdown_attribute.Set(0)
            numeric_attribute = self._stage.DefinePrim(_TARGETS[1]).CreateAttribute("number", Sdf.ValueTypeNames.Int)
            numeric_attribute.Set(0)
            source = USDAttributeItem("", [source_attribute.GetPath()])
            dropdown = USDAttrListItem(
                "", [dropdown_attribute.GetPath()], default_value="wrap_clamp", options=["wrap_clamp", "wrap_repeat"]
            )
            numeric = USDAttributeItem("", [numeric_attribute.GetPath()])
            await self.__show([source])
            AttributeCopyPasteHelper.copy(source_rows=[source])
            await self.__show([dropdown, numeric])

            # Incompatible setter representations are ineligible, while the later integer row still pastes.
            self.assertFalse(AttributeCopyPasteHelper.can_paste(target_rows=[dropdown], allow_name_mismatch=True))
            report = AttributeCopyPasteHelper.paste(target_rows=[dropdown, numeric], allow_name_mismatch=True)
            self.assertEqual(dropdown_attribute.Get(), 0)
            self.assertEqual(numeric_attribute.Get(), 1)
            self.assertEqual(report.submitted_count, 1)
            self.assertEqual(report.adjustments, [])
            self.assertIsNone(report.error)

            # An unauthored dropdown still declares its type and transfers its label to a differently named row.
            source = VirtualUSDAttrListItem(
                "",
                [Sdf.Path(_SOURCE).AppendProperty("virtualChoice")],
                default_value="wrap_repeat",
                options=["wrap_clamp", "wrap_repeat"],
                value_type_name=Sdf.ValueTypeNames.Int,
            )
            await self.__show([source])
            AttributeCopyPasteHelper.copy(source_rows=[source])
            await self.__show([dropdown])
            AttributeCopyPasteHelper.paste(target_rows=[dropdown], allow_name_mismatch=True)
            self.assertEqual(dropdown_attribute.Get(), 1)
            self.assertFalse(self._stage.GetAttributeAtPath(f"{_SOURCE}.virtualChoice"))

    async def test_paste_selected_multiple_copied_attributes_does_not_guess_name_mapping(self):
        """Reject ambiguous type-based mapping when several copied floats could supply a destination."""
        async with self.__fixture():
            # Competing copied attributes must not be guessed into one differently named destination.
            source_prim = self._stage.DefinePrim(_SOURCE)
            source_rows = []
            for name, value in (("first", 0.5), ("second", 0.75)):
                attribute = source_prim.CreateAttribute(name, Sdf.ValueTypeNames.Float)
                attribute.Set(value)
                source_rows.append(USDAttributeItem("", [attribute.GetPath()]))
            attribute = self._stage.DefinePrim(_TARGETS[0]).CreateAttribute("destination", Sdf.ValueTypeNames.Float)
            attribute.Set(0.25)
            target = USDAttributeItem("", [attribute.GetPath()])
            # Attempt the ambiguous paste through the public API without modifying its target.
            await self.__show(source_rows)
            AttributeCopyPasteHelper.copy(source_rows=source_rows)
            await self.__show([target])
            self.assertFalse(AttributeCopyPasteHelper.can_paste(target_rows=[target], allow_name_mismatch=True))
            report = AttributeCopyPasteHelper.paste(target_rows=[target], allow_name_mismatch=True)
            self.assertEqual(attribute.Get(), 0.25)
            self.assertEqual(report.submitted_count, 0)
            self.assertEqual(report.unmatched, ["first", "second"])

    async def test_paste_invalid_or_clamped_values_reports_stored_usd_values_and_details(self):
        """Verify authored values and validation feedback through real USD editors and paste menus."""
        for action, copied, unmatched in (
            ("Paste Selected", "invalid", False),
            ("Paste Selected", 2.0, False),
            ("Paste Selected", 2.0, True),
            ("Paste All", 2.0, True),
        ):
            with self.subTest(action=action, copied=copied, unmatched=unmatched):
                destroy_all_notifications()
                async with self.__fixture():
                    # Copy real source attributes, including a property absent from the destination when requested.
                    prim = self._stage.DefinePrim(_SOURCE)
                    value_type = Sdf.ValueTypeNames.String if isinstance(copied, str) else Sdf.ValueTypeNames.Float
                    attribute = prim.CreateAttribute("bounded", value_type)
                    attribute.Set(copied)
                    source = [USDAttributeItem("", [attribute.GetPath()])]
                    if unmatched:
                        unmatched_names = (
                            [f"sourceOnly{index:02d}" for index in range(30)]
                            if action == "Paste All"
                            else ["sourceOnly"]
                        )
                        if action == "Paste All":
                            unmatched_names[-1] += "_nested_directory" * 30 + "_Texture"
                        for name in unmatched_names:
                            attribute = prim.CreateAttribute(name, Sdf.ValueTypeNames.Float)
                            attribute.Set(5.0)
                            source.append(USDAttributeItem("", [attribute.GetPath()]))
                    await self.__show(source)
                    await self.__menu(source[0], "Copy All")

                    # Give rejected destinations distinct labels while retaining the same canonical identity.
                    labels = ("First target", "Second target") if copied == "invalid" else ("bounded",)
                    targets = []
                    destinations = []
                    for path, label in zip(_TARGETS, labels):
                        destination = self._stage.DefinePrim(path).CreateAttribute("bounded", Sdf.ValueTypeNames.Float)
                        destination.Set(0.25)
                        destinations.append(destination)
                        targets.append(
                            USDAttributeItem(
                                "",
                                [destination.GetPath()],
                                display_attr_names=[label],
                                bounds_adapter=BoundsAdapter(
                                    normalized_data={
                                        "soft_min": None,
                                        "soft_max": None,
                                        "hard_min": 0.0,
                                        "hard_max": 1.0,
                                        "step": None,
                                    }
                                ),
                            )
                        )
                    await self.__show(targets)
                    if copied == "invalid":
                        # One invalid source reports each real destination without weakening exact type matching.
                        report = AttributeCopyPasteHelper.paste(target_rows=targets, allow_name_mismatch=True)
                    else:
                        # Valid numeric input still passes through the native editor's context-menu action.
                        await self.__menu(targets[0], action)

                    # One warning describes the result, and USD retains either the original or clamped value.
                    notifications = await self.__notifications()
                    self.assertEqual(len(notifications), 1)
                    self.assertEqual(notifications[0].info.status, NotificationStatus.WARNING)
                    if copied == "invalid":
                        self.assertEqual([attribute.Get() for attribute in destinations], [0.25, 0.25])
                        self.assertEqual(len(report.diagnostics), 2)
                        self.assertIn("skipped 2", report.message)
                        self.assertIn("skipped 2", notifications[0].info.text)
                        await self.__open_notification_details()
                        title = "Properties could not be pasted"
                        field = await ui_test.find_with_retry(
                            f"{title}//Frame/**/Label[*].identifier=='error_popup_details'"
                        )
                        self.assertIn("Invalid numeric value", field.widget.text)
                        for label in labels:
                            self.assertTrue(any(label in diagnostic for diagnostic in report.diagnostics))
                            self.assertIn(label, report.details)
                            self.assertIn(label, field.widget.text)
                        await self.__close_prompt(title)
                        continue
                    self.assertEqual(destinations[0].Get(), 1.0)
                    self.assertIn("limit", notifications[0].info.text)
                    if unmatched:
                        self.assertIn("Submitted 1", notifications[0].info.text)
                        self.assertIn(f"skipped {len(unmatched_names)}", notifications[0].info.text)
                    if action == "Paste All":
                        # Partial Paste All offers Details with both the skipped identity and the adjustment.
                        await self.__open_notification_details()
                        field = await ui_test.find_with_retry(
                            "Skipped properties//Frame/**/Label[*].identifier=='error_popup_details'"
                        )
                        self.assertIn(unmatched_names[0], field.widget.text)
                        self.assertIn(unmatched_names[-1], field.widget.text)
                        self.assertIn("2.0 -> 1.0", field.widget.text)
                        # Scroll a material-sized report and copy its complete text without display wrapping.
                        scroll = ui_test.find(
                            "Skipped properties//Frame/**/ScrollingFrame[*].identifier=='error_popup_details_scroll'"
                        )
                        await ui_test.emulate_mouse_move(
                            ui_test.Vec2(scroll.widget.screen_position_x + 20, scroll.widget.screen_position_y + 20)
                        )
                        await ui_test.human_delay()
                        for _ in range(20):
                            await ui_test.input.emulate_mouse_scroll(ui_test.Vec2(0, -1200))
                            await ui_test.human_delay()
                            if scroll.widget.scroll_y >= scroll.widget.scroll_y_max:
                                break
                        self.assertGreater(scroll.widget.scroll_y, 0)
                        self.assertEqual(scroll.widget.scroll_y, scroll.widget.scroll_y_max)
                        await ui_test.find(
                            "Skipped properties//Frame/**/Button[*].identifier=='error_popup_copy_details'"
                        ).click()
                        await ui_test.human_delay()
                        self.assertEqual(omni.kit.clipboard.paste(), field.widget.text)
                        await self.__close_prompt("Skipped properties")
                    else:
                        # Selected paste explains the clamp directly, without an extra Details action.
                        self.assertEqual(notifications[0].info.button_infos, [])
                        self.assertIn("2.0 -> 1.0", notifications[0].info.text)
                        if not unmatched:
                            # Menu availability uses its snapshot; the click must read the latest clipboard.
                            for content in ("", '[{"properties": [{"name": "other", "value": 9}]}]'):
                                destroy_all_notifications()
                                AttributeCopyPasteHelper.copy(source_rows=source)
                                label = await ui_test.find_with_retry(
                                    f"{self._window.title}//Frame/**/Label[*].text=='bounded'"
                                )
                                await label.click(right_click=True)
                                await ui_test.human_delay()
                                menu = await ui_test.menu.get_context_menu()
                                self.assertIn("Paste Selected", menu["_"])
                                omni.kit.clipboard.copy(content)
                                await ui_test.menu.select_context_menu("Paste Selected", offset=ui_test.Vec2(10, 10))
                                await ui_test.human_delay()
                                self.assertEqual(destinations[0].Get(), 1.0)
                                if content:
                                    notifications = await self.__notifications()
                                    self.assertEqual(len(notifications), 1)
                                    self.assertEqual(notifications[0].info.status, NotificationStatus.WARNING)
                                    self.assertEqual(notifications[0].info.text, "No matching attributes found.")
                                    self.assertEqual(notifications[0].info.button_infos, [])
                                else:
                                    self.assertEqual(get_all_notifications(), [])

    async def test_paste_different_name_and_value_type_is_rejected(self):
        """Do not convert floats to integers, booleans, or a different USD numeric precision."""
        for value_type, original in (
            (Sdf.ValueTypeNames.Int, 3),
            (Sdf.ValueTypeNames.Bool, False),
            (Sdf.ValueTypeNames.Double, 0.25),
        ):
            with self.subTest(destination_type=str(value_type)):
                async with self.__fixture():
                    # Matching numeric families still require the exact declared USD type.
                    attribute = self._stage.DefinePrim(_SOURCE).CreateAttribute("source", Sdf.ValueTypeNames.Float)
                    attribute.Set(2.0)
                    destination = self._stage.DefinePrim(_TARGETS[0]).CreateAttribute("destination", value_type)
                    destination.Set(original)
                    source = USDAttributeItem("", [attribute.GetPath()])
                    target = USDAttributeItem("", [destination.GetPath()])
                    await self.__show([source])
                    AttributeCopyPasteHelper.copy(source_rows=[source])
                    await self.__show([target])
                    # The incompatible paste stays unavailable and an explicit API attempt leaves the value intact.
                    self.assertFalse(AttributeCopyPasteHelper.can_paste(target_rows=[target], allow_name_mismatch=True))
                    report = AttributeCopyPasteHelper.paste(target_rows=[target], allow_name_mismatch=True)
                    self.assertEqual(destination.Get(), original)
                    self.assertEqual(report.submitted_count, 0)
                    self.assertEqual(report.unmatched, ["source"])

    async def test_paste_command_failure_reports_real_usd_error_details_and_successful_retry_stays_quiet(self):
        """Use production USD writers for callback errors, menu feedback, and a successful retry."""
        async with self.__fixture():
            source_attribute = self._stage.DefinePrim(_SOURCE).CreateAttribute("value", Sdf.ValueTypeNames.Color3f)
            source_attribute.Set(Gf.Vec3f(1, 0, 0))
            destination_attribute = self._stage.DefinePrim(_TARGETS[0]).CreateAttribute(
                "value", Sdf.ValueTypeNames.Color3f
            )
            original = Gf.Vec3f(0.25, 0.5, 0.75)
            destination_attribute.Set(original)
            source = USDAttributeItem("", [source_attribute.GetPath()])
            destination = USDAttributeItem("", [destination_attribute.GetPath()])

            # Copy a valid color before locking its destination layer against writes.
            await self.__show([source])
            await self.__menu(source, "Copy Selected")
            await self.__show([destination])
            layer = self._stage.GetRootLayer()
            logging_enabled = omni.kit.commands.command.LOGGING_ENABLED
            omni.kit.commands.set_logging_enabled(False)
            try:
                layer.SetPermissionToEdit(False)
                # API and menu callers receive the same report without an exception escaping the edit callback.
                report = AttributeCopyPasteHelper.paste(target_rows=[destination])
                self.assertIn("USD property write failed", report.error)
                self.assertIn("Traceback", report.error)
                self.assertEqual(destination_attribute.Get(), original)
                self.assertEqual(destination.value_models[0].get_value(), original)
                notifications = await self.__notifications()
                self.assertEqual(len(notifications), 1)
                self.assertEqual(notifications[0].info.status, NotificationStatus.WARNING)
                self.assertIn("failed", notifications[0].info.text.lower())
                destroy_all_notifications()

                # The actual Paste Selected menu shows a warning and opens the native writer's Details.
                await self.__menu(destination, "Paste Selected")
                notifications = await self.__notifications()
                self.assertEqual(len(notifications), 1)
                self.assertEqual(notifications[0].info.status, NotificationStatus.WARNING)
                self.assertIn("failed", notifications[0].info.text.lower())
                self.assertEqual(destination_attribute.Get(), original)
                await self.__open_notification_details()
                field = await ui_test.find_with_retry(
                    "Paste failed//Frame/**/Label[*].identifier=='error_popup_details'"
                )
                self.assertIn(str(destination_attribute.GetPath()), field.widget.text)
                self.assertIn("Console", field.widget.text)
                await self.__close_prompt("Paste failed")
            finally:
                layer.SetPermissionToEdit(True)
                omni.kit.commands.set_logging_enabled(logging_enabled)
            destroy_all_notifications()

            # A later valid menu paste succeeds without repeating the earlier failed write's warning.
            source_attribute = source_attribute.GetPrim().CreateAttribute("roughness", Sdf.ValueTypeNames.Float)
            source_attribute.Set(0.75)
            destination_attribute = destination_attribute.GetPrim().CreateAttribute(
                "roughness", Sdf.ValueTypeNames.Float
            )
            destination_attribute.Set(0.25)
            source = USDAttributeItem("", [source_attribute.GetPath()])
            destination = USDAttributeItem("", [destination_attribute.GetPath()])
            await self.__show([source])
            await self.__menu(source, "Copy Selected")
            await self.__show([destination])
            await self.__menu(destination, "Paste Selected")
            self.assertEqual(destination_attribute.Get(), 0.75)
            self.assertEqual(get_all_notifications(), [])

    async def test_paste_referenced_texture_preserves_source_location_and_undo_redo(self):
        """Transfer differently named textures and persist source identity using the destination path policy."""
        settings = carb.settings.get_settings()
        policy = "/persistent/app/material/dragDropMaterialPath"
        original_policy = settings.get(policy)
        if original_policy is None:
            self.addCleanup(settings.destroy_item, policy)
        else:
            self.addCleanup(settings.set, policy, original_policy)
        for path_policy in ("relative", "absolute"):
            with self.subTest(path_policy=path_policy):
                settings.set_string(policy, path_policy)
                async with self.__fixture() as directory:
                    source_directory = directory / "assets" / "models"
                    texture_directory = source_directory / "textures"
                    texture_directory.mkdir(parents=True)
                    texture_path = texture_directory / "preview.png"
                    shutil.copyfile(
                        carb.tokens.get_tokens_interface().resolve("${omni.flux.utils.tests}/data/preview.png"),
                        texture_path,
                    )
                    source_stage = Usd.Stage.CreateNew(str(source_directory / "material.usda"))
                    source_prim = source_stage.DefinePrim("/Material", "Shader")
                    source_prim.CreateAttribute("texture", Sdf.ValueTypeNames.Asset).Set(
                        Sdf.AssetPath("./textures/preview.png")
                    )
                    source_prim.GetAttribute("texture").SetMetadata("colorSpace", "sRGB")
                    source_stage.GetRootLayer().Save()
                    self._stage.DefinePrim(_SOURCE).GetReferences().AddReference(
                        "./assets/models/material.usda", "/Material"
                    )
                    self._stage.GetAttributeAtPath(f"{_SOURCE}.texture").SetCustomDataByKey(
                        "preserved", "metadata override"
                    )
                    (directory / "edits").mkdir()
                    edit_layer = Sdf.Layer.CreateNew(str(directory / "edits" / "overrides.usda"))
                    self._stage.GetRootLayer().subLayerPaths.append("./edits/overrides.usda")
                    self._stage.SetEditTarget(edit_layer)
                    for target in _TARGETS:
                        self._stage.DefinePrim(target, "Shader").CreateAttribute(
                            "destinationTexture", Sdf.ValueTypeNames.Asset
                        ).Set(Sdf.AssetPath())
                        self._stage.GetAttributeAtPath(f"{target}.destinationTexture").SetMetadata("colorSpace", "sRGB")
                    source = USDAttributeItem(
                        "", [Sdf.Path(_SOURCE).AppendProperty("texture")], display_attr_names=["Shared texture label"]
                    )
                    target = USDAttributeItem(
                        "",
                        [Sdf.Path(path).AppendProperty("destinationTexture") for path in _TARGETS],
                        display_attr_names=["Shared texture label"],
                    )
                    source_value = self._stage.GetAttributeAtPath(f"{_SOURCE}.texture").Get()
                    self.assertEqual(Path(source_value.resolvedPath), texture_path)
                    originals = self.__values(_TARGETS, ["destinationTexture"])

                    # Copy resolves the referenced asset before discarding the source material context.
                    await self.__show([source])
                    AttributeCopyPasteHelper.copy(source_rows=[source])
                    copied_asset = json.loads(omni.kit.clipboard.paste())[0]["properties"][0]["value"]
                    self.assertEqual(Path(copied_asset["_value"]), texture_path)

                    # Paste honors the destination path policy while passing the absolute source string to callbacks.
                    await self.__show([target])
                    self.assertFalse(AttributeCopyPasteHelper.can_paste(target_rows=[target]))
                    report = AttributeCopyPasteHelper.paste(target_rows=[target])
                    self.assertEqual(report.unmatched, ["texture"])
                    self.assertEqual(self.__values(_TARGETS, ["destinationTexture"]), originals)
                    destroy_all_notifications()
                    self.assertTrue(AttributeCopyPasteHelper.can_paste(target_rows=[target], allow_name_mismatch=True))

                    def validate_texture_path(setter, value, texture_path=texture_path, target=target):
                        """Check the material callback's string-path API without replacing the authored path."""
                        self.assertIsInstance(value, str)
                        self.assertEqual(Path(value), texture_path)
                        outcome = setter(value)
                        self.assertEqual(outcome.value, target.value_models[0].get_value_as_string())
                        return outcome

                    target.value_models[0].set_callback_pre_set_value(validate_texture_path)
                    omni.kit.undo.clear_stack()
                    AttributeCopyPasteHelper.paste(target_rows=[target], allow_name_mismatch=True)
                    authored_path = (
                        "../assets/models/textures/preview.png"
                        if path_policy == "relative"
                        else texture_path.as_posix()
                    )
                    expected = {
                        path: {"destinationTexture": Sdf.AssetPath(authored_path, str(texture_path))}
                        for path in _TARGETS
                    }
                    self.assertEqual(self.__values(_TARGETS, ["destinationTexture"]), expected)
                    for target_path in _TARGETS:
                        self.assertEqual(
                            edit_layer.GetAttributeAtPath(f"{target_path}.destinationTexture").default.path,
                            authored_path,
                        )
                    await self.__undo_redo(["destinationTexture"], originals, expected)
                    self.assertEqual(self._stage.GetAttributeAtPath(f"{_SOURCE}.texture").Get(), source_value)

                    # Save the composed scene before exercising an independent clear and its undo history.
                    root_layer = self._stage.GetRootLayer()
                    root_layer.Save()
                    edit_layer.Save()

                    # An empty copied asset still clears the existing textures and can be undone.
                    target.value_models[0].set_callback_pre_set_value(None)
                    self._stage.GetAttributeAtPath(f"{_SOURCE}.texture").Set(Sdf.AssetPath())
                    await self.__show([source])
                    AttributeCopyPasteHelper.copy(source_rows=[source])
                    await self.__show([target])
                    omni.kit.undo.clear_stack()
                    AttributeCopyPasteHelper.paste(target_rows=[target], allow_name_mismatch=True)
                    self.assertEqual(self.__values(_TARGETS, ["destinationTexture"]), originals)
                    await self.__undo_redo(["destinationTexture"], expected, originals)

                    # Reopen saved layers from disk, retaining the relative layer reference and original texture location.
                    await self.__show([])
                    context = omni.usd.get_context("")
                    await context.close_stage_async()
                    root_layer.Reload()
                    edit_layer.Reload()
                    await context.open_stage_async(root_layer.identifier)
                    self._stage = context.get_stage()
                    self.assertEqual(list(self._stage.GetRootLayer().subLayerPaths), ["./edits/overrides.usda"])
                    self.assertEqual(self.__values(_TARGETS, ["destinationTexture"]), expected)
                    self.assertEqual(self._stage.GetAttributeAtPath(f"{_SOURCE}.texture").Get(), source_value)
                    for target_path in _TARGETS:
                        self.assertEqual(
                            edit_layer.GetAttributeAtPath(f"{target_path}.destinationTexture").default.path,
                            authored_path,
                        )

    async def test_paste_texture_to_session_prim_keeps_absolute_path_when_edit_target_is_on_disk(self):
        """Keep a texture resolvable when its actual receiving layer has no filesystem anchor."""
        settings = carb.settings.get_settings()
        policy = "/persistent/app/material/dragDropMaterialPath"
        original_policy = settings.get(policy)
        if original_policy is None:
            self.addCleanup(settings.destroy_item, policy)
        else:
            self.addCleanup(settings.set, policy, original_policy)
        settings.set_string(policy, "relative")
        async with self.__fixture() as directory:
            # The source texture is anchored on disk, while the destination prim is defined in session state.
            texture_path = directory / "preview.png"
            shutil.copyfile(
                carb.tokens.get_tokens_interface().resolve("${omni.flux.utils.tests}/data/preview.png"), texture_path
            )
            source_attribute = self._stage.DefinePrim(_SOURCE, "Shader").CreateAttribute(
                "texture", Sdf.ValueTypeNames.Asset
            )
            source_attribute.Set(Sdf.AssetPath("./preview.png"))
            root_layer = self._stage.GetRootLayer()
            session_layer = self._stage.GetSessionLayer()
            with Usd.EditContext(self._stage, session_layer):
                destination = self._stage.DefinePrim(_TARGETS[0], "Shader").CreateAttribute(
                    "texture", Sdf.ValueTypeNames.Asset
                )
                destination.Set(Sdf.AssetPath())
                destination.SetMetadata("colorSpace", "sRGB")
            source = USDAttributeItem("", [source_attribute.GetPath()])
            target = USDAttributeItem("", [destination.GetPath()])
            self.assertTrue(session_layer.anonymous)
            self.assertEqual(self._stage.GetEditTarget().GetLayer(), root_layer)

            # Paste through the public API with relative policy and a different effective receiving layer.
            await self.__show([source])
            AttributeCopyPasteHelper.copy(source_rows=[source])
            await self.__show([target])
            report = AttributeCopyPasteHelper.paste(target_rows=[target])

            # Anonymous layers retain the absolute source identity without leaving a shadowed disk opinion.
            self.assertEqual(report.submitted_count, 1)
            self.assertEqual(report.diagnostics, [])
            self.assertEqual(
                session_layer.GetAttributeAtPath(destination.GetPath()).default.path, texture_path.as_posix()
            )
            self.assertEqual(Path(destination.Get().resolvedPath), texture_path)
            self.assertIsNone(root_layer.GetAttributeAtPath(destination.GetPath()))

            # Existing copy callbacks can return paths relative to the disk edit target before the session write.
            target.set_row_values(("",))
            outcome = target.value_models[0].set_value("./preview.png")
            self.assertEqual(outcome.value, texture_path.as_posix())
            self.assertEqual(
                session_layer.GetAttributeAtPath(destination.GetPath()).default.path, texture_path.as_posix()
            )
            self.assertEqual(Path(destination.Get().resolvedPath), texture_path)

    async def test_paste_invalid_texture_skips_asset_and_reports_reason_while_applying_other_properties(self):
        """Preserve valid matches and report diagnostic reasons for unanchored or missing textures."""
        for unanchored in (True, False):
            with self.subTest(source="anonymous capture" if unanchored else "missing file"):
                async with self.__fixture() as directory:
                    layer = self._stage.GetRootLayer()
                    if unanchored:
                        layer = Sdf.Layer.CreateAnonymous("capture.usda")
                        self._stage.GetRootLayer().subLayerPaths.append(layer.identifier)
                    asset_path = "./textures/unresolved.png" if unanchored else (directory / "missing.png").as_posix()
                    with Usd.EditContext(self._stage, layer):
                        prim = self._stage.DefinePrim(_SOURCE, "Shader")
                        prim.CreateAttribute("texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(asset_path))
                        prim.CreateAttribute("roughness", Sdf.ValueTypeNames.Float).Set(0.75)
                    for path in _TARGETS:
                        prim = self._stage.DefinePrim(path, "Shader")
                        prim.CreateAttribute("texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath())
                        prim.CreateAttribute("roughness", Sdf.ValueTypeNames.Float).Set(0.25)
                    if not unanchored:
                        for path in (_SOURCE, *_TARGETS):
                            self._stage.GetAttributeAtPath(f"{path}.texture").SetMetadata("colorSpace", "sRGB")
                    names = ["texture", "roughness"]
                    originals = self.__values(_TARGETS, names)
                    source_rows = [USDAttributeItem("", [Sdf.Path(_SOURCE).AppendProperty(name)]) for name in names]
                    target_rows = [
                        USDAttributeItem("", [Sdf.Path(path).AppendProperty(name) for path in _TARGETS])
                        for name in names
                    ]
                    source_rows[0].hidden = target_rows[0].hidden = not unanchored
                    # Hidden asset rows still participate without opening a preview for a missing texture.
                    await self.__show(source_rows)
                    AttributeCopyPasteHelper.copy(source_rows=source_rows)
                    await self.__show(target_rows)
                    omni.kit.undo.clear_stack()
                    report = AttributeCopyPasteHelper.paste(target_rows=target_rows)

                    expected = {path: {**originals[path], "roughness": 0.75} for path in _TARGETS}
                    self.assertEqual(self.__values(_TARGETS, names), expected)
                    self.assertEqual(report.submitted_count, 1)
                    self.assertEqual(report.unmatched, [])
                    self.assertEqual(len(report.diagnostics), 1)
                    diagnostic = report.diagnostics[0]
                    self.assertIn("texture", diagnostic)
                    self.assertIn(asset_path, diagnostic)
                    self.assertIn("could not be resolved" if unanchored else "missing or unreadable", diagnostic)
                    if not unanchored:
                        self.assertIn("scene.usda", diagnostic)
                    await self.__undo_redo(names, originals, expected)

                    if not unanchored:
                        # An already-authored missing reference is unchanged and must not be rejected on retry.
                        unchanged_path = omni.usd.make_path_relative_to_current_edit_target(
                            asset_path, stage=self._stage
                        )
                        for path in _TARGETS:
                            self._stage.GetAttributeAtPath(f"{path}.texture").Set(Sdf.AssetPath(unchanged_path))
                        await self.__show(target_rows)
                        authored = self._stage.GetRootLayer().ExportToString()
                        report = AttributeCopyPasteHelper.paste(target_rows=target_rows)
                        self.assertEqual(report.diagnostics, [])
                        self.assertIsNone(report.error)
                        self.assertEqual(self._stage.GetRootLayer().ExportToString(), authored)

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

            # The public clipboard API transfers the source panel to both destination prims.
            await self.__show(source_rows)
            self.assertEqual(self._model.get_all_items(), [row for row in source_rows if not row.hidden])
            self.assertEqual(self._model.get_all_items(include_hidden=True), source_rows)
            AttributeCopyPasteHelper.copy(source_rows=source_rows)
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
            AttributeCopyPasteHelper.paste(target_rows=target_rows)

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
                    target_name = "destinationScale"
                    default_value = Gf.Vec2f(1, 2)
                    source_prim = self._stage.DefinePrim(_SOURCE, "Xform")
                    if has_attribute_spec:
                        source_prim.CreateAttribute(name, Sdf.ValueTypeNames.Float2)
                    for index, path in enumerate(_TARGETS):
                        prim = self._stage.DefinePrim(path, "Xform")
                        prim.CreateAttribute(target_name, Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(7 + index, 9 + index))
                    source = VirtualUSDAttributeItem(
                        "",
                        [Sdf.Path(_SOURCE).AppendProperty(name)],
                        value_type_name=Sdf.ValueTypeNames.Float2,
                        default_value=default_value,
                        display_attr_names=["Scale"],
                    )
                    target = USDAttributeItem(
                        "",
                        [Sdf.Path(path).AppendProperty(target_name) for path in _TARGETS],
                        display_attr_names=["Scale"],
                    )
                    originals = self.__values(_TARGETS, [target_name])
                    expected = {path: {target_name: default_value} for path in _TARGETS}
                    original_layer = self._stage.GetRootLayer().ExportToString()

                    # Reading a missing or value-less source must preserve its unauthored state.
                    await self.__show([source])
                    AttributeCopyPasteHelper.copy(source_rows=[source])
                    self.assertEqual(
                        json.loads(omni.kit.clipboard.paste()),
                        [{"properties": [{"name": name, "value": [1, 2]}], "type_name": "float2"}],
                    )
                    self.assertEqual(self._stage.GetRootLayer().ExportToString(), original_layer)

                    # Paste each scalar channel into both destinations, then restore and reapply the values.
                    await self.__show([target])
                    omni.kit.undo.clear_stack()
                    AttributeCopyPasteHelper.paste(target_rows=[target], allow_name_mismatch=True)
                    self.assertEqual(self.__values(_TARGETS, [target_name]), expected)
                    await self.__undo_redo([target_name], originals, expected)
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

                    # Claim resolution supplies the logical primary with its complete backing values.
                    await self.__show(panels[0][0])
                    AttributeCopyPasteHelper.copy(source_rows=[panels[0][1]])
                    self.assertEqual(root_layer.ExportToString(), original_layer)
                    await self.__show(panels[1][0])
                    omni.kit.undo.clear_stack()
                    AttributeCopyPasteHelper.paste(target_rows=[panels[1][1]], allow_name_mismatch=True)

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
            cleanup.callback(self._delegate.destroy)
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

    async def __notifications(self):
        for _ in range(30):
            notifications = get_all_notifications()
            if notifications:
                return notifications
            await ui_test.human_delay()
        raise AssertionError("Paste notification did not appear")

    async def __close_prompt(self, title):
        acknowledge = next(
            button
            for button in ui_test.find_all(f"{title}//Frame/**/Button[*]")
            if button.widget.text in ("OK", "Okay")
        )
        await acknowledge.click()
        await ui_test.human_delay()

    async def __open_notification_details(self):
        for _ in range(30):
            buttons = [
                button
                for window in ui.Workspace.get_windows()
                if window.visible
                for button in ui_test.find_all(f"{window.title}//Frame/**/Button[*].text=='Details'")
            ]
            if buttons:
                self.assertEqual(len(buttons), 1)
                await buttons[0].click()
                await ui_test.human_delay()
                return
            await ui_test.human_delay()
        self.fail("Notification Details button did not appear")

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
