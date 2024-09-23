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

__all__ = (
    "MockClipboard",
    "TestItemModel",
    "TestItem",
    "AsyncTestPropertyWidget",
)

import asyncio
import uuid
from typing import Any, Iterable, TypeVar
from unittest import mock

import omni.kit.app
import omni.kit.ui_test
import omni.ui as ui
from omni.flux.property_widget_builder.widget import Delegate, FieldBuilder, Item, ItemValueModel, Model, PropertyWidget

# NOTE: This can be swapped out with typing.Self once we update our version of typing.
AsyncTestPropertyWidgetT = TypeVar("AsyncTestPropertyWidgetT", bound="AsyncTestPropertyWidget")


class MockClipboard:
    """
    Wraps the omni.kit.clipboard copy/paste methods so the data is unique per-instance.

    This avoids race conditions when trying to test data stored in the system clipboard.
    """

    def __init__(self):
        self._data = None
        self._ctx = [
            mock.patch("omni.kit.clipboard.copy", autospec=True, side_effect=self.copy),
            mock.patch("omni.kit.clipboard.paste", autospec=True, side_effect=self.paste),
        ]

    def start(self):
        for ctx in self._ctx:
            ctx.__enter__()  # noqa PCL2801

    def stop(self):
        for ctx in reversed(self._ctx):
            ctx.__exit__(None, None, None)

    def __enter__(self):
        self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def copy(self, data):
        self._data = data

    def paste(self):
        return self._data


class TestItemModel(ItemValueModel):
    def __init__(self, value):
        super().__init__()
        self._value = value
        self._read_only = False

    def get_value(self):
        return self._value

    def _set_value(self, value):
        if value != self._value:
            self._value = value
            self._on_dirty()

    def _on_dirty(self):
        self._value_changed()

    def refresh(self):
        pass

    def _get_value_as_string(self) -> str:
        return str(self._value)

    def _get_value_as_float(self) -> float:
        return float(self._value)

    def _get_value_as_bool(self) -> bool:
        return bool(self._value)

    def _get_value_as_int(self) -> int:
        return int(self._value)


class TestItem(Item):
    def __init__(self, data: Iterable[tuple[str, Any]]):
        super().__init__()
        for name, value in data:
            self._name_models.append(TestItemModel(name))
            self._value_models.append(TestItemModel(value))
        self.selected = False

    @property
    def default_attr(self) -> dict[str, None]:
        return super().default_attr

    def get_value(self):
        return [x.get_value() for x in self._value_models]


class TestDelegate(Delegate):
    def __init__(self, field_builders: list[FieldBuilder] | None = None):
        super().__init__(field_builders=field_builders)
        self.widgets: dict[int, dict[int, list[ui.Widget]]] = {}

    @property
    def default_attr(self) -> dict[str, None]:
        attrs = super().default_attr
        attrs.update(
            {
                "widgets": None,
            }
        )
        return attrs

    def _build_item_widgets(
        self, model: Model, item: Item, column_id: int = 0, level: int = 0, expanded: bool = False
    ) -> ui.Widget | list[ui.Widget] | None:
        cache = self.widgets.setdefault(id(item), {})
        widgets = super()._build_item_widgets(model, item, column_id=column_id, level=level, expanded=expanded)
        cache[column_id] = widgets
        return widgets


class AsyncTestPropertyWidget:
    """
    Helper context manager that simplifies testing PropertyWidget.
    """

    def __init__(self, model: Model | None = None, delegate: Delegate = None):
        self.model = model if model is not None else Model()
        self.delegate = delegate if delegate is not None else TestDelegate()

        self.window = None
        self.property_widget = None

        self._is_built = False

    async def build(self):
        self.window = ui.Window(
            f"{self.__class__.__name__}_{str(uuid.uuid1())}",
            height=200,
            width=200,
            position_x=0,
            position_y=0,
        )
        with self.window.frame:
            self.property_widget = PropertyWidget(
                model=self.model,
                delegate=self.delegate,
            )
        self.window.width = 400
        self.window.height = 400

        await asyncio.sleep(0.1)
        self._is_built = True

    async def destroy(self):
        self.property_widget.destroy()
        self.window.destroy()
        self._is_built = False

    async def __aenter__(self) -> AsyncTestPropertyWidgetT:
        await self.build()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.destroy()

    async def set_item_expand(self, item: Item, value: bool):
        self.delegate._item_expanded(0, item, value)  # noqa PLW0212

    async def click_item(self, item: Item, column_id: int = 0, right_click: bool = False):
        cache = self.delegate.widgets.get(id(item), {})
        widgets = cache.get(column_id)
        if widgets:
            widget = widgets[-1]
            await omni.kit.ui_test.emulate_mouse_move_and_click(
                omni.kit.ui_test.Vec2(widget.screen_position_x, widget.screen_position_y),
                right_click=right_click,
            )
            return
        raise ValueError(f"Could not find widget for {item}")

    async def set_items(self, items: Iterable[Item]):
        await omni.kit.app.get_app().next_update_async()
        self.model.set_items(items)
        await asyncio.sleep(0.05)

    def get_selected_items(self) -> list[Item]:
        return list(self.property_widget._tree_view.selection)  # noqa PLW0212

    async def select_items(self, items: Iterable[Item]):
        await omni.kit.app.get_app().next_update_async()
        self.property_widget._tree_view.selection = items  # noqa PLW0212

    def get_context_menu(self) -> ui.Menu | None:
        return self.delegate._context_menu  # noqa PLW0212
