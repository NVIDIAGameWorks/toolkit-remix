"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import functools
from pathlib import Path
from typing import Optional

import carb
from lightspeed.widget.content_viewer.scripts.core import ContentData, ContentViewerCore
from pydantic import ValidationError

from .utils import get_capture_image, get_captures


class GameCapturesCore(ContentViewerCore):
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

    def __init__(self):
        super().__init__()
        self.__current_game_capture_folder = None
        self.__current_capture = None
        self.__on_current_game_capture_folder_changed = self._Event()
        self.__on_current_capture_changed = self._Event()

    @property
    def default_attr(self):
        result = super().default_attr
        result.update({})
        return result

    def set_current_game_capture_folder(self, data: Optional[ContentData]):
        self.__current_game_capture_folder = data
        self._current_game_capture_folder_changed()

    def get_current_game_capture_folder(self) -> Optional[ContentData]:
        return self.__current_game_capture_folder

    def _current_game_capture_folder_changed(self):
        """Call the event object that has the list of functions"""
        self.__on_current_game_capture_folder_changed(self.__current_game_capture_folder)

    def subscribe_current_game_capture_folder_changed(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_current_game_capture_folder_changed, fn)

    def set_current_capture(self, data: Optional[ContentData]):
        self.__current_capture = data
        self._current_capture_changed()

    def get_current_capture(self) -> Optional[ContentData]:
        return self.__current_capture

    def _current_capture_changed(self):
        """Call the event object that has the list of functions"""
        self.__on_current_capture_changed(self.__current_capture)

    def subscribe_current_capture_changed(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_current_capture_changed, fn)

    def _get_capture_image(self, capture_usd_path: str) -> Optional[str]:
        return get_capture_image(capture_usd_path)

    def _get_content_data(self):
        files = get_captures(self.__current_game_capture_folder)

        result = []
        for path in files:
            try:
                p_obj = Path(path)
                result.append(
                    ContentData(
                        title=p_obj.stem.capitalize(),
                        path=path,
                        image_path_fn=functools.partial(self._get_capture_image, path),
                        image_primary_detail_fn=functools.partial(self._get_capture_image, path),
                    )
                )
            except ValidationError as e:
                carb.log_error(e.json())

        return result
