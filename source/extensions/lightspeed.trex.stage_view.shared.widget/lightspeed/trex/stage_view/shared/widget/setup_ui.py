"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb.events
import carb.settings
import omni.usd
from omni.kit.widget.stage import DefaultSelectionWatch as _SelectionWatch
from omni.kit.widget.stage import StageWidget as _StageWidget
from omni.kit.widget.stage.stage_style import Styles as _StageStyles

from .stage_settings import StageSettings as _StageSettings


class _CustomizedStageWidget(_StageWidget):
    @_StageWidget.show_prim_display_name.setter
    def show_prim_display_name(self, value):
        _StageWidget.show_prim_display_name.fset(self, value)
        _StageSettings().show_prim_displayname = value

    @_StageWidget.children_reorder_supported.setter
    def children_reorder_supported(self, value):
        _StageWidget.children_reorder_supported.fset(self, value)
        _StageSettings().should_keep_children_order = value

    @_StageWidget.auto_reload_prims.setter
    def auto_reload_prims(self, value):
        _StageWidget.auto_reload_prims.fset(self, value)
        _StageSettings().auto_reload_prims = value


class SetupUI:
    """The Stage widget"""

    def __init__(self, usd_context_name: str = ""):
        self._usd_context = omni.usd.get_context(usd_context_name)

        _StageStyles.on_startup()

        # Get list of columns from settings
        self._settings = carb.settings.get_settings()
        self._columns = ["Type"]  # visibility is broken in the current Kit SDK because it doesn't pass the context

        self._stage_widget = _CustomizedStageWidget(
            None,
            columns_enabled=self._columns,
            children_reorder_supported=_StageSettings().should_keep_children_order,
            show_prim_display_name=_StageSettings().show_prim_displayname,
            auto_reload_prims=_StageSettings().auto_reload_prims,
        )

        # The Open/Close Stage logic
        self.__enable_context_event = True
        self._stage_subscription = self._usd_context.get_stage_event_stream().create_subscription_to_pop(
            self._on_usd_context_event, name="Stage Widget USD Stage Open/Closing Listening"
        )

        self._on_stage_opened()

        # The selection logic
        self._selection = _SelectionWatch(usd_context=self._usd_context)
        self._stage_widget.set_selection_watch(self._selection)

    def destroy(self):
        """
        Called by extension before destroying this object. It doesn't happen automatically.
        Without this hot reloading doesn't work.
        """
        if self._selection:
            self._selection.destroy()
        self._stage_widget.destroy()
        self._stage_widget = None
        self._stage_subscription = None
        self._settings = None

    def enable_context_event(self, value):
        self.__enable_context_event = value

    def _on_usd_context_event(self, event: carb.events.IEvent):
        """Called on USD Context event"""
        if not self.__enable_context_event:
            return
        if event.type == int(omni.usd.StageEventType.OPENED):
            self._on_stage_opened()
        elif event.type == int(omni.usd.StageEventType.CLOSING):
            self._on_stage_closing()

    def _on_stage_opened(self):
        """Called when opening a new stage"""
        stage = self._usd_context.get_stage()
        if not stage:
            return

        self._stage_widget.open_stage(stage)

    def _on_stage_closing(self):
        """Called when close the stage"""
        self._stage_widget.open_stage(None)
