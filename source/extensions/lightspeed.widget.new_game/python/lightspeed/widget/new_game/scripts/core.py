"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from pathlib import Path

from typing import Optional
import carb
import carb.settings
import json
from lightspeed.widget.content_viewer.scripts.core import ContentData, ContentDataAdd, ContentViewerCore
from pydantic import ValidationError

from .utils import get_instance as get_game_json_instance


class GameCore(ContentViewerCore):
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
        super(GameCore, self).__init__()
        self._settings = carb.settings.get_settings()
        self._filter = None

        self.__current_game = None
        self.__on_current_game_changed = self._Event()

    def set_filter(self, filter: str):
        self._filter = filter

    def set_current_game(self, data: Optional[ContentData]):
        self.__current_game = data
        self._current_game_changed()

    def get_current_game(self) -> ContentData:
        return self.__current_game

    def _current_game_changed(self):
        """Call the event object that has the list of functions"""
        self.__on_current_game_changed(self.__current_game)

    def subscribe_current_game_changed(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._EventSubscription(self.__on_current_game_changed, fn)

    def save_current_game_in_json(self):
        if isinstance(self.__current_game, ContentDataAdd):
            get_game_json_instance().append_path_to_file(self.__current_game.path, self.__current_game.title)

    @property
    def default_attr(self):
        result = super(GameCore, self).default_attr
        result.update({})
        return result

    def _get_content_data(self):
        json_data = get_game_json_instance().get_file_data()
        result = []
        for title, data in json_data.items():
            try:
                result.append(ContentData(title=title, path=data.get("path")))
            except ValidationError as e:
                carb.log_error(e.json())
        return result

    def destroy(self):
        super(GameCore, self).destroy()
