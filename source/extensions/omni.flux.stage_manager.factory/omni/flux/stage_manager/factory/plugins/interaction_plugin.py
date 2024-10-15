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

import abc
import math
from asyncio import Future, ensure_future
from functools import partial
from typing import TYPE_CHECKING, Any, Iterable

import omni.kit.app
from omni import ui
from omni.flux.stage_manager.factory import StageManagerDataTypes as _StageManagerDataTypes
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.widget.tree_widget import TreeWidget as _TreeWidget
from pydantic import Field, PrivateAttr, root_validator, validator

from .base import StageManagerUIPluginBase as _StageManagerUIPluginBase
from .column_plugin import LengthUnit as _LengthUnit
from .column_plugin import StageManagerColumnPlugin as _StageManagerColumnPlugin
from .context_plugin import StageManagerContextPlugin as _StageManagerContextPlugin
from .filter_plugin import StageManagerFilterPlugin as _StageManagerFilterPlugin
from .tree_plugin import StageManagerTreeItem as _StageManagerTreeItem
from .tree_plugin import StageManagerTreePlugin as _StageManagerTreePlugin

if TYPE_CHECKING:
    from .column_plugin import ColumnWidth as _ColumnWidth


class StageManagerInteractionPlugin(_StageManagerUIPluginBase, abc.ABC):
    """
    A plugin that encompasses other plugins in the Stage Manager.
    The Interaction Plugin builds the TreeWidget and uses the filter, column & widget plugins to build the contents.
    """

    tree: _StageManagerTreePlugin = Field(..., description="The tree plugin defining the model and delegate")
    filters: list[_StageManagerFilterPlugin] = Field(..., description="Filters to apply to the context data")
    columns: list[_StageManagerColumnPlugin] = Field(..., description="Columns to display in the TreeWidget")

    required_filters: list[_StageManagerFilterPlugin] = Field(
        [],
        description="Mandatory filters defined by the interaction plugin. Will never be displayed in UI.",
        exclude=True,
    )

    row_height: int = Field(24 + 4, description="The height of the Tree rows in pixels.", exclude=True)
    header_height: int = Field(
        24 + 4,
        description="The height of the header in pixels. Will be used to offset the alternating row background",
        exclude=True,
    )
    alternate_row_colors: bool = Field(
        True, description="Whether the tree's rows should alternate in color", exclude=True
    )

    _row_background_frame: ui.Frame | None = PrivateAttr(None)
    _tree_frame: ui.Frame | None = PrivateAttr(None)
    _tree_widget: _TreeWidget | None = PrivateAttr(None)
    _tree_scroll_frame: ui.Frame | None = PrivateAttr(None)

    _context: _StageManagerContextPlugin | None = PrivateAttr(None)

    _result_frames: list[ui.Frame] = PrivateAttr([])

    _item_expansion_states: dict[int, bool] = PrivateAttr({})

    _item_changed_sub: _EventSubscription | None = PrivateAttr(None)
    _item_expanded_sub: _EventSubscription | None = PrivateAttr(None)
    _selection_changed_sub: _EventSubscription | None = PrivateAttr(None)

    _widget_item_clicked_subs: list[_EventSubscription] | None = PrivateAttr([])
    _filter_items_changed_subs: list[_EventSubscription] = PrivateAttr([])
    _listener_event_occurred_subs: list[_EventSubscription] = PrivateAttr([])

    _draw_row_background_task: Future | None = PrivateAttr(None)
    _update_expansion_task: Future | None = PrivateAttr(None)
    _update_scroll_frame_task: Future | None = PrivateAttr(None)

    _is_initialized: bool = PrivateAttr(False)
    _is_active: bool = PrivateAttr(False)

    _FILTERS_HORIZONTAL_PADDING: int = 24
    _FILTERS_VERTICAL_PADDING: int = 8
    _RESULTS_HORIZONTAL_PADDING: int = 16
    _RESULTS_VERTICAL_PADDING: int = 4

    @validator("filters", "required_filters", allow_reuse=True)
    def check_unique_filters(cls, v):  # noqa N805
        # Use a list + validator to keep the list order
        return list(dict.fromkeys(v))

    @root_validator(allow_reuse=True)
    def check_plugin_compatibility(cls, values):  # noqa N805
        # In the root validator, plugins are already resolved
        cls._check_plugin_compatibility(values.get("tree").name, values.get("compatible_trees"))
        for filter_plugin in values.get("filters"):
            cls._check_plugin_compatibility(filter_plugin.name, values.get("compatible_filters"))
        for column_plugin in values.get("columns"):
            for widget_plugin in column_plugin.widgets:
                cls._check_plugin_compatibility(widget_plugin.name, values.get("compatible_widgets"))

        # The interaction filter plugins are not resolved at this point
        for filter_plugin in values.get("required_filters"):
            cls._check_plugin_compatibility(filter_plugin.get("name"), values.get("compatible_filters"))

        return values

    @classmethod
    @property
    def compatible_data_type(cls) -> _StageManagerDataTypes:
        """
        The data type this plugin supports
        """
        return _StageManagerDataTypes.NONE

    @classmethod
    @property
    def _select_all_children(cls) -> bool:
        """
        Whether the tree should select all children items when selecting a parent item or not
        """
        return False

    @classmethod
    @property
    def _scroll_to_selection(cls) -> bool:
        """
        Whether the tree should scroll to the first item in the selection when selection changes
        """
        return True

    @classmethod
    @property
    def _validate_action_selection(cls) -> bool:
        """
        Whether the tree selection should be validated & updated to include the item being right-clicked on or not
        """
        return True

    @classmethod
    @property
    @abc.abstractmethod
    def compatible_trees(cls) -> list[str]:
        """
        Get the list of tree plugins compatible with this interaction plugin
        """
        pass

    @classmethod
    @property
    @abc.abstractmethod
    def compatible_filters(cls) -> list[str]:
        """
        Get the list of filter plugins compatible with this interaction plugin
        """
        pass

    @classmethod
    @property
    @abc.abstractmethod
    def compatible_widgets(cls) -> list[str]:
        """
        Get the list of widget plugins compatible with this interaction plugin
        """
        pass

    @abc.abstractmethod
    def _setup_listeners(self):
        """
        Subscribe to the context's listeners event occurred subscriptions and react to them
        """
        pass

    @abc.abstractmethod
    def _clear_listeners(self):
        """
        Clear the subscriptions to the context's listeners events
        """
        pass

    @classmethod
    def _check_plugin_compatibility(cls, value: Any, compatible_items: list[Any] | None) -> Any:
        """
        Check if the given value is contained within the compatible items.

        Args:
            value: The value to be checked.
            compatible_items: A list of compatible items to compare value to

        Raises:
            ValueError: If the value is not compatible with any of the compatible items.

        Returns:
            The value if it is compatible
        """
        if value not in (compatible_items or []):
            raise ValueError(
                f"The selected plugin is not compatible with this plugin -> {value}\n"
                f"  Compatible plugin(s): {', '.join(compatible_items)}"
            )
        return value

    def setup(self, value: _StageManagerContextPlugin):
        """
        Set up the interaction plugin with the given context.

        Args:
            value: the context the interaction plugin should use
        """

        self._context = value

        self._validate_data_type()

        self._setup_tree()
        self._setup_filters()
        self._setup_columns()

        self._update_context_items()

        self._is_initialized = True

    def build_ui(self):  # noqa PLW0221
        """
        The method used to build the UI for the plugin.

        Raises:
            ValueError: If the plugin was not initialized before building the UI.
        """

        if not self.enabled:
            return

        if not self._is_initialized:
            raise ValueError("InteractionPlugin.setup() must be called before build_ui()")

        self._result_frames.clear()

        self.tree.delegate.header_height = self.header_height
        self.tree.delegate.row_height = self.row_height

        enabled_filters = [f for f in self.filters if f.enabled]
        enabled_columns = [c for c in self.columns if c.enabled]

        column_widths = [self._get_ui_length(c.width) for c in enabled_columns]

        root_frame = ui.Frame(computed_content_size_changed_fn=self._draw_row_background)
        with root_frame:
            with ui.VStack():
                # Filters UI
                ui.Spacer(height=ui.Pixel(self._FILTERS_VERTICAL_PADDING), width=0)
                with ui.HStack(height=0):
                    ui.Spacer(height=0)
                    with ui.HStack(width=0, height=0, spacing=self._FILTERS_HORIZONTAL_PADDING):
                        for filter_plugin in enabled_filters:
                            # Some filters should not be displayed in the UI
                            if not filter_plugin.display:
                                continue
                            ui.Frame(tooltip=filter_plugin.tooltip, build_fn=filter_plugin.build_ui)
                    ui.Spacer(width=12, height=0)
                ui.Spacer(height=ui.Pixel(self._FILTERS_VERTICAL_PADDING), width=0)

                with ui.ZStack():
                    with ui.VStack():
                        # Tree UI
                        self._tree_scroll_frame = ui.ScrollingFrame(name="TreePanelBackground")
                        with self._tree_scroll_frame:
                            with ui.ZStack():
                                self._row_background_frame = ui.Frame(vertical_clipping=True, separate_window=True)
                                self._tree_frame = ui.ZStack(content_clipping=True)
                                with self._tree_frame:
                                    self._tree_widget = _TreeWidget(
                                        self.tree.model,
                                        delegate=self.tree.delegate,
                                        select_all_children=self._select_all_children,
                                        validate_action_selection=self._validate_action_selection,
                                        root_visible=False,
                                        header_visible=True,
                                        columns_resizable=False,  # Can't resize the results after resizing a column
                                        column_widths=column_widths,
                                    )
                                    self._selection_changed_sub = self._tree_widget.subscribe_selection_changed(
                                        self._on_selection_changed
                                    )

                        # Results UI
                        with ui.ZStack(height=self.row_height):
                            ui.Rectangle(name="TabBackground")
                            with ui.VStack():
                                ui.Spacer(height=self._RESULTS_VERTICAL_PADDING, width=0)
                                with ui.HStack():
                                    for index, column in enumerate(enabled_columns):
                                        self._result_frames.append(
                                            ui.Frame(
                                                width=column_widths[index],
                                                horizontal_clipping=True,
                                                build_fn=partial(column.build_overview_ui, self.tree.model),
                                            )
                                        )
                                    # Spacing for the scrollbar
                                    ui.Spacer(width=self._RESULTS_HORIZONTAL_PADDING, height=0)
                                ui.Spacer(height=self._RESULTS_VERTICAL_PADDING, width=0)

                    # Column separators
                    with ui.Frame(separate_window=True):
                        with ui.HStack():
                            for index, _ in enumerate(enabled_columns):
                                with ui.HStack(width=column_widths[index]):
                                    ui.Spacer(height=0)
                                    # Don't draw a line at the end of the tree
                                    if index < len(enabled_columns) - 1:
                                        ui.Rectangle(width=ui.Pixel(2), name="ColumnSeparator")
                            # Spacing for the scrollbar
                            ui.Spacer(width=self._RESULTS_HORIZONTAL_PADDING, height=0)

    def set_active(self, value: bool):
        """
        Whether the interaction plugin is active or not. Only 1 interaction plugin should be active at a time.
        Active status should be managed by the widget

        Args:
            value: whether the interaction plugin is active or not
        """
        self._is_active = value

        if self._is_active:
            self._setup_listeners()
            self._update_context_items()
        else:
            self._clear_listeners()

    @staticmethod
    def _get_ui_length(column_width: "_ColumnWidth") -> ui.Length:
        """
        Args:
            column_width: A ColumnWidth base model describing the length object

        Returns:
            An OmniUI length object
        """
        length_class = ui.Fraction
        match column_width.unit:
            case _LengthUnit.FRACTION:
                length_class = ui.Fraction
            case _LengthUnit.PERCENT:
                length_class = ui.Percent
            case _LengthUnit.PIXEL:
                length_class = ui.Pixel
        return length_class(column_width.value)

    def _setup_tree(self):
        """
        Subscribe to the `_item_changed` event triggered by the tree model to rebuild the result UI frames
        """
        self._item_changed_sub = self.tree.model.subscribe_item_changed_fn(self._on_item_changed)

        # Make sure the widgets' `_item_clicked` event triggers the delegate's `_item_clicked` event
        for column in self.columns:
            for widget in column.widgets:
                self._widget_item_clicked_subs.append(
                    widget.subscribe_item_clicked(self.tree.delegate.call_item_clicked)
                )

    def _setup_filters(self):
        """
        Subscribe to the on_filter_items_changed event to refresh the tree widget model & add the filter functions to
        the tree model.
        """
        self.tree.model.clear_filter_functions()
        for filter_plugin in self.filters + self.required_filters:
            if not filter_plugin.enabled:
                continue
            self._filter_items_changed_subs.append(
                filter_plugin.subscribe_filter_items_changed(self._on_filter_items_changed)
            )
            # Some models might need to filter children items so pass the filter functions down
            self.tree.model.add_filter_functions([filter_plugin.filter_items])

    def _setup_columns(self):
        """
        Set up the tree delegate to have the right column information
        """
        enabled_columns = [c for c in self.columns if c.enabled]

        self.tree.model.column_count = len(enabled_columns)
        self.tree.delegate.set_column_builders(enabled_columns)

        self._item_expanded_sub = self.tree.delegate.subscribe_item_expanded(self._on_item_expanded)

    def _on_item_changed(self, _model: ui.AbstractItemModel, _item: ui.AbstractItem):
        """
        Event handler to execute when the tree model's items change
        """
        # Rebuild the result UI with the update model data
        for frame in self._result_frames:
            frame.rebuild()

        self._update_expansion_states()

    def _on_filter_items_changed(self):
        """
        Event handler to execute when event filter widgets are updated
        """
        self._update_context_items()

    def _on_item_expanded(self, item: _StageManagerTreeItem, expanded: bool):
        """
        A callback executed whenever a tree item is expanded or collapsed.

        Args:
            item: The item that was expanded or collapsed.
            expanded: The expansion state
        """
        self._item_expansion_states[hash(item)] = expanded
        self._draw_row_background()

    def _on_selection_changed(self, items: list[_StageManagerTreeItem]):
        """
        A callback executed whenever the tree selection changes.

        Args:
            items: The list of items selected in the tree.
        """
        pass

    def _validate_data_type(self):
        """
        Validate the compatibility of the context data type

        Raises:
            ValueError: If the data type is not compatible with this plugin
        """
        if self._context.data_type != self.compatible_data_type:
            raise ValueError(
                f"The context plugin data type is not compatible with this interaction plugin -> {self.name} -> "
                f"{self._context.data_type.value} != {self.compatible_data_type.value}"
            )

    def _update_context_items(self):
        """
        Set the context items for the interaction plugin Tree model and refresh the model.
        """
        if not self._is_active:
            return

        self.tree.model.context_items = self._filter_context_items(self._context.get_items())
        self.tree.model.refresh()

    def _filter_context_items(self, items: Iterable[Any]) -> list[Any]:
        """
        Filter the context items based on the enabled filters.

        Args:
            items: The items to be filtered

        Returns:
            A filtered list of items
        """
        filtered_items = list(items)

        for filter_plugin in self.filters + self.required_filters:
            if filter_plugin.enabled:
                filtered_items = filter_plugin.filter_items(filtered_items)
        return filtered_items

    def _draw_row_background(self):
        if self._draw_row_background_task:
            self._draw_row_background_task.cancel()
        self._draw_row_background_task = ensure_future(self._draw_row_background_deferred())

    async def _draw_row_background_deferred(self):
        if not self._row_background_frame or not self.alternate_row_colors:
            return

        await omni.kit.app.get_app().next_update_async()

        row_count = math.ceil(self._tree_frame.computed_height / self.row_height)

        self._row_background_frame.clear()
        with self._row_background_frame:
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(self.header_height))
                for i in range(row_count):
                    ui.Rectangle(name=("Alternate" if i % 2 else "") + "Row", height=ui.Pixel(self.row_height))

        self._row_background_frame.height = self._tree_frame.computed_height

    def _update_expansion_states(self):
        """
        Fire and forget the `_update_expansion_states_deferred` function
        """
        if self._update_expansion_task:
            self._update_expansion_task.cancel()
        self._update_expansion_task = ensure_future(self._update_expansion_states_deferred())

    @omni.usd.handle_exception
    async def _update_expansion_states_deferred(self):
        """
        Wait 1 frame, then update the expansion state of the Tree items based on their cached state
        """
        await omni.kit.app.get_app().next_update_async()

        items_dict = self.tree.model.items_dict

        # Expand the items that were previously expanded
        for item_hash, expanded in reversed(self._item_expansion_states.items()):
            item = items_dict.get(item_hash)
            if not item:
                continue
            self._tree_widget.set_expanded(item, expanded, False)

    def _update_scroll_frame(self):
        """
        Fire and forget the `_update_scroll_frame_deferred` function
        """
        if not self._scroll_to_selection:
            return

        if self._update_scroll_frame_task:
            self._update_scroll_frame_task.cancel()
        self._update_scroll_frame_task = ensure_future(self._update_scroll_frame_deferred())

    @omni.usd.handle_exception
    async def _update_scroll_frame_deferred(self):
        """
        Wait 2 frame, then update the scroll frame to display selection
        """
        # make sure this occurs after tree items have been expanded
        for _ in range(2):
            await omni.kit.app.get_app().next_update_async()

        # Scroll to first item in selection
        self._scroll_to_items(self._tree_widget.selection)

    def _scroll_to_items(self, items: Iterable[_StageManagerTreeItem], center_ratio: float = 0.2):
        """
        Scroll to reveal the first item in `items`.

        Args:
            center_ratio: where to frame first item (0.0: top, 0.5: center, 1.0: bottom)
        """
        if not self._tree_scroll_frame:
            return

        items = set(items)
        for i, child in enumerate(self._tree_widget.iter_visible_children()):
            if child in items:
                idx_item = i
                break
        else:
            return

        # find out how far down the first item's center is
        scroll_y = (idx_item + 0.5) * self.tree.delegate.row_height
        # since that would scroll to the item, subtract some height to center the item
        target_from_top = self._tree_scroll_frame.computed_content_height * center_ratio
        self._tree_scroll_frame.scroll_y = scroll_y - target_from_top

    def destroy(self):
        if self._draw_row_background_task:
            self._draw_row_background_task.cancel()
        if self._update_expansion_task:
            self._update_expansion_task.cancel()

    class Config(_StageManagerUIPluginBase.Config):
        fields = {
            **_StageManagerUIPluginBase.Config.fields,
            "compatible_trees": {"exclude": True},
            "compatible_filters": {"exclude": True},
            "compatible_widgets": {"exclude": True},
        }
