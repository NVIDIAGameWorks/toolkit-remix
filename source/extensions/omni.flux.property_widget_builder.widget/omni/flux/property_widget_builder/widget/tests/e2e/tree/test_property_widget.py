__all__ = ("TestPropertyWidget",)

from collections.abc import Iterable

import carb.input
import omni.kit.clipboard
import omni.kit.test
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.delegates import FloatDragFieldGroup
from omni.flux.property_widget_builder.widget import FieldBuilderList, Item, ItemGroup

from ...ui_components import AsyncTestPropertyWidget, TestItem


class TestPropertyWidget(omni.kit.test.AsyncTestCase):
    def assert_items_equal(self, a: Iterable[Item], b: Iterable[Item]):
        # custom sort key to just use the item id
        self.assertListEqual(sorted(a, key=id), sorted(b, key=id))

    def assert_widget_inside_panel(self, field_widget, panel_frame, details=""):
        field_right = field_widget.screen_position_x + field_widget.computed_width
        panel_right = panel_frame.screen_position_x + panel_frame.computed_width
        message = f"field right edge {field_right} exceeded panel right edge {panel_right}"
        if details:
            message = f"{message}. {details}"
        self.assertLessEqual(
            field_right,
            panel_right + 1,
            message,
        )

    async def test_tree_selection(self):
        async with AsyncTestPropertyWidget() as helper:
            group_a = ItemGroup("Parent_A")
            for child in [
                TestItem([("A_Child_1", 42)]),
                TestItem([("A_Child_2", 42)]),
                TestItem([("A_Child_3", 42)]),
            ]:
                child.parent = group_a

            group_b = ItemGroup("Parent_B")
            for child in [
                TestItem([("B_Child_1", 42)]),
                TestItem([("B_Child_2", 42)]),
                TestItem([("B_Child_3", 42)]),
            ]:
                child.parent = group_b

            await helper.set_items(
                [
                    group_a,
                    group_b,
                ]
            )

            # Expand all groups
            for widget_ref in omni.kit.ui_test.find_all(
                f"{helper.window.title}//Frame/**/Image[*].identifier=='property_branch'"
            ):
                await widget_ref.click()
                await omni.kit.ui_test.wait_n_updates(1)
            await omni.kit.ui_test.wait_n_updates(2)

            # Clicking just the single child that is the only thing selected
            await helper.click_item(group_a.children[0])
            await omni.kit.ui_test.wait_n_updates(1)
            self.assert_items_equal(helper.get_selected_items(), [group_a.children[0]])

            # Control click another child
            async with omni.kit.ui_test.KeyDownScope(carb.input.KeyboardInput.LEFT_CONTROL):
                await helper.click_item(group_b.children[1])
            await omni.kit.ui_test.wait_n_updates(1)
            self.assert_items_equal(helper.get_selected_items(), [group_a.children[0], group_b.children[1]])

            # Click an unselected child
            await helper.click_item(group_a.children[1])
            await omni.kit.ui_test.wait_n_updates(1)
            self.assert_items_equal(helper.get_selected_items(), [group_a.children[1]])

            # Click an unselected parent
            await helper.click_item(group_a)
            await omni.kit.ui_test.wait_n_updates(1)
            self.assert_items_equal(helper.get_selected_items(), [group_a] + group_a.children)

    async def test_widget_update(self):
        async with AsyncTestPropertyWidget() as helper:
            items = [
                TestItem([("Translate X", "0.0"), ("Y", "0.0"), ("Z", "0.0")]),
                TestItem([("Rotate X", "0.0"), ("Y", "0.0"), ("Z", "0.0")]),
                TestItem([("Scale X", "1.0"), ("Y", "1.0"), ("Z", "1.0")]),
            ]
            await helper.set_items(items)

            widget_refs = omni.kit.ui_test.find_all(f"{helper.window.title}//Frame/**/StringField[*]")
            self.assertTrue(len(widget_refs) > 0, "No widgets found")
            widget_ref = widget_refs[0]

            # Be explicit about replacing text to avoid platform-dependent
            # double-click selection behavior in StringField.
            await widget_ref.click()

            async def _replace_and_tab(value: str):
                for _ in range(8):
                    await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.BACKSPACE)
                await omni.kit.ui_test.emulate_char_press(value)
                await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.TAB)
                await omni.kit.ui_test.wait_n_updates(1)

            await _replace_and_tab("1.2")
            await _replace_and_tab("1.3")
            await _replace_and_tab("1.4")
            await _replace_and_tab("1.5")
            await omni.kit.ui_test.emulate_char_press("1.6")
            # NOTE: This last one we don't hit tab or enter after so the value should not update the value.

            self.assertListEqual(items[0].get_value(), ["1.2", "1.3", "1.4"])
            self.assertListEqual(items[1].get_value(), ["1.5", "0.0", "0.0"])

    async def test_slider_widget(self):
        min_value = 0.0
        max_value = 1.0
        item = TestItem([("Slider", (max_value - min_value) / 2)])

        field_builders = FieldBuilderList()

        @field_builders.register_build(lambda _: True)
        def build(item):
            builder = FloatDragFieldGroup(min_value, max_value)
            return builder(item)

        async with AsyncTestPropertyWidget() as helper:
            helper.delegate.field_builders = field_builders

            await helper.set_items([item])

            widget_refs = omni.kit.ui_test.find_all(f"{helper.window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertTrue(len(widget_refs) > 0, "No widgets found")
            widget_ref = widget_refs[0]

            # Test min value - click and drag left
            drag_vector = widget_ref.center
            drag_vector.x -= 400
            await omni.kit.ui_test.human_delay(30)
            await omni.kit.ui_test.emulate_mouse_drag_and_drop(widget_ref.center, drag_vector)
            await omni.kit.ui_test.wait_n_updates(2)
            self.assertAlmostEqual(item.get_value()[0], min_value)

            # Test max value - click and drag right
            drag_vector = widget_ref.center
            drag_vector.x += 400
            await omni.kit.ui_test.human_delay(30)
            await omni.kit.ui_test.emulate_mouse_drag_and_drop(widget_ref.center, drag_vector)
            await omni.kit.ui_test.wait_n_updates(2)
            self.assertAlmostEqual(item.get_value()[0], max_value)

            # Test manually entering value outside the soft range:
            # typed values are accepted unless explicit hard bounds are provided.
            typed_value = 2.2
            await widget_ref.double_click()
            await omni.kit.ui_test.emulate_char_press(str(typed_value))
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
            self.assertAlmostEqual(item.get_value()[0], typed_value)

    async def test_editor_property_fields_stay_inside_panel_when_resized(self):
        field_builders = FieldBuilderList()

        @field_builders.register_build(lambda _: True)
        def build(item):
            builder = FloatDragFieldGroup(0.0, 1.0)
            return builder(item)

        item = TestItem([("Width", 0.5)])
        async with AsyncTestPropertyWidget(
            tree_column_widths=[ui.Pixel(270), ui.Fraction(1)],
            columns_resizable=True,
            width=500,
            use_scrolling_frame=True,
            scrolling_frame_horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
        ) as helper:
            helper.delegate.field_builders = field_builders
            await helper.set_items([item])
            await omni.kit.ui_test.wait_n_updates(4)

            field_refs = omni.kit.ui_test.find_all(f"{helper.window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertTrue(field_refs, "No float field found")
            field_widget = field_refs[0].widget
            wide_field_width = field_widget.computed_width
            wide_label_width = helper.property_widget.tree_view.column_widths[0].value
            self.assert_widget_inside_panel(field_widget, helper.window.frame)

            helper.window.width = 340
            await omni.kit.ui_test.wait_n_updates(8)

            field_refs = omni.kit.ui_test.find_all(f"{helper.window.title}//Frame/**/FloatBoundedDrag[*]")
            self.assertTrue(field_refs, "No resized float field found")
            field_widget = field_refs[0].widget
            narrow_label_width = helper.property_widget.tree_view.column_widths[0].value
            self.assertLess(narrow_label_width, wide_label_width, "Label column width did not shrink with the panel")
            self.assertLess(field_widget.computed_width, wide_field_width, "Field width did not shrink with the panel")
            details = (
                f"field_width={field_widget.computed_width}, "
                f"field_x={field_widget.screen_position_x}, "
                f"panel_width={helper.window.frame.computed_width}, "
                f"panel_x={helper.window.frame.screen_position_x}, "
                f"tree_width={helper.property_widget.tree_view.computed_width}, "
                f"label_width={narrow_label_width}"
            )
            self.assert_widget_inside_panel(field_widget, helper.window.frame, details)
            self.assertIsNotNone(helper.scrolling_frame)
            self.assertLessEqual(
                helper.scrolling_frame.scroll_x_max,
                1,
                f"Property widget created horizontal scroll range {helper.scrolling_frame.scroll_x_max} "
                f"with no visible overflow. {details}",
            )
