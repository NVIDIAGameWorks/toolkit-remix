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
import uuid
from pathlib import Path
from typing import Optional

import carb
import omni.client
import omni.ext
import omni.usd
from lightspeed.common import constants
from lightspeed.layer_manager.scripts.core import LayerManagerCore, LayerType
from omni.kit.tool.collect.collector import Collector

from .post_process import LightspeedPosProcessExporter
from .pre_process import preprocess


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

    def get_default_export_path(self, create_if_not_exist: bool = False) -> Optional[str]:
        current_game_capture_folder = self._layer_manager.game_current_game_capture_folder()
        if not current_game_capture_folder:
            return None
        path = str(Path(current_game_capture_folder.path).parent.joinpath(constants.GAME_READY_ASSETS_FOLDER)) + os.sep
        if create_if_not_exist:
            Path(path).mkdir(parents=True, exist_ok=True)
        return path

    def check_export_path(self, path) -> bool:
        stage = omni.usd.get_context().get_stage()
        if stage.GetRootLayer().anonymous:
            carb.log_error("Please save your stage first")
            return False
        if not path:
            carb.log_error("Please set a folder for the export")
            return False
        else:
            result, entry = omni.client.stat(path)
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                carb.log_error("The export path should be an existing folder")
                return False
        # detect when a user tries to export into gameReadyAssets while using gameReadyAsset/replacements.usda
        replacement_layer = self._layer_manager.get_layer(LayerType.replacement)
        replacement_layer_dir_path = Path(replacement_layer.realPath).parent.resolve()
        if str(replacement_layer_dir_path) == str(Path(path).resolve()):
            carb.log_error(
                "Cannot export to the same folder in which the source replacements layer resides: "
                + str(replacement_layer_dir_path)
            )
            return False
        return True

    def _start_exporting(self, export_folder):
        context = omni.usd.get_context()
        # Save the current stage
        context.save_stage()
        # cache workspace stage path, which is currently open
        workspace_stage_path = context.get_stage_url()
        workspace_stage_path_norm = omni.client.normalize_url(workspace_stage_path)

        # Get current stage path
        layer = self._layer_manager.get_layer(LayerType.replacement)
        if layer is None:
            carb.log_error("Can't find the replacement layer")
            return

        preprocess(self._layer_manager)

        usd_path = layer.realPath
        # Make a temporary copy of the replacement layer with the preprocessing applied.  This is needed for the
        # exporter to pick up any changed dependencies.
        temp_file_path = os.path.join(os.path.dirname(usd_path), f"pre_processed_replacement_{str(uuid.uuid4())}.usda")
        layer.Export(temp_file_path)

        self._progress_text_changed(f"Analyzing USD {os.path.basename(usd_path)}...")
        self._collector = Collector(temp_file_path, export_folder, False, True, False)

        def progress_callback(step, total):
            self._progress_text_changed(f"Collecting USD {os.path.basename(usd_path)}...")
            if total != 0:
                self._progress_changed(float(step) / total)
            else:
                self._progress_changed(0.0)

        async def _deferred_finish_callback():
            export_file_path = export_folder
            if not export_file_path.endswith("/"):
                export_file_path += "/"
            # The collector makes a copy of the temporary replacement layer, so rename that to the intended destination.
            export_file_path_norm = omni.client.normalize_url(export_file_path + os.path.basename(temp_file_path))
            dest_file_path_norm = omni.client.normalize_url(export_file_path + os.path.basename(usd_path))
            os.replace(export_file_path_norm, dest_file_path_norm)

            self._progress_text_changed(f"Post Processing USD {os.path.basename(usd_path)}...")
            # now process/optimize geo for game
            await self._post_exporter.process(dest_file_path_norm)

            # reopen original stage
            # TODO: Crash, use async function instead, waiting OM-42168
            # omni.usd.get_context().open_stage(workspace_stage_path)
            await context.open_stage_async(workspace_stage_path_norm)

            # Delete the temporary pre-processed replacement layer.
            os.remove(temp_file_path)

            self._finish_export()

        def finish_callback():
            loop = asyncio.get_event_loop()
            asyncio.ensure_future(_deferred_finish_callback(), loop=loop)

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
