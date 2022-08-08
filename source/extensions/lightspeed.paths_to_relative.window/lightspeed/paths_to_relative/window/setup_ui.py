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

import omni.ui as ui
import omni.usd
from lightspeed.error_popup.window import ErrorPopup
from lightspeed.paths_to_relative.core import PathsToRelative, deep_update_data
from lightspeed.progress_popup.window import ProgressPopup
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .tree import delegate, model


class PathsToRelativeWindow:
    def __init__(self):
        self.__default_attr = {
            "_core": None,
            "_model": None,
            "_delegate": None,
            "_window": None,
            "_tree": None,
            "_progress_bar": None,
            "_error_popup": None,
        }
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self._core = PathsToRelative()
        self._delegate = delegate.Delegate()
        self._model = model.ListModel()

        self.__create_ui()

    def __create_ui(self):
        """Create the main UI"""
        window_name = "Paths to relative window"
        self._window = ui.Window(window_name, name=window_name, width=1280, height=600, visible=False)

        with self._window.frame:
            with ui.VStack():
                ui.Button("Scan current stage (included all dependencies)", clicked_fn=self._scan, height=24)
                with ui.ScrollingFrame(
                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
                    style_type_name_override="TreeView",
                ):
                    self._tree = ui.TreeView(
                        self._model,
                        delegate=self._delegate,
                        root_visible=False,
                        header_visible=True,
                        columns_resizable=True,
                        column_widths=[ui.Pixel(90), ui.Percent(70), ui.Percent(30)],
                    )
                ui.Button("Fix it!", clicked_fn=self._fix, height=24)

    def _batch_upscale_set_progress(self, progress):
        if not self._progress_bar:
            self._progress_bar = ProgressPopup(title="Scanning")
            self._progress_bar.show()
        self._progress_bar.set_progress(progress)

    @omni.usd.handle_exception
    async def _run_batch_convert(self, scan_only=True):
        def grab_data(item):
            data = {}
            if not item.enabled:
                return data
            if item.children:
                for child in item.children:
                    deep_update_data(data, grab_data(child))
            else:
                deep_update_data(data, {item.stage_path: [item.attr_path]})
            return data

        if not self._progress_bar:
            self._progress_bar = ProgressPopup(title="Scanning" if scan_only else "Fixing")
        self._progress_bar.set_progress(0)
        self._progress_bar.show()

        data = None
        if not scan_only:
            # grab enabled stuff
            data = {}
            for item in self._model.get_item_children(None):
                deep_update_data(data, grab_data(item))

        await asyncio.sleep(0.01)

        result, errors_messages = await PathsToRelative.convert_current_stage(
            progress_callback=self._batch_upscale_set_progress, scan_only=scan_only, only_data=data
        )
        if scan_only:
            self._model.refresh(result)
        else:
            # we re-scan after the fix to update the UI
            await self._run_batch_convert()

        if self._progress_bar:
            self._progress_bar.hide()
            self._progress_bar = None

        if errors_messages:
            self._error_popup = ErrorPopup("Errors!", "There are some errors:", errors_messages)
            self._error_popup.show()

    def _scan(self):
        asyncio.ensure_future(self._run_batch_convert())

    def _fix(self):
        asyncio.ensure_future(self._run_batch_convert(scan_only=False))

    def toggle_window(self):
        if self._window:
            self._window.visible = not self._window.visible

    def destroy(self):
        _reset_default_attrs(self)
