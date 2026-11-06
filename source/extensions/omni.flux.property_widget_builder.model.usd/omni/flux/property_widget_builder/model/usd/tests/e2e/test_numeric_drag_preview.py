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

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

import omni.kit.test
import omni.kit.undo
import omni.ui as ui
import omni.usd
from carb.input import KEYBOARD_MODIFIER_FLAG_CONTROL, KeyboardInput, MouseEventType
from omni.flux.property_widget_builder.model.usd import (
    USDAttributeItem,
    USDAttributeXformItem,
    USDDelegate,
    USDModel,
    USDPropertyWidget,
    get_usd_listener_instance,
)
from omni.flux.utils.common.interactive_usd_notices import register_objects_changed_listener
from omni.kit import ui_test
from pxr import Sdf, Tf, Usd, UsdGeom, UsdLux, UsdShade

__all__ = ["TestNumericDragPreview"]

_TEST_WINDOW_WIDTH = ui.Pixel(600)
_TEST_WINDOW_HEIGHT = ui.Pixel(200)


class TestNumericDragPreview(omni.kit.test.AsyncTestCase):
    """Exercise numeric edits and live previews through real USD property fields."""

    @asynccontextmanager
    async def __numeric_widget(self):
        context = omni.usd.get_context("")
        async with AsyncExitStack() as cleanup:
            cleanup.push_async_callback(context.close_stage_async)
            cleanup.callback(omni.kit.undo.clear_stack)
            await context.new_stage_async()
            window = ui.Window("Numeric drag steps", width=_TEST_WINDOW_WIDTH, height=_TEST_WINDOW_HEIGHT)
            cleanup.callback(window.destroy)
            model = USDModel(context_name="")
            cleanup.callback(model.destroy)
            with window.frame:
                widget = USDPropertyWidget(context_name="", model=model, delegate=USDDelegate())
                cleanup.callback(widget.destroy)
            listener = get_usd_listener_instance()
            self.assertIsNotNone(listener)
            listener.add_model(model)
            cleanup.callback(listener.remove_model, model)
            await ui_test.human_delay()
            try:
                yield context.get_stage(), window, model
            finally:
                await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
                await ui_test.human_delay()

    def __float_drag(self, window, item):
        identifier = ",".join(str(path) for path in item.attribute_paths)
        query = f"{window.title}//Frame/**/FloatBoundedDrag[*].identifier=='{identifier}'"
        fields = ui_test.find_all(query)
        self.assertEqual(len(fields), 1)
        return fields[0]

    async def __drag_field(self, window, item, model):
        # Focus empty space so a previous edit cannot turn the gesture into a double-click.
        await ui_test.emulate_mouse_move_and_click(
            ui_test.Vec2(window.position_x + 20, window.position_y + window.height - 20)
        )
        await ui_test.human_delay()
        start = self.__float_drag(window, item).center
        await ui_test.emulate_mouse_drag_and_drop(start, start + ui_test.Vec2(30, 0))
        await ui_test.human_delay()
        if model._pending_property_edit_finish_task is not None:
            await asyncio.wait_for(model._pending_property_edit_finish_task, timeout=5)

    async def __type_value(self, window, item, model, text):
        # Native Ctrl-click text entry does not depend on the preceding drag's click history.
        field = self.__float_drag(window, item)
        await field.click()
        await ui_test.human_delay()
        async with ui_test.KeyDownScope(KeyboardInput.LEFT_CONTROL):
            await field.click()
            await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.A, KEYBOARD_MODIFIER_FLAG_CONTROL)
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.BACKSPACE)
        await ui_test.human_delay()
        await ui_test.emulate_char_press(text)
        await ui_test.human_delay()
        await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
        await ui_test.human_delay()
        if model._pending_property_edit_finish_task is not None:
            await asyncio.wait_for(model._pending_property_edit_finish_task, timeout=5)

    async def test_edit_light_and_emissive_properties_preserves_steps_overrides_and_undo(self):
        """Fine edits, metadata overrides, and mixed light selections remain independent and undoable."""
        async with self.__numeric_widget() as (stage, window, model):
            cases = (
                ("/Distant", UsdLux.DistantLight, "inputs:intensity", 25.0, 0.1),
                ("/Sphere", UsdLux.SphereLight, "inputs:intensity", 2500.0, 0.5),
                ("/Radius", UsdLux.SphereLight, "inputs:radius", 1.0, 0.1),
                ("/Material", UsdShade.Shader, "inputs:emissive_intensity", 1.0, 0.1),
                ("/CompanionLight", UsdLux.DistantLight, "inputs:intensity", 2500.0, 0.1),
                ("/CompanionMaterial", UsdShade.Shader, "inputs:emissive_intensity", 1.0, 0.1),
            )
            attributes = {}
            for path, schema, attribute_name, initial_value, _step in cases:
                prim = schema.Define(stage, path).GetPrim()
                attribute = prim.CreateAttribute(attribute_name, Sdf.ValueTypeNames.Float, custom=False)
                attribute.Set(initial_value)
                attributes[path] = attribute
            model.set_prim_paths([attribute.GetPrim().GetPath() for attribute in attributes.values()])

            # Small gestures and exact typing cover low/high intensities, radius, and material emission.
            for path, _schema, attribute_name, original_value, expected_step in cases[:4]:
                with self.subTest(phase="default fields", path=path):
                    attribute = attributes[path]
                    item = USDAttributeItem("", [attribute.GetPath()])
                    model.set_items([item])
                    await ui_test.human_delay()
                    field = self.__float_drag(window, item).widget
                    self.assertAlmostEqual(field.step, expected_step)
                    self.assertEqual(field.min, 0.0)
                    self.assertEqual(field.max, 65504.0 if attribute_name == "inputs:emissive_intensity" else 65000.0)
                    self.assertEqual(field.hard_min_value, 0.0)
                    self.assertIsNone(field.hard_max_value)
                    omni.kit.undo.clear_stack()
                    await self.__drag_field(window, item, model)
                    self.assertGreater(attribute.Get() - original_value, 0.0)
                    self.assertLess(attribute.Get() - original_value, 100.0)
                    self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)
                    omni.kit.undo.undo()
                    await ui_test.human_delay()
                    self.assertEqual(attribute.Get(), original_value)
                    self.assertEqual(self.__float_drag(window, item).widget.model.get_value_as_float(), original_value)

                    # Undo each typed edit so later selections retain their different authored values.
                    for text, expected_value in (("0.125", 0.125), ("70000", 70000.0), ("-1", 0.0)):
                        await self.__type_value(window, item, model, text)
                        self.assertEqual(attribute.Get(), expected_value)
                        self.assertEqual(
                            self.__float_drag(window, item).widget.model.get_value_as_float(), expected_value
                        )
                        omni.kit.undo.undo()
                        await ui_test.human_delay()
                        self.assertEqual(attribute.Get(), original_value)

            # Other light controls retain their existing bounds and range-derived speed despite step metadata.
            for attribute_name, original_value, minimum, maximum, hard_minimum, hard_maximum, expected_step in (
                ("inputs:colorTemperature", 6500.0, 2500.0, 8500.0, None, None, 30.0),
                ("inputs:exposure", 1.0, 0.0, 10.0, 0.0, None, 0.05),
                ("inputs:shaping:cone:angle", 45.0, 0.0, 360.0, 0.0, 360.0, 1.8),
                ("inputs:shaping:cone:softness", 1.0, 0.0, 10.0, 0.0, None, 0.05),
                ("inputs:shaping:focus", 1.0, 0.0, 10.0, 0.0, None, 0.05),
                ("inputs:volumetric_radiance_scale", 1.0, 0.0, 10.0, 0.0, None, 0.05),
            ):
                with self.subTest(phase="other light controls", attribute=attribute_name):
                    attribute = (
                        attributes["/Sphere"].GetPrim().CreateAttribute(attribute_name, Sdf.ValueTypeNames.Float)
                    )
                    attribute.Set(original_value)
                    attribute.SetCustomData({"ui:step": 100.0})
                    item = USDAttributeItem("", [attribute.GetPath()], ui_metadata=attribute.GetCustomData())
                    model.set_items([item])
                    await ui_test.human_delay()
                    field = self.__float_drag(window, item).widget
                    self.assertEqual(
                        (field.min, field.max, field.hard_min_value, field.hard_max_value),
                        (minimum, maximum, hard_minimum, hard_maximum),
                    )
                    self.assertAlmostEqual(field.step, expected_step)

            # Same-type and mixed selections use the same speed in either order.
            for second_path, expected_step in (("/CompanionLight", 0.1), ("/Sphere", 0.5)):
                selected = [attributes["/Distant"], attributes[second_path]]
                for ordered_attributes in (selected, list(reversed(selected))):
                    with self.subTest(
                        phase="selected lights", paths=[str(attribute.GetPath()) for attribute in ordered_attributes]
                    ):
                        item = USDAttributeItem("", [attribute.GetPath() for attribute in ordered_attributes])
                        model.set_items([item])
                        await ui_test.human_delay()
                        field = self.__float_drag(window, item).widget
                        self.assertAlmostEqual(field.step, expected_step)

            # Author overrides after default typing, then rebuild light/material rows in both orders.
            for kind, paths, expected_steps in (
                ("lights", ("/CompanionLight", "/Distant", "/Sphere"), (0.25, 0.1, 0.5)),
                ("materials", ("/CompanionMaterial", "/Material"), (0.25, 0.1)),
            ):
                items = []
                for index, path in enumerate(paths):
                    attribute = attributes[path]
                    metadata = {"range": {"min": 10.0 if kind == "lights" else 0.0, "max": 1000.0}}
                    if index == 0:
                        metadata["ui:step"] = 0.25
                    attribute.SetCustomData(metadata)
                    items.append(USDAttributeItem("", [attribute.GetPath()], ui_metadata=attribute.GetCustomData()))
                for ordered_items in (items, list(reversed(items))):
                    with self.subTest(
                        phase=f"{kind} metadata isolation",
                        paths=[str(item.attribute_paths[0]) for item in ordered_items],
                    ):
                        model.set_items(ordered_items)
                        await ui_test.human_delay()
                        for item, expected_step in zip(items, expected_steps):
                            field = self.__float_drag(window, item).widget
                            self.assertAlmostEqual(field.step, expected_step)
                            self.assertEqual(field.max, 65000.0 if kind == "lights" else 1000.0)
                            if kind == "lights":
                                self.assertEqual(field.min, 0.0)
                                self.assertEqual(field.hard_min_value, 0.0)
                                self.assertIsNone(field.hard_max_value)
                        before = {name: attribute.Get() for name, attribute in attributes.items()}
                        await self.__drag_field(window, items[1], model)
                        self.assertGreater(attributes[paths[1]].Get() - before[paths[1]], 0.0)
                        self.assertLess(attributes[paths[1]].Get() - before[paths[1]], 100.0)
                        for other_path, attribute in attributes.items():
                            if other_path != paths[1]:
                                self.assertEqual(attribute.Get(), before[other_path])
                        if kind == "lights":
                            await self.__type_value(window, items[0], model, "-1")
                            self.assertEqual(attributes[paths[0]].Get(), 0.0)

    async def test_drag_multiple_attributes_previews_without_notices_and_commits_one_undo(self):
        """Keep previews live during a held mouse gesture and undo the final edit together."""
        context = omni.usd.get_context("")
        mouse_held = False

        async def release_mouse():
            """Release a possibly held button before destroying its target widgets."""
            if mouse_held:
                await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
                await ui_test.human_delay()

        cases = [
            ("speed", [1.0, 3.0], 0, False),
            ("xformOp:translate", [(1, 2, 3), (4, 6, 8)], 1, False),
            ("xformOp:rotateXYZ", [(10, 20, 30), (40, 60, 80)], 1, False),
            ("xformOp:scale", [(1, 1, 1), (3, 3, 3)], 0, True),
        ]
        for attribute_name, initial_values, channel, linked in cases:
            with self.subTest(title=attribute_name):
                async with AsyncExitStack() as cleanup:
                    cleanup.push_async_callback(context.close_stage_async)
                    cleanup.callback(omni.kit.undo.clear_stack)
                    await context.new_stage_async()
                    stage = context.get_stage()
                    attributes = []
                    xformables = []
                    related_paths = []
                    for path, value in zip(("/A", "/B"), initial_values):
                        prim = stage.DefinePrim(path, "Xform")
                        if attribute_name == "speed":
                            attribute = prim.CreateAttribute(attribute_name, Sdf.ValueTypeNames.Float)
                        else:
                            xformable = UsdGeom.Xformable(prim)
                            operations = [
                                xformable.AddTranslateOp(),
                                xformable.AddRotateXYZOp(),
                                xformable.AddScaleOp(),
                            ]
                            for operation, initial in zip(operations, ((1, 2, 3), (10, 20, 30), (2, 3, 4))):
                                operation.Set(initial)
                                related_paths.append(operation.GetAttr().GetPath())
                            related_paths.append(xformable.GetXformOpOrderAttr().GetPath())
                            xformables.append(xformable)
                            attribute = prim.GetAttribute(attribute_name)
                        attribute.Set(value)
                        attributes.append(attribute)
                    originals = [attribute.Get() for attribute in attributes]
                    attribute_paths = [attribute.GetPath() for attribute in attributes]
                    if xformables:
                        item = USDAttributeXformItem("", attribute_paths, related_attribute_paths=related_paths)
                    else:
                        item = USDAttributeItem("", attribute_paths, ui_metadata={"ui:step": 0.1})
                    siblings = {
                        path: stage.GetAttributeAtPath(path).Get()
                        for path in related_paths
                        if path not in attribute_paths
                    }
                    original_transforms = [xformable.GetLocalTransformation() for xformable in xformables]
                    window = ui.Window("Numeric drag preview", width=_TEST_WINDOW_WIDTH, height=_TEST_WINDOW_HEIGHT)
                    cleanup.callback(window.destroy)
                    model = USDModel(context_name="")
                    cleanup.callback(model.destroy)
                    delegate = USDDelegate()
                    with window.frame:
                        widget = USDPropertyWidget(context_name="", model=model, delegate=delegate)
                        cleanup.callback(widget.destroy)
                    model.set_items([item])
                    notices = []
                    raw_notices = []
                    self._subscription = register_objects_changed_listener(
                        stage, lambda notice, sender, events=notices: events.append(notice)
                    )
                    cleanup.callback(self._subscription.Revoke)
                    self._raw_subscription = Tf.Notice.Register(
                        Usd.Notice.ObjectsChanged,
                        lambda notice, sender, events=raw_notices: events.append(notice),
                        stage,
                    )
                    cleanup.callback(self._raw_subscription.Revoke)
                    mouse_held = False

                    cleanup.push_async_callback(release_mouse)
                    # Link through the real control, closing its inline editor before the drag begins.
                    await ui_test.human_delay()
                    if linked:
                        link_identifier = "linked_drag_field_link_" + "".join(
                            name_model.get_value_as_string() for name_model in item.name_models
                        )
                        links = ui_test.find_all(f"{window.title}//Frame/**/Image[*].identifier=='{link_identifier}'")
                        self.assertEqual(len(links), 2)
                        mouse_held = True
                        await links[0].click()
                        mouse_held = False
                        await ui_test.human_delay()
                        await ui_test.emulate_keyboard_press(KeyboardInput.ENTER)
                        await ui_test.human_delay()
                        if model._pending_property_edit_finish_task is not None:
                            await asyncio.wait_for(model._pending_property_edit_finish_task, timeout=5)
                        self.assertTrue(item.linked_edit_enabled)
                        self.assertEqual([attribute.Get() for attribute in attributes], originals)
                    else:
                        self.assertFalse(item.linked_edit_enabled)
                    # Focus empty pane space so consecutive cases cannot become a double-click on the field.
                    mouse_held = True
                    await ui_test.emulate_mouse_move_and_click(
                        ui_test.Vec2(window.position_x + 20, window.position_y + window.height - 20)
                    )
                    mouse_held = False
                    identifier = ",".join(
                        str(path) for value_model in item.value_models for path in value_model.attribute_paths
                    )
                    field_query = f"{window.title}//Frame/**/FloatBoundedDrag[*].identifier=='{identifier}'"
                    fields = ui_test.find_all(field_query)
                    self.assertEqual(len(fields), item.element_count)
                    field = next(field for field in fields if field.widget.model is item.value_models[channel])
                    start = field.center
                    omni.kit.undo.clear_stack()
                    notices.clear()
                    raw_notices.clear()
                    await ui_test.input.emulate_mouse(MouseEventType.MOVE, start)
                    await ui_test.human_delay()
                    mouse_held = True
                    await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN, start)
                    await ui_test.human_delay()

                    # Both selections preview while held, preserving unedited channels and sibling operations.
                    previous_values = originals
                    drag_distances = (30, 60)
                    for distance in drag_distances:
                        await ui_test.input.emulate_mouse(MouseEventType.MOVE, start + ui_test.Vec2(distance, 0))
                        await ui_test.human_delay()
                        values = [attribute.Get() for attribute in attributes]
                        for value, previous in zip(values, previous_values):
                            self.assertNotEqual(value, previous)
                        edited_values = [value[channel] for value in values] if xformables else values
                        self.assertEqual(edited_values[0], edited_values[1])
                        self.assertAlmostEqual(edited_values[0], field.widget.model.get_value_as_float(), places=5)
                        if xformables:
                            for value, original in zip(values, originals):
                                for index in range(3):
                                    self.assertEqual(
                                        value[index],
                                        edited_values[0] if linked or index == channel else original[index],
                                    )
                            for xformable, original in zip(xformables, original_transforms):
                                self.assertNotEqual(xformable.GetLocalTransformation(), original)
                        self.assertEqual({path: stage.GetAttributeAtPath(path).Get() for path in siblings}, siblings)
                        self.assertEqual(notices, [])
                        self.assertGreater(len(raw_notices), 0)
                        self.assertEqual(list(omni.kit.undo.get_undo_stack()), [])
                        previous_values = values
                    final_transforms = [xformable.GetLocalTransformation() for xformable in xformables]

                    # Release keeps the exact preview and records one action for the entire selection.
                    await ui_test.input.emulate_mouse(
                        MouseEventType.LEFT_BUTTON_UP, start + ui_test.Vec2(drag_distances[-1], 0)
                    )
                    mouse_held = False
                    await ui_test.human_delay()
                    if model._pending_property_edit_finish_task is not None:
                        await asyncio.wait_for(model._pending_property_edit_finish_task, timeout=5)
                    self.assertEqual([attribute.Get() for attribute in attributes], previous_values)
                    self.assertEqual({path: stage.GetAttributeAtPath(path).Get() for path in siblings}, siblings)
                    self.assertEqual([xformable.GetLocalTransformation() for xformable in xformables], final_transforms)
                    self.assertEqual(len(notices), 1)
                    self.assertEqual(sum(entry.level == 0 for entry in omni.kit.undo.get_undo_stack()), 1)

                    # Undo restores each complete original transform; redo restores the final preview.
                    for action, expected_values, expected_transforms in (
                        (omni.kit.undo.undo, originals, original_transforms),
                        (omni.kit.undo.redo, previous_values, final_transforms),
                    ):
                        action()
                        await ui_test.human_delay()
                        self.assertEqual([attribute.Get() for attribute in attributes], expected_values)
                        self.assertEqual({path: stage.GetAttributeAtPath(path).Get() for path in siblings}, siblings)
                        self.assertEqual(
                            [xformable.GetLocalTransformation() for xformable in xformables], expected_transforms
                        )
                        if action == omni.kit.undo.undo:
                            self.assertEqual(list(omni.kit.undo.get_undo_stack()), [])
