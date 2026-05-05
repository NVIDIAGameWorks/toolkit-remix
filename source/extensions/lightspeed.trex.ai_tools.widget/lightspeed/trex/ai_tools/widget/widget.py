"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from __future__ import annotations

import asyncio
import enum
import pathlib
import webbrowser
from collections.abc import Callable, Iterable

import carb
import carb.tokens
import omni.flux.job_queue.core.interface
import omni.flux.job_queue.core.job
import omni.flux.job_queue.widget
import omni.kit.app
import omni.ui as ui
from lightspeed.trex.ai_tools.widget.comfy import ConnectionState, Field, Workflow, get_comfy_interface
from lightspeed.trex.ai_tools.widget.job_generator import ComfyJobGenerator, iter_selected_prims
from lightspeed.trex.ai_tools.widget.lazy_values import LAZY_VALUE_REGISTRY, LazyValue
from omni.flux.utils.common import Event, EventSubscription
from omni.flux.utils.common.decorators import ignore_function_decorator


def get_job_queue_interface(
    db_path: str | pathlib.Path | None = None,
) -> omni.flux.job_queue.core.interface.QueueInterface:
    if db_path is None:
        token = carb.tokens.get_tokens_interface()
        directory = token.resolve("${app_documents}")
        if not directory:
            raise RuntimeError("Could not resolve ${app_documents} path.")

        db_path = pathlib.Path(directory) / "data" / "job_queue" / "job_queue.sqlite"

    if not isinstance(db_path, pathlib.Path):
        db_path = pathlib.Path(db_path)

    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    return omni.flux.job_queue.core.interface.QueueInterface(
        str(db_path),
        initialize=True,
    )


def submit_selected_prims_to_comfy(
    interface: omni.flux.job_queue.core.interface.QueueInterface | None = None,
    workflow: Workflow | None = None,
    use_inputs_for_output_filename_prefix: bool = False,
) -> None:
    """
    Submit the currently selected prims to ComfyUI for processing.

    This is a convenience function that creates a ComfyJobGenerator with the current
    selection and submits jobs using the provided (or default) interface and workflow.

    Args:
        interface: The job queue interface. If None, uses the default interface.
        workflow: The workflow to use. If None, uses the workflow from the ComfyInterface.
        use_inputs_for_output_filename_prefix: If True, uses input filenames for output prefixes.
    """
    comfy = get_comfy_interface()

    if interface is None:
        interface = get_job_queue_interface()
    selected_workflow = workflow
    if selected_workflow is None:
        selected_workflow = comfy.workflow
    if selected_workflow is None:
        raise ValueError(
            "No ComfyUI workflow selected. Connect to ComfyUI and select a workflow before submitting jobs."
        )

    job_generator = ComfyJobGenerator(
        producer=iter_selected_prims,
        comfy_url=comfy.url,
    )
    job_generator.submit(
        interface,
        selected_workflow,
        use_inputs_for_output_filename_prefix=use_inputs_for_output_filename_prefix,
    )


class FieldWidget:
    def __init__(
        self,
        field: Field,
    ):
        self._field = field
        self._container: ui.Frame | None = None
        self._widget: ui.Widget | None = None
        self._model: ui.AbstractValueModel | None = None
        self._menu: ui.Menu | None = None
        self._override_backgrounds: list[ui.Rectangle] = []
        self._more_button: ui.Image | None = None
        self._indicator_circle: ui.Circle | None = None
        self._rebuild_task: asyncio.Task | None = None

    def __del__(self):
        self.destroy()

    def destroy(self) -> None:
        if self._rebuild_task is not None:
            self._rebuild_task.cancel()
            self._rebuild_task = None
        if self._menu is not None:
            self._menu.destroy()
            self._menu = None
        if self._container is not None:
            self._container.clear()
            self._container = None
        self._widget = None
        self._model = None
        self._field = None
        self._override_backgrounds.clear()
        self._more_button = None
        self._indicator_circle = None

    def _get_compatible_lazy_values(self) -> list[LazyValue]:
        return [x for x in LAZY_VALUE_REGISTRY if x.return_type == self._field.native_type]

    def _has_override(self) -> bool:
        if callable(self._field.value):
            return True
        # Check if value differs from default
        return self._field.value != self._field.default_value

    def _build_lazy_widget(self) -> tuple[ui.Widget, ui.AbstractValueModel | None, Callable | None]:
        func = self._field.value
        if isinstance(func, LazyValue):
            label = func.label
        else:
            label = getattr(func, "__name__", str(func))

        widget = ui.StringField(width=360, enabled=False, style={"color": 0xFFFFC734})
        widget.model.set_value(label)

        return widget, None, None

    def _build_value_widget(self) -> tuple[ui.Widget, ui.AbstractValueModel | None, Callable | None]:
        native_type = self._field.native_type
        width = 360

        if native_type is str:
            widget = ui.StringField(width=width)
            return widget, widget.model, widget.model.get_value_as_string

        if native_type is pathlib.Path:
            widget = ui.StringField(width=width)
            return widget, widget.model, lambda: pathlib.Path(widget.model.get_value_as_string())

        if native_type is int:
            widget = ui.IntField(width=width)
            return widget, widget.model, widget.model.get_value_as_int

        if native_type is float:
            widget = ui.FloatField(width=width)
            return widget, widget.model, widget.model.get_value_as_float

        if native_type is bool:
            widget = ui.CheckBox(width=width)
            return widget, widget.model, widget.model.get_value_as_bool

        if isinstance(native_type, type) and issubclass(native_type, enum.Enum):
            members = list(native_type)
            current_index = members.index(self._field.value) if self._field.value in members else 0
            widget = ui.ComboBox(current_index, *(x.value for x in members), width=width)

            def on_item_changed(_model, _item):
                idx = widget.model.get_item_value_model(_item).get_value_as_int()
                self._field.value = members[idx]

            widget.model.add_item_changed_fn(on_item_changed)
            return widget, None, None

        carb.log_error(f"Unsupported type for field {self._field.name}: {native_type}")
        raise NotImplementedError(f"Unsupported field type: {native_type}")

    def _on_value_changed(self, _) -> None:
        if self._indicator_circle is not None:
            has_override = self._has_override()
            if has_override:
                style_type_name_override = "OverrideIndicator"
                tooltip = (
                    "The displayed value is not the default value.\n\n"
                    "Click to reset the attribute to the default value."
                )
            else:
                style_type_name_override = "OverrideIndicatorForceDisabled"
                tooltip = "When highlighted, the displayed value is not the default value."

            self._indicator_circle.style_type_name_override = style_type_name_override
            self._indicator_circle.tooltip = tooltip

    def _setup_value_binding(self, getter: Callable | None) -> None:
        if self._model is None or getter is None:
            return

        def on_value_changed(_):
            self._field.value = getter()
            self._on_value_changed(_)

        self._model.set_value(self._field.value)
        self._model.add_value_changed_fn(on_value_changed)

    async def _deferred_rebuild(self) -> None:
        task = asyncio.current_task()
        try:
            await omni.kit.app.get_app().next_update_async()
            if self._field is not None and self._container is not None:
                self.rebuild()
        except asyncio.CancelledError:
            return
        finally:
            if self._rebuild_task is task:
                self._rebuild_task = None

    def _queue_rebuild(self) -> None:
        if self._rebuild_task is not None:
            self._rebuild_task.cancel()
        self._rebuild_task = asyncio.ensure_future(self._deferred_rebuild())

    def _reset_to_default(self) -> None:
        if self._field is None:
            return
        self._field.value = self._field.default_value
        self._queue_rebuild()

    def _switch_to_lazy(self, value: LazyValue) -> None:
        if self._field is None:
            return
        self._field.value = value
        self._queue_rebuild()

    def _show_more_menu(
        self,
        compatible_lazy_values: list[LazyValue],
        has_override: bool,
        button: int,
    ) -> None:
        if button != 0 or (not has_override and not compatible_lazy_values):
            return

        self._menu = ui.Menu("Field Options")
        with self._menu:
            if has_override:
                ui.MenuItem("Reset to Default", triggered_fn=self._reset_to_default)

            if compatible_lazy_values:
                if has_override:
                    ui.Separator()
                for lazy_value in compatible_lazy_values:
                    ui.MenuItem(
                        lazy_value.label,
                        triggered_fn=lambda lv=lazy_value: self._switch_to_lazy(lv),
                    )
        self._menu.show()

    def _build_ui_content(self) -> None:
        compatible_lazy_values = self._get_compatible_lazy_values()

        has_override = self._has_override()
        show_more = has_override or bool(compatible_lazy_values)

        with ui.HStack(spacing=ui.Pixel(8)):
            self._indicator_circle = ui.Circle(
                width=ui.Pixel(12),
                mouse_released_fn=lambda x, y, b, m: self._reset_to_default(),
            )
            if show_more:
                tooltip = (
                    "The displayed value has been modified.\n\nClick to view options."
                    if has_override
                    else "Click to select a value from RTX Remix."
                )
                self._more_button = ui.Image(
                    "",
                    name="More",
                    tooltip=tooltip,
                    mouse_released_fn=lambda x, y, b, m: self._show_more_menu(compatible_lazy_values, has_override, b),
                    width=ui.Pixel(16),
                )
            else:
                ui.Spacer(width=ui.Pixel(16))

            ui.Label(
                self._field.metadata.get("label", self._field.name),
                elided_text=True,
                tooltip=self._field.metadata.get("label", self._field.name),
                width=200,
            )

            # Main widget content
            if callable(self._field.value):
                self._widget, self._model, getter = self._build_lazy_widget()
            else:
                self._widget, self._model, getter = self._build_value_widget()
                self._setup_value_binding(getter)

        # Apply tooltip if available
        tooltip = self._field.metadata.get("tooltip")
        if tooltip and self._widget:
            self._widget.tooltip = tooltip

        self._on_value_changed(None)

    def build(self) -> ui.Frame:
        self._container = ui.Frame()
        with self._container:
            self._build_ui_content()
        return self._container

    def rebuild(self) -> None:
        if not self._container:
            return

        self._override_backgrounds.clear()
        self._more_button = None
        self._indicator_circle = None

        self._container.clear()
        with self._container:
            self._build_ui_content()


class FieldGroupWidget:
    def __init__(self, fields: list[Field], group_name: str = ""):
        self._fields = fields
        self._group_name = group_name
        self._field_widgets: dict[str, FieldWidget] = {}

    def __del__(self):
        self.destroy()

    def destroy(self) -> None:
        for field_widget in self._field_widgets.values():
            field_widget.destroy()
        self._field_widgets.clear()
        self._fields = []
        self._group_name = ""

    def build(self) -> ui.Widget:
        sorted_fields = sorted(self._fields, key=lambda f: (f.metadata.get("order", 0), f.name))

        frame = ui.CollapsableFrame(self._group_name, collapsed=bool(self._group_name))
        with frame:
            with ui.VStack(spacing=ui.Pixel(8)):
                for field in sorted_fields:
                    field_widget = FieldWidget(field)
                    self._field_widgets[field.name] = field_widget
                    field_widget.build()

        return frame


class FieldCollectionWidget:
    def __init__(self, fields: Iterable[Field]):
        self._fields = list(fields)
        self._groups: dict[str, FieldGroupWidget] = {}
        self._container: ui.Frame | None = None

        groups_dict: dict[str, list[Field]] = {}
        for field in self._fields:
            group_name = field.metadata.get("group", "")
            groups_dict.setdefault(group_name, []).append(field)
        for group_name, group_fields in groups_dict.items():
            self._groups[group_name] = FieldGroupWidget(group_fields, group_name)

        self.build()

    def __del__(self):
        self.destroy()

    def destroy(self) -> None:
        for group in self._groups.values():
            group.destroy()
        self._groups.clear()
        self._fields = []
        if self._container is not None:
            self._container.clear()
            self._container = None

    def build(self) -> ui.Widget:
        # container = ui.ScrollingFrame(name="WorkspaceBackground")
        self._container = ui.Frame()
        with self._container:
            with ui.HStack(spacing=ui.Pixel(8)):
                with ui.VStack(spacing=ui.Pixel(8)):
                    # Sort groups: unnamed group first, then alphabetically
                    for group_name in sorted(self._groups.keys(), key=lambda k: (bool(k), k)):
                        self._groups[group_name].build()

        return self._container


class ComfyJobSubmitterWidget:
    def __init__(
        self,
        interface: omni.flux.job_queue.core.interface.QueueInterface,
        comfy_url: str | None = None,
        context_name: str = "",
    ):
        self.interface = interface
        self._comfy = get_comfy_interface()
        if comfy_url is not None:
            self._comfy.set_url(comfy_url)
        self._workflows: list[str] = []
        self._connection_state = ConnectionState.DISCONNECTED
        self._ignore_workflow_changed = False
        self._ignore_combo_changed = False

        self._use_inputs_for_output_filename_prefix = True

        self._job_submitted_event = Event()
        self._field_collection_widget: FieldCollectionWidget | None = None

        # Subscribe to ComfyInterface events
        self._connected_sub = self._comfy.subscribe_connected_changed(self._on_comfy_connected_changed)
        self._workflow_sub = self._comfy.subscribe_workflow_changed(self._on_comfy_workflow_changed)

        with ui.Frame(width=0):
            with ui.VStack(spacing=ui.Pixel(8)):
                with ui.HStack(height=ui.Pixel(12), spacing=ui.Pixel(8)):
                    ui.Label("COMFYUI URL", name="PropertiesPaneSectionTitle", width=120)
                    self.url_widget = ui.StringField(name="Disconnected", width=300)
                    self.url_widget.model.set_value(self._comfy.url)
                    self.connect_btn = ui.Button("Connect", width=100, clicked_fn=self._connect_to_comfy)
                    self._open_browser_btn = ui.Image(
                        "",
                        name="OpenInBrowser",
                        tooltip="Open ComfyUI in the default browser",
                        height=ui.Pixel(24),
                        width=ui.Pixel(24),
                        mouse_pressed_fn=self._open_in_browser,
                        enabled=False,
                    )

                ui.Spacer(height=ui.Pixel(12))
                with ui.VStack(spacing=ui.Pixel(16)):
                    self._workflow_stack = ui.HStack(height=ui.Pixel(12), spacing=ui.Pixel(8))
                    self._workflow_stack.visible = False
                    with self._workflow_stack:
                        ui.Label("WORKFLOW", name="PropertiesPaneSectionTitle", width=120)
                        self.workflows_combo_widget = ui.ComboBox(0, width=300 + 8 + 100)
                        self.workflows_combo_widget.model.add_item_changed_fn(self._on_workflow_combo_changed)
                        self._workflows_refresh = ui.Image(
                            "",
                            name="Refresh",
                            tooltip="Refresh the workflow from ComfyUI",
                            height=ui.Pixel(24),
                            width=ui.Pixel(24),
                            mouse_pressed_fn=lambda *_: self._connect_to_comfy(True),
                        )
                        ui.Spacer()

                    self.workflow_frame = ui.Frame(height=0)

                ui.Spacer()

                with ui.HStack(spacing=ui.Pixel(8), height=0):
                    ui.Label(
                        "Use input names for output filename prefix",
                        width=0,
                        tooltip="This attempts to make the output file names based on the input filename(s). "
                        "If this is set, then repeated runs will overwrite existing files.",
                    )
                    checkbox = ui.CheckBox(width=0)
                    checkbox.model.set_value(self._use_inputs_for_output_filename_prefix)

                    def _on_checkbox_changed(_model):
                        self._use_inputs_for_output_filename_prefix = _model.get_value_as_bool()

                    checkbox.model.add_value_changed_fn(_on_checkbox_changed)

                self._submit_btn = ui.Button(
                    "Submit Job",
                    height=ui.Pixel(40),
                    clicked_fn=self._on_submit_job_clicked,
                )
                self._submit_btn.enabled = False

        # Initialize UI from the interface's current state
        self._on_comfy_connected_changed(self._comfy.connection_state)
        self._on_comfy_workflow_changed(self._comfy.workflow)

    def __del__(self):
        self.destroy()

    def destroy(self) -> None:
        self._connected_sub = None
        self._workflow_sub = None
        self._destroy_field_collection_widget()
        self._workflows.clear()
        self.interface = None
        self._comfy = None
        self._job_submitted_event = Event()
        self.url_widget = None
        self.connect_btn = None
        self._open_browser_btn = None
        self._workflow_stack = None
        self.workflows_combo_widget = None
        self._workflows_refresh = None
        self.workflow_frame = None
        self._submit_btn = None

    def _destroy_field_collection_widget(self) -> None:
        if self._field_collection_widget is not None:
            self._field_collection_widget.destroy()
            self._field_collection_widget = None

    def _open_in_browser(self, _x: float, _y: float, button: int, _modifiers: int) -> None:
        """Open the ComfyUI URL in the default browser."""
        if button != 0 or not self._comfy or not self._comfy.url:
            return

        if self._connection_state == ConnectionState.CONNECTED:
            webbrowser.open(self._comfy.url)

    def _update_ui_for_connection_state(self) -> None:
        """Update all UI elements to reflect the current connection state."""
        is_connected = self._connection_state == ConnectionState.CONNECTED

        self.connect_btn.text = self._connection_state.button_text
        self.url_widget.enabled = not is_connected
        self.url_widget.name = self._connection_state.status_text
        self._workflow_stack.visible = is_connected
        self._submit_btn.enabled = is_connected
        self._open_browser_btn.enabled = is_connected
        self._open_browser_btn.tooltip = (
            "Open ComfyUI in the default browser"
            if is_connected
            else "Connect to ComfyUI to enable opening the user interface in the default browser"
        )

    def _clear_workflows(self) -> None:
        """Clear all workflow-related state and UI."""
        self._destroy_field_collection_widget()
        self._ignore_combo_changed = True
        try:
            for item in self.workflows_combo_widget.model.get_item_children():
                self.workflows_combo_widget.model.remove_item(item)
        finally:
            self._ignore_combo_changed = False
        self.workflow_frame.clear()
        self._workflows.clear()

    def _load_workflows(self) -> None:
        """Load workflows from ComfyUI and populate the combo widget."""
        self._workflows = self._comfy.get_api_workflows()
        self._ignore_combo_changed = True
        try:
            for source_type, workflow_name in self._workflows:
                self.workflows_combo_widget.model.append_child_item(
                    None, ui.SimpleStringModel(f"({source_type}) {workflow_name}")
                )
        finally:
            self._ignore_combo_changed = False

        # Explicitly load the default (first) workflow
        if self._workflows:
            self._select_workflow(0)

    def _do_connect(self) -> bool:
        """
        Attempt to connect to ComfyUI.

        Only performs the connection check and updates state. All side effects
        (loading workflows, updating UI) happen in _on_comfy_connected_changed.

        Returns:
            bool: True if connection was successful, False otherwise.
        """
        self._comfy.set_url(self.url_widget.model.get_value_as_string())

        if not self._comfy.is_alive():
            carb.log_error(f"Could not connect to ComfyUI at {self._comfy.url}")
            return False

        self._comfy.set_connected(ConnectionState.CONNECTED)  # Event handler does the rest
        return True

    def _do_disconnect(self) -> None:
        """Disconnect from ComfyUI by updating connection state."""
        self._comfy.set_connected(ConnectionState.DISCONNECTED)  # Event handler does the rest

    def _connect_to_comfy(self, value: bool | None = None) -> None:
        """
        Connect to or disconnect from ComfyUI.

        Args:
            value: If None, toggles the current connection state.
                   If True, connects (or refreshes if already connected).
                   If False, disconnects.
        """
        if value is None:
            value = self._connection_state == ConnectionState.DISCONNECTED

        if value:
            self._do_connect()
        else:
            self._do_disconnect()

    def _on_comfy_connected_changed(self, connection_state: ConnectionState) -> None:
        """
        React to connection state changes by handling all side effects.

        This is the reactive handler for connection state changes. ALL side effects
        (loading workflows, clearing UI, updating UI) happen here - NOT in the button
        click handlers. This ensures the UI reacts to state changes, not button clicks.

        Args:
            connection_state: The new connection state
        """
        self._connection_state = connection_state
        self._clear_workflows()  # Always clear first
        if connection_state == ConnectionState.CONNECTED:
            self._load_workflows()  # Load new workflows when connecting
        self._update_ui_for_connection_state()

    @ignore_function_decorator(["_ignore_workflow_changed"])
    def _on_comfy_workflow_changed(self, workflow: Workflow | None) -> None:
        """
        React to workflow changes by rebuilding the workflow UI.

        Uses ignore_function_decorator to prevent reacting to events triggered
        by UI callbacks (combo selection) which already handle their own UI updates.

        Args:
            workflow: The new workflow, or None if cleared
        """
        self._destroy_field_collection_widget()
        self.workflow_frame.clear()
        if workflow:
            with self.workflow_frame:
                self._field_collection_widget = FieldCollectionWidget(workflow.inputs)

    def _select_workflow(self, index: int) -> None:
        """Fetch workflow data for the given index, store it, and rebuild the UI."""
        if not self._workflows:
            return
        if index < 0 or index >= len(self._workflows):
            index = 0
        source_type, workflow_name = self._workflows[index]
        workflow_dict = self._comfy.get_workflow_data(source_type, workflow_name)
        workflow = Workflow.from_dict(
            workflow_dict,
            name=workflow_name.replace(".json", ""),
        )
        # Suppress _on_comfy_workflow_changed while we store the workflow and rebuild the UI
        # ourselves, to avoid a double-build.
        self._ignore_workflow_changed = True
        try:
            self._comfy.set_workflow(workflow)

            self._destroy_field_collection_widget()
            self.workflow_frame.clear()
            with self.workflow_frame:
                self._field_collection_widget = FieldCollectionWidget(workflow.inputs)
        finally:
            self._ignore_workflow_changed = False

    def _on_workflow_combo_changed(self, model, item) -> None:
        if self._ignore_combo_changed:
            return
        index = model.get_item_value_model(item).get_value_as_int()
        self._select_workflow(index)

    def _on_submit_job_clicked(self) -> None:
        try:
            submit_selected_prims_to_comfy(
                interface=self.interface,
                workflow=self._comfy.workflow,
                use_inputs_for_output_filename_prefix=self._use_inputs_for_output_filename_prefix,
            )
        except ValueError as exc:
            carb.log_error(str(exc))
            return
        self._job_submitted_event()

    def subscribe_job_submitted_event(self, callback: Callable[[], None]) -> EventSubscription:
        return EventSubscription(self._job_submitted_event, callback)


class JobQueueWidget:
    """
    A widget which combines the controls for the job scheduler and the queue view.
    """

    def __init__(
        self,
        interface: omni.flux.job_queue.core.interface.QueueInterface | None = None,
        context_name: str = "",
    ):
        if interface is None:
            interface = get_job_queue_interface()
        self.interface = interface
        self.context_name = context_name
        self.queue_widget: omni.flux.job_queue.widget.QueueWidget | None = None
        self.submitter_widget: ComfyJobSubmitterWidget | None = None
        self._job_submitted_subscription: EventSubscription | None = None

        # Create a CallbackExecutor with the ApplyHandlerRegistry
        callback_executor = omni.flux.job_queue.widget.CallbackExecutor(
            interface=self.interface,
            apply_handler=omni.flux.job_queue.widget.ApplyHandlerRegistry.apply,
            can_apply=omni.flux.job_queue.widget.ApplyHandlerRegistry.can_apply,
            has_been_applied=omni.flux.job_queue.widget.ApplyHandlerRegistry.has_been_applied,
        )

        with ui.HStack(spacing=ui.Pixel(16)):
            self.submitter_widget = ComfyJobSubmitterWidget(self.interface, context_name=context_name)
            self.queue_widget = omni.flux.job_queue.widget.QueueWidget(
                interface=self.interface,
                callback_executor=callback_executor,
            )

        self._job_submitted_subscription = self.submitter_widget.subscribe_job_submitted_event(
            lambda: self.queue_widget.model.refresh(force=True)
        )

    def __del__(self):
        self.destroy()

    def destroy(self) -> None:
        self._job_submitted_subscription = None
        if self.submitter_widget is not None:
            self.submitter_widget.destroy()
            self.submitter_widget = None
        if self.queue_widget is not None:
            self.queue_widget.destroy()
            self.queue_widget = None


class AIToolsWidget:
    def __init__(self, context_name: str = ""):
        self.context_name = context_name
        self.root: ui.Frame | None = None
        self.job_queue_widget: JobQueueWidget | None = None
        self.build()

    def build(self):
        self.root = ui.ScrollingFrame(name="WorkspaceBackground")
        with self.root:
            with ui.VStack():
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(16))
                    with ui.VStack():
                        ui.Spacer(height=ui.Pixel(16))
                        self.job_queue_widget = JobQueueWidget(context_name=self.context_name)
                        ui.Spacer(height=ui.Pixel(16))
                    ui.Spacer(width=ui.Pixel(16))

    def __del__(self):
        self.destroy()

    def show(self, visible: bool):
        if self.root is not None:
            self.root.visible = visible

    def destroy(self):
        if self.job_queue_widget is not None:
            self.job_queue_widget.destroy()
            self.job_queue_widget = None
        if self.root is not None:
            self.root.destroy()
        self.root = None
