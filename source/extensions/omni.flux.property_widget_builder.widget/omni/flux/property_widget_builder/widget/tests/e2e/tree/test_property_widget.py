__all__ = ("TestPropertyWidget",)

from typing import Iterable

import carb.input
import omni.kit.clipboard
import omni.kit.test
import omni.kit.ui_test
from omni.flux.property_widget_builder.delegates import FloatSliderField
from omni.flux.property_widget_builder.widget import FieldBuilderList, Item, ItemGroup

from ...ui_components import AsyncTestPropertyWidget, TestItem


class TestPropertyWidget(omni.kit.test.AsyncTestCase):
    def assert_items_equal(self, a: Iterable[Item], b: Iterable[Item]):  # noqa N806
        # custom sort key to just use the item id
        self.assertListEqual(sorted(a, key=id), sorted(b, key=id))

    async def test_tree_selection(self):
        async with AsyncTestPropertyWidget() as helper:

            group_a = ItemGroup("Parent_A")
            group_a.children.extend(
                [
                    TestItem([("A_Child_1", 42)]),
                    TestItem([("A_Child_2", 42)]),
                    TestItem([("A_Child_3", 42)]),
                ]
            )

            group_b = ItemGroup("Parent_B")
            group_b.children.extend(
                [
                    TestItem([("B_Child_1", 42)]),
                    TestItem([("B_Child_2", 42)]),
                    TestItem([("B_Child_3", 42)]),
                ]
            )

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

            # Clicking just the single child that is the only thing selected
            await helper.click_item(group_a.children[0])
            self.assert_items_equal(helper.get_selected_items(), [group_a.children[0]])

            # Control click another child
            async with omni.kit.ui_test.KeyDownScope(carb.input.KeyboardInput.LEFT_CONTROL):
                await helper.click_item(group_b.children[1])
            self.assert_items_equal(helper.get_selected_items(), [group_a.children[0], group_b.children[1]])

            # Click an unselected child
            await helper.click_item(group_a.children[1])
            self.assert_items_equal(helper.get_selected_items(), [group_a.children[1]])

            # Click an unselected parent
            await helper.click_item(group_a)
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

            await widget_ref.double_click()

            await omni.kit.ui_test.emulate_char_press("1.2")
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.emulate_char_press("1.3")
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.emulate_char_press("1.4")
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.TAB)
            await omni.kit.ui_test.emulate_char_press("1.5")
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.TAB)
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
            builder = FloatSliderField(min_value, max_value)
            return builder(item)

        async with AsyncTestPropertyWidget() as helper:

            helper.delegate.field_builders = field_builders

            await helper.set_items([item])

            widget_refs = omni.kit.ui_test.find_all(f"{helper.window.title}//Frame/**/FloatDrag[*]")
            self.assertTrue(len(widget_refs) > 0, "No widgets found")
            widget_ref = widget_refs[0]

            # Test min value - click and drag left
            drag_vector = widget_ref.center
            drag_vector.x = drag_vector.x - 400
            await omni.kit.ui_test.human_delay(30)
            await omni.kit.ui_test.emulate_mouse_drag_and_drop(widget_ref.center, drag_vector)
            await omni.kit.ui_test.wait_n_updates(2)
            self.assertAlmostEqual(item.get_value()[0], min_value)

            # Test max value - click and drag right
            drag_vector = widget_ref.center
            drag_vector.x = drag_vector.x + 400
            await omni.kit.ui_test.human_delay(30)
            await omni.kit.ui_test.emulate_mouse_drag_and_drop(widget_ref.center, drag_vector)
            await omni.kit.ui_test.wait_n_updates(2)
            self.assertAlmostEqual(item.get_value()[0], max_value)

            # Test manually entering value outside the range
            await widget_ref.double_click()
            await omni.kit.ui_test.emulate_char_press("2.2")
            await omni.kit.ui_test.emulate_keyboard_press(carb.input.KeyboardInput.ENTER)
            self.assertAlmostEqual(item.get_value()[0], 2.2)
