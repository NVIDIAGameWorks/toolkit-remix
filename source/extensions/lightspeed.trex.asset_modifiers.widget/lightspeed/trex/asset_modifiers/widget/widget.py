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

__all__ = ["AssetModifiersWidget"]

from carb.eventdispatcher import get_eventdispatcher
from lightspeed.trex.asset_modifiers.core import AssetModifiersCore
from lightspeed.trex.asset_modifiers.core.constants import FILE_INPUT, SOURCE_INPUT
from lightspeed.trex.asset_modifiers.core.enums import SourceGetter
from lightspeed.trex.asset_modifiers.core.settings import AssetModifierSettings
from lightspeed.trex.asset_modifiers.factory import get_instance as _get_asset_modifier_factory
from lightspeed.trex.utils.widget.workspace import WorkspaceWidget
from omni import ui, usd
from omni.flux.info_icon.widget import InfoIconWidget
from omni.flux.property_widget_builder.widget import ItemGroup, Model, PropertyWidget
from omni.flux.utils.common import weak_callback
from omni.flux.utils.widget.collapsable_frame import PropertyCollapsableFrameWithInfoPopup
from omni.flux.utils.widget.combo_box import SectionedComboBox, SectionedComboItem

from .delegate import ModifierDelegate
from .item import ModifierValueItem
from .submitter import AssetModifierSubmitter


class AssetModifiersWidget(WorkspaceWidget):
    """Select an asset modifier, edit its inputs, and run it, like the ComfyUI Workflow panel."""

    _CONTENT_PADDING = ui.Pixel(5)
    _SECTION_SPACING = ui.Pixel(16)
    _FORM_SPACING = ui.Pixel(8)
    _NAME_COLUMN_PERCENT = 40
    _NO_MODIFIERS_TEXT = "No asset modifiers available"
    _PICKER_TOOLTIP = "Select the asset modifier to run on the source prims."

    def __init__(self, context_name: str):
        """Build the controls for one USD context."""
        super().__init__()
        self._context_name = context_name
        self._core = AssetModifiersCore(context_name)
        self._settings = AssetModifierSettings()
        self._layout_key = None
        self._property_widget: PropertyWidget | None = None
        self._input_items: list[ModifierValueItem] = []
        self._root = ui.ZStack()
        with self._root:
            ui.Rectangle(name="WorkspaceBackground")
            with ui.VStack():
                with ui.HStack(height=0):
                    ui.Spacer(width=self._CONTENT_PADDING)
                    with ui.VStack(spacing=self._SECTION_SPACING):
                        ui.Spacer(height=self._CONTENT_PADDING)
                        with PropertyCollapsableFrameWithInfoPopup("ASSET MODIFIER", info_text=self._PICKER_TOOLTIP):
                            with ui.HStack(spacing=self._FORM_SPACING, height=0):
                                ui.Label(
                                    "Modifier",
                                    width=ui.Percent(self._NAME_COLUMN_PERCENT),
                                    word_wrap=False,
                                    tooltip=self._PICKER_TOOLTIP,
                                )
                                self._picker = SectionedComboBox(
                                    identifier="AssetModifierPicker",
                                    tooltip=self._PICKER_TOOLTIP,
                                    on_selection_changed_fn=lambda _index, item: (
                                        self._settings.set_active_modifier_name(item.data.name)
                                    ),
                                    width=ui.Fraction(1),
                                )
                                self._description_icon: InfoIconWidget | None = None
                                self._description_stack = ui.VStack(width=0)
                        with ui.VStack(height=0, visible=False) as self._last_run:
                            ui.Label("Last Run", height=0)
                            self._last_run_label = ui.Label(
                                "", height=0, word_wrap=True, identifier="AssetModifierLastRun"
                            )
                    ui.Spacer(width=self._CONTENT_PADDING)
                ui.Spacer(height=self._SECTION_SPACING)
                with ui.HStack():
                    ui.Spacer(width=self._CONTENT_PADDING)
                    with ui.ScrollingFrame(
                        name="PropertiesPaneSection",
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    ):
                        self._inputs_frame = ui.Frame(build_fn=self._build_inputs)
                    ui.Spacer(width=self._CONTENT_PADDING)
                ui.Spacer(height=self._FORM_SPACING)
                with ui.HStack(height=0):
                    ui.Spacer(width=self._CONTENT_PADDING)
                    self._run_button = ui.Button(
                        "Run Modifier",
                        identifier="AssetModifierRun",
                        clicked_fn=self._submit,
                    )
                    ui.Spacer(width=self._CONTENT_PADDING)
                ui.Spacer(height=self._CONTENT_PADDING)
        self._changed_subscription = _get_asset_modifier_factory().subscribe_changed(self._on_changed)
        context = usd.get_context(context_name)
        # Run depends on stage presence, not selection or stage contents.
        self._stage_subscription = [
            get_eventdispatcher().observe_event(
                event_name=context.stage_event_name(event_type),
                on_event=lambda _event: self._update_run_button(),
                observer_name="lightspeed.trex.asset_modifiers.widget:AssetModifiersWidget._update_run_button",
            )
            for event_type in (usd.StageEventType.OPENED, usd.StageEventType.CLOSED)
        ]
        self._on_changed()
        AssetModifierSubmitter.set_result_listener(context_name, weak_callback(self._on_job_result))

    def destroy(self) -> None:
        """Release the subscriptions and widgets."""
        if self.destroyed:
            return
        self._mark_destroyed()
        AssetModifierSubmitter.set_result_listener(self._context_name, None)
        self._changed_subscription = None
        self._stage_subscription = None
        if self._property_widget is not None:
            self._property_widget.destroy()
            self._property_widget = None
        for row in self._input_items:
            row.destroy()
        self._input_items.clear()
        self._picker.destroy()
        if self._description_icon is not None:
            self._description_icon.destroy()
        self._root.clear()

    def _on_changed(self) -> None:
        """Rebuild the controls when the modifier list, active modifier, or source changes."""
        modifier = self._core.active_modifier
        registered = _get_asset_modifier_factory().get_all_plugins()
        layout_key = (
            tuple(registered.items()),
            modifier,
            modifier and self._settings.get_value(modifier, SOURCE_INPUT),
        )
        if layout_key != self._layout_key:
            self._layout_key = layout_key
            modifiers = sorted(registered.values(), key=lambda item: item.display_name)
            items = [
                SectionedComboItem(
                    label=item.display_name + (" (Experimental)" if item.experimental else ""),
                    data=item,
                    tooltip=item.tooltip
                    + (
                        " This modifier is experimental. Check its output before you use it."
                        if item.experimental
                        else ""
                    ),
                )
                for item in modifiers
            ]
            self._picker.set_items(
                items or [SectionedComboItem(label=self._NO_MODIFIERS_TEXT)],
                modifiers.index(modifier) if modifier else 0,
            )
            self._picker.enabled = bool(items)
            # The picker tooltip and the (i) icon beside it describe the selected modifier, like the AI Tools picker.
            self._picker.tooltip = (modifier and modifier.description) or self._PICKER_TOOLTIP
            self._build_description_icon()
            self._inputs_frame.rebuild()
        self._update_visibility()
        self._update_run_button()

    def _build_description_icon(self) -> None:
        """Build the (i) icon that shows the picker tooltip, vertically centered on the picker."""
        if self._description_icon is not None:
            self._description_icon.destroy()
        self._description_stack.clear()
        with self._description_stack:
            ui.Spacer()
            self._description_icon = InfoIconWidget(self._picker.tooltip)
            ui.Spacer()

    def _build_inputs(self) -> None:
        """Build the Source group and one collapsible group per parameter group."""
        if self._property_widget is not None:
            self._property_widget.destroy()
            self._property_widget = None
        for row in self._input_items:
            row.destroy()
        self._input_items.clear()
        modifier = self._core.active_modifier
        if modifier is None:
            return
        groups: dict[str, ItemGroup] = {}
        constant = self._settings.get_value(modifier, SOURCE_INPUT) is SourceGetter.CONSTANT
        source_inputs = (SOURCE_INPUT, *((FILE_INPUT,) if constant else ()))
        for item in (*source_inputs, *modifier.inputs):
            row = ModifierValueItem(modifier, item)
            row.parent = groups.setdefault(item.group, ItemGroup(item.group, expanded=True))
            self._input_items.append(row)
        self._update_visibility()
        model = Model()
        model.set_items(list(groups.values()))
        delegate = ModifierDelegate()
        delegate.resolve_claims(model)
        with PropertyCollapsableFrameWithInfoPopup(
            "MODIFIER INPUTS",
            info_text="Each row is an input of the selected modifier. Source selects the prims to modify.",
        ):
            self._property_widget = PropertyWidget(
                model=model,
                delegate=delegate,
                tree_column_widths=[ui.Percent(self._NAME_COLUMN_PERCENT), ui.Fraction(1)],
                tree_min_column_widths=[ui.Pixel(0), ui.Pixel(0)],
            )
        self._property_widget.tree_view.identifier = "AssetModifierInputs"

    def _update_visibility(self) -> None:
        """Hide conditional rows without removing their values."""
        modifier = self._core.active_modifier
        if modifier is None:
            return
        values = {
            item.name: self._settings.get_value(modifier, item) for item in (SOURCE_INPUT, FILE_INPUT, *modifier.inputs)
        }
        for row in self._input_items:
            predicate = row.modifier_input.visible_if
            row.hidden = predicate is not None and not predicate(values)

    def _submit(self) -> None:
        """Submit the active modifier and show its result in Last Run."""
        AssetModifierSubmitter.submit(self._context_name)

    def _on_job_result(self, message: str) -> None:
        """Show the result unless this widget was destroyed."""
        if self.destroyed:
            return
        self._last_run_label.text = message
        self._last_run.visible = True

    def _update_run_button(self) -> None:
        """Disable Run and show the reason when the settings cannot run."""
        reason = self._core.get_run_block_reason()
        self._run_button.enabled = reason is None
        self._run_button.tooltip = reason or "Run the modifier with the current settings."
