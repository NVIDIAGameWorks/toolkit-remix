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
from typing import TYPE_CHECKING, Any, Callable, Iterable

import omni.kit.app
import omni.usd
from omni import ui
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.widget.tree_widget import TreeWidget as _TreeWidget
from pydantic import Field, PrivateAttr, root_validator, validator

from ..enums import StageManagerDataTypes as _StageManagerDataTypes
from ..utils import StageManagerUtils as _StageManagerUtils
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

    columns: list[_StageManagerColumnPlugin] = Field([], description="Columns to display in the TreeWidget")
    filters: list[_StageManagerFilterPlugin] = Field(
        [], description="Filters to apply to the context data on tree model refresh"
    )
    context_filters: list[_StageManagerFilterPlugin] = Field(
        [],
        description="Filters to execute when the context data is updated. Will never be displayed in UI.",
    )

    internal_filters: list[_StageManagerFilterPlugin] = Field(
        [],
        description=(
            "Context filters defined solely by the interaction plugin. The definition should not be part of the schema."
            "Will never be displayed in UI and will be executed with the context filters."
        ),
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
    _loading_frame: ui.ZStack | None = PrivateAttr(None)

    _context: _StageManagerContextPlugin | None = PrivateAttr(None)

    _result_frames: list[ui.Frame] = PrivateAttr([])

    _item_expansion_states: dict[int, bool] = PrivateAttr({})

    _context_items_changed: _Event = PrivateAttr(_Event())

    _context_items_changed_sub: _EventSubscription | None = PrivateAttr(None)
    _item_changed_sub: _EventSubscription | None = PrivateAttr(None)
    _item_expanded_sub: _EventSubscription | None = PrivateAttr(None)
    _selection_changed_sub: _EventSubscription | None = PrivateAttr(None)

    _widget_item_clicked_subs: list[_EventSubscription] | None = PrivateAttr([])
    _filter_items_changed_subs: list[_EventSubscription] = PrivateAttr([])
    _listener_event_occurred_subs: list[_EventSubscription] = PrivateAttr([])

    _update_context_items_task: Future | None = PrivateAttr(None)
    _update_content_size_task: Future | None = PrivateAttr(None)
    _draw_row_background_task: Future | None = PrivateAttr(None)
    _update_expansion_task: Future | None = PrivateAttr(None)
    _model_refresh_task: Future | None = PrivateAttr(None)

    _is_initialized: bool = PrivateAttr(False)
    _is_active: bool = PrivateAttr(False)

    _previous_frame_height: float = PrivateAttr(-1.0)

    _FILTERS_HORIZONTAL_PADDING: int = 24
    _FILTERS_VERTICAL_PADDING: int = 8
    _RESULTS_HORIZONTAL_PADDING: int = 16
    _RESULTS_VERTICAL_PADDING: int = 4

    @validator("filters", "context_filters", "internal_filters", allow_reuse=True)
    def check_unique_filters(cls, v):  # noqa N805
        # Use a list + validator to keep the list order
        return list(dict.fromkeys(v))

    @root_validator(allow_reuse=True)
    def check_plugin_compatibility(cls, values):  # noqa N805
        # In the root validator, plugins are already resolved
        for filter_plugin in values.get("filters"):
            cls._check_plugin_compatibility(filter_plugin.name, values.get("compatible_filters"))
        for filter_plugin in values.get("context_filters"):
            cls._check_plugin_compatibility(filter_plugin.name, values.get("compatible_filters"))
        for column_plugin in values.get("columns"):
            for widget_plugin in column_plugin.widgets:
                cls._check_plugin_compatibility(widget_plugin.name, values.get("compatible_widgets"))

        # The tree & internal filter plugins are not resolved at this point because we only set the name in the plugins
        cls._check_plugin_compatibility(values.get("tree").get("name"), values.get("compatible_trees"))
        for filter_plugin in values.get("internal_filters"):
            cls._check_plugin_compatibility(filter_plugin.get("name"), values.get("compatible_filters"))

        return values

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._context_items_changed_sub = self.subscribe_context_items_changed(self._refresh_tree_model)

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
    def tree(cls) -> _StageManagerTreePlugin:
        """
        The tree plugin defining the model and delegate
        """
        pass

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

        self._queue_update_context_items()

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

        with ui.ZStack():
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
                                self._tree_frame = ui.ZStack(
                                    content_clipping=True,
                                    computed_content_size_changed_fn=self._on_content_size_changed,
                                )
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

            self._loading_frame = ui.ZStack(content_clipping=True, visible=False)
            with self._loading_frame:
                ui.Rectangle(name="LoadingBackground", tooltip="Fetching updated data")
                with ui.VStack(spacing=ui.Pixel(4)):
                    ui.Spacer(width=0)
                    ui.Image("", name="TimerStatic", height=32)
                    ui.Label("Updating", name="LoadingLabel", height=0, alignment=ui.Alignment.CENTER)
                    ui.Spacer(width=0)

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
            self._queue_update_context_items()
        else:
            self._clear_listeners()
            if self._update_context_items_task:
                self._update_context_items_task.cancel()

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

    def _show_loading_overlay(self, show: bool):
        """
        Show or hide the loading overlay

        Args:
            show: whether to show or hide the loading overlay
        """
        if self._loading_frame:
            self._loading_frame.visible = show

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
        self.tree.model.clear_context_predicates()
        self.tree.model.add_context_predicates(
            [
                filter_plugin.filter_predicate
                for filter_plugin in (self.context_filters + self.internal_filters)
                if filter_plugin.enabled
            ]
        )

        self.tree.model.clear_filter_predicates()
        for filter_plugin in self.filters:
            if not filter_plugin.enabled:
                continue
            self._filter_items_changed_subs.append(
                filter_plugin.subscribe_filter_items_changed(self._refresh_tree_model)
            )
            # Some models might need to filter children items so pass the filter functions down
            self.tree.model.add_filter_predicates([filter_plugin.filter_predicate])

    def _setup_columns(self):
        """
        Set up the tree delegate to have the right column information
        """
        enabled_columns = [c for c in self.columns if c.enabled]

        self.tree.model.column_count = len(enabled_columns)
        self.tree.delegate.set_column_builders(enabled_columns)

        self._item_expanded_sub = self.tree.delegate.subscribe_item_expanded(self._on_item_expanded)

    def _refresh_tree_model(self):
        """
        Callback to execute when context items are updated
        """
        self._show_loading_overlay(True)

        if self._model_refresh_task:
            self._model_refresh_task.cancel()
        self._model_refresh_task = ensure_future(self.tree.model.refresh())

    def _on_item_changed(self, _model: ui.AbstractItemModel, _item: ui.AbstractItem):
        """
        Event handler to execute when the tree model's items change
        """
        # Rebuild the result UI with the update model data
        for frame in self._result_frames:
            frame.rebuild()

        if self._update_expansion_task:
            self._update_expansion_task.cancel()
        self._update_expansion_task = ensure_future(self._update_expansion_states_deferred())

        if self._draw_row_background_task:
            self._draw_row_background_task.cancel()
        self._draw_row_background_task = ensure_future(self._draw_row_background_deferred())

        self._show_loading_overlay(False)

    def _on_item_expanded(self, item: _StageManagerTreeItem, expanded: bool):
        """
        A callback executed whenever a tree item is expanded or collapsed.

        Args:
            item: The item that was expanded or collapsed.
            expanded: The expansion state
        """
        self._item_expansion_states[hash(item)] = expanded

    def _on_content_size_changed(self):
        if self._update_content_size_task:
            self._update_content_size_task.cancel()
        self._update_content_size_task = ensure_future(self._update_content_size_deferred())

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

    def _queue_update_context_items(self):
        """
        Queue up the update of the context items using the `_update_context_items` function.
        """
        if self._update_context_items_task:
            self._update_context_items_task.cancel()
        self._update_context_items_task = ensure_future(self._update_context_items())

    @omni.usd.handle_exception
    async def _update_context_items(self):
        """
        Set the context items for the interaction plugin TreeView model and trigger the `_context_items_changed` event.
        """
        if not self._is_active:
            return

        # Debounce the calls by waiting 1 frame
        await omni.kit.app.get_app().next_update_async()

        self._show_loading_overlay(True)

        predicates = [
            filter_plugin.filter_predicate
            for filter_plugin in (self.context_filters + self.internal_filters)
            if filter_plugin.enabled
        ]

        filtered_items = await _StageManagerUtils.filter_items(self._context.get_items(), predicates)
        if filtered_items is None:
            return

        self.tree.model.set_context_items(filtered_items)

        self._context_items_changed()

    @omni.usd.handle_exception
    async def _update_content_size_deferred(self):
        """
        Update the scroll position when the content size changes to force the ScrollFrame to resize.
        """
        # Only update the scroll position when shrinking the frame
        if self._tree_widget.computed_height < self._previous_frame_height:
            # Cache the current scroll position
            previous_scroll_y = self._tree_scroll_frame.scroll_y
            # Scroll to the top of the tree
            self._tree_scroll_frame.scroll_y = 0
            # Wait for the updated widget to be drawn
            await omni.kit.app.get_app().next_update_async()
            if previous_scroll_y > self._tree_scroll_frame.scroll_y_max:
                # Scroll to the bottom of the tree or the previous scroll position if still valid
                self._tree_scroll_frame.scroll_y = min(previous_scroll_y, self._tree_scroll_frame.scroll_y_max)
        # Cache the current frame height for the next update
        self._previous_frame_height = self._tree_widget.computed_height

    @omni.usd.handle_exception
    async def _draw_row_background_deferred(self):
        """
        Draw the alternate row background for the tree
        """
        if not self._row_background_frame or not self.alternate_row_colors:
            return

        await omni.kit.app.get_app().next_update_async()

        min_row_count = math.ceil(self._tree_frame.computed_height / self.row_height)
        items_count = len(list(self.tree.model.iter_items_children()))

        # Make sure to fill up the available space and cover every item in the tree
        row_count = max(min_row_count, items_count)

        self._row_background_frame.clear()
        with self._row_background_frame:
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(self.header_height))
                for i in range(row_count):
                    ui.Rectangle(name=("Alternate" if i % 2 else "") + "Row", height=ui.Pixel(self.row_height))

    @omni.usd.handle_exception
    async def _update_expansion_states_deferred(self, scroll_to_selection_override: bool = True):
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

        if scroll_to_selection_override and self._scroll_to_selection and self._tree_scroll_frame:
            await omni.kit.app.get_app().next_update_async()
            self._scroll_to_items(self._tree_widget.selection)

    def _scroll_to_items(self, items: Iterable[_StageManagerTreeItem], center_ratio: float = 0.2):
        """
        Scroll to reveal the first item in `items`.

        Args:
            center_ratio: where to frame first item (0.0: top, 0.5: center, 1.0: bottom)
        """
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

    def subscribe_context_items_changed(self, callback: Callable[[], None]) -> _EventSubscription:
        """
        Execute the callback when context items are updated.

        Args:
            callback: The callback to execute

        Returns:
            Return an object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self._context_items_changed, callback)

    def destroy(self):
        if self._update_context_items_task:
            self._update_context_items_task.cancel()
        if self._update_content_size_task:
            self._update_content_size_task.cancel()
        if self._draw_row_background_task:
            self._draw_row_background_task.cancel()
        if self._update_expansion_task:
            self._update_expansion_task.cancel()
        if self._model_refresh_task:
            self._model_refresh_task.cancel()

    class Config(_StageManagerUIPluginBase.Config):
        fields = {
            **_StageManagerUIPluginBase.Config.fields,
            "tree": {"exclude": True},
            "compatible_data_type": {"exclude": True},
            "compatible_trees": {"exclude": True},
            "compatible_filters": {"exclude": True},
            "compatible_widgets": {"exclude": True},
        }
