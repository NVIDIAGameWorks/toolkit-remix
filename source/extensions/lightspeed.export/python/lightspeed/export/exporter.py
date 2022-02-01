"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import os
from pathlib import Path
from typing import Optional

import carb
import omni
import omni.client
import omni.ext
from lightspeed.common.constants import GAME_READY_ASSETS_FOLDER, LSS_FOLDER
from lightspeed.layer_manager.scripts.core import LayerManagerCore, LayerType
from lightspeed.layer_manager.scripts.layers.replacement import LSS_LAYER_GAME_NAME, LSS_LAYER_GAME_PATH
from lightspeed.widget.content_viewer.scripts.core import ContentData
from omni.kit.tool.collect.collector import Collector

from .post_process import LightspeedPosProcessExporter


class LightspeedExporterCore:
    class _Event(set):
        """
        A list of callable objects. Calling an instance of this will cause a
        call to each item in the list in ascending order by index.
        """

        def __call__(self, *args, **kwargs):
            """Called when the instance is “called” as a function"""
            # Call all the saved functions
            for f in self:
                f(*args, **kwargs)

        def __repr__(self):
            """
            Called by the repr() built-in function to compute the “official”
            string representation of an object.
            """
            return f"Event({set.__repr__(self)})"

    class _EventSubscription:
        """
        Event subscription.

        _Event has callback while this object exists.
        """

        def __init__(self, event, fn):
            """
            Save the function, the event, and add the function to the event.
            """
            self._fn = fn
            self._event = event
            event.add(self._fn)

        def __del__(self):
            """Called by GC."""
            self._event.remove(self._fn)

    def __init__(self, export_button_fn=None, cancel_button_fn=None):
        self.__default_attr = {"_layer_manager": None, "_post_exporter": None, "_collector": None}
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self.__on_progress_changed = self._Event()
        self.__on_progress_text_changed = self._Event()
        self.__on_finish_export = self._Event()

        self.__collector_weakref = None
        self._export_button_fn = export_button_fn
        self._cancel_button_fn = cancel_button_fn
        self._layer_manager = LayerManagerCore()
        self._post_exporter = LightspeedPosProcessExporter()

    def _progress_changed(self, progress: float = None):
        """Call the event object that has the list of functions"""
        self.__on_progress_changed(progress)

    def subscribe_progress_changed(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_progress_changed, fn)

    def _progress_text_changed(self, text: str = None):
        """Call the event object that has the list of functions"""
        self.__on_progress_text_changed(text)

    def subscribe_progress_text_changed(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_progress_text_changed, fn)

    def _finish_export(self):
        """Call the event object that has the list of functions"""
        self.__on_finish_export()

    def subscribe_finish_export(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_finish_export, fn)

    def set_export_fn(self, export_fn):
        self._export_button_fn = export_fn

    def set_cancel_fn(self, cancel_fn):
        self._cancel_button_fn = cancel_fn

    def export(self, export_dir):
        if self._export_button_fn:
            self._export_button_fn(export_dir)
        else:
            self._start_exporting(export_dir)

    def cancel(self):
        if self._cancel_button_fn:
            self._cancel_button_fn()
        carb.log_info("Cancel export...")

        if self._collector:
            self._collector.cancel()

    def _game_current_game_from_replacement_layer(self) -> Optional["ContentData"]:
        """Returns true if the layer is already watched"""
        layer_replacement = self._layer_manager.get_layer(LayerType.replacement)
        # we only save stage that have a replacement layer
        if not layer_replacement:
            carb.log_error("Can't find the replacement layer in the current stage")
            return None
        title = layer_replacement.customLayerData.get(LSS_LAYER_GAME_NAME)
        if not title:
            carb.log_error("Can't find the game title from the replacement layer")
            return None
        path = layer_replacement.customLayerData.get(LSS_LAYER_GAME_PATH)
        if not path:
            carb.log_error("Can't find the game path from the replacement layer")
            return None
        return ContentData(title=title, path=path)

    def get_default_export_path(self):
        current_game = self._game_current_game_from_replacement_layer()
        if not current_game:
            return ""
        return str(Path(current_game.path).parent.joinpath(LSS_FOLDER, GAME_READY_ASSETS_FOLDER)) + os.sep

    def check_export_path(self, path) -> bool:
        if not path:
            carb.log_error("Please set a folder for the export")
            return False
        else:
            result, entry = omni.client.stat(path)
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                carb.log_error("The export path should be an existing folder")
                return False
        return True

    def _start_exporting(self, export_folder):
        # Save the current stage
        omni.usd.get_context().save_stage()

        # Get current stage path
        layer = self._layer_manager.get_layer(LayerType.replacement)
        if layer is None:
            carb.log_error("Can't find the replacement layer")
            return

        usd_path = layer.realPath
        self._progress_text_changed(f"Analyzing USD {os.path.basename(usd_path)}...")
        self._collector = Collector(usd_path, export_folder, False, True, False)

        def progress_callback(step, total):
            self._progress_text_changed(f"Collecting USD {os.path.basename(usd_path)}...")
            if total != 0:
                self._progress_changed(float(step) / total)
            else:
                self._progress_changed(0.0)

        def finish_callback():
            # now process/optimize geo for game
            file_path = export_folder
            if not file_path.endswith("/"):
                file_path += "/"
            file_path += os.path.basename(usd_path)
            stage_path = omni.usd.get_context().get_stage_url()
            self._post_exporter.process(omni.client.normalize_url(file_path))
            # reopen original stage
            omni.usd.get_context().open_stage(stage_path)
            self._finish_export()

        asyncio.ensure_future(self._collector.collect(progress_callback, finish_callback))

    def destroy(self):
        self.__collector_weakref = None
        for attr, value in self.__default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()
                del m_attr
                setattr(self, attr, value)
