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
import functools
import traceback
from pathlib import Path
from typing import List, Optional

import carb
import carb.input
import omni.kit
import omni.ui as ui

from .core import ContentData, ContentDataAdd, ContentViewerCore
from .ui_detail_popup import AssetDetailWindow
from .utils import is_path_readable


def handle_exception(func):
    """
    Decorator to print exception in async functions

    TODO: The alternative way would be better, but we want to use traceback.format_exc for better error message.
        result = await asyncio.gather(*[func(*args)], return_exceptions=True)
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            # We always cancel the task. It's not a problem.
            pass
        except Exception as e:  # noqa PLW0703, PLC0103
            carb.log_error(f"Exception when async '{func}'")
            carb.log_error(f"{e}")
            carb.log_error(f"{traceback.format_exc()}")

    return wrapper


def async_wrap(func):
    @asyncio.coroutine
    @functools.wraps(func)
    def run(*args, loop=None, executor=None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = functools.partial(func, *args, **kwargs)
        return loop.run_in_executor(executor, pfunc)

    return run


class ContentItemAdd:

    NO_FONT_SIZE = 14
    TITLE_FONT_SIZE = 14

    def __init__(self, content_data: ContentDataAdd, core):
        """Content Item represent the UI of 1 content in the grid"""
        self._default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._style = {
            "Image::Add": {"color": 0xFFDADADA},
            "Rectangle.Overlay": {"background_color": 0x00FFFFFF},
            "Rectangle.Overlay:hovered": {"background_color": 0x21FFFFFF},
            "Rectangle::Wide": {"background_color": 0x00FFFFFF},
            "Rectangle::Wide:selected": {
                "border_color": 0xFFC5911A,
                "border_width": 1.0,
                "background_color": 0x70C5911A,
            },
        }
        self.content_data = content_data
        self._core = core

        self.__overlay_wide_rectangle = None
        self.__overlay_highlight_rectangle = None  # noqa PLW0238

        self.__create_ui()

    @property
    def current_extension_path(self):
        current_path = Path(__file__).parent
        for _ in range(4):
            current_path = current_path.parent
        return current_path

    def _get_icon_path(self, name: str):
        """Get an icon path form his name"""
        path = self.current_extension_path.joinpath("icons", f"{name}.svg")
        if path.exists():
            return str(path)
        return None

    @property
    def default_attr(self):
        return {"_core": None, "_current_extension_path": None}

    def __create_ui(self):
        """Create the UI"""
        with ui.ZStack(style=self._style):
            with ui.HStack():
                ui.Spacer(width=ui.Fraction(1))
                self.__overlay_wide_rectangle = ui.Rectangle(
                    name="Wide",
                    mouse_pressed_fn=self._on_mouse_clicked,
                    mouse_released_fn=self._on_mouse_released,
                    mouse_moved_fn=self._on_mouse_moved,
                    width=ui.Fraction(80),
                )
                ui.Spacer(width=ui.Fraction(1))
            with ui.HStack():
                ui.Spacer(width=ui.Fraction(1))
                with ui.VStack(width=ui.Fraction(30)):
                    ui.Spacer(height=ui.Fraction(1))
                    with ui.VStack(height=ui.Fraction(30), spacing=8):
                        with ui.ZStack():
                            # no image/loading frame for label
                            with ui.Frame():
                                ui.Label("Image", name="NoImage")
                                ui.Image(self._get_icon_path("add"), name="Add")

                            # highlight rectangle when the mouse is over it
                            self.__overlay_highlight_rectangle = ui.Rectangle(  # noqa PLW0238
                                style_type_name_override="Rectangle.Overlay"
                            )
                    ui.Spacer(height=ui.Fraction(1))
                ui.Spacer(width=ui.Fraction(1))

    def on_resized_grid(self, grid_size):
        pass

    def set_selected(self, value):
        """Select the item"""
        self.__overlay_wide_rectangle.selected = value

    def is_selected(self):
        return self.__overlay_wide_rectangle.selected

    def _on_mouse_clicked(self, x, y, b, m):  # noqa PLC0103
        """Called when the item is clicked on"""
        self._core.set_item_was_clicked(True)
        self._core.set_selection(self.content_data)

    def _on_mouse_released(self, x, y, b, m):  # noqa PLC0103
        """Called when the mouse is released"""
        pass

    def _on_mouse_moved(self, x, y, b, m):  # noqa PLC0103
        """Called when the mouse is moved"""
        pass

    def destroy(self):
        self.__overlay_highlight_rectangle = None  # noqa PLW0238
        self.__overlay_wide_rectangle = None
        for attr, value in self.default_attr.items():
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


class ContentItem:

    NO_FONT_SIZE = 14
    TITLE_FONT_SIZE = 14
    MULTI_SELECTION = True
    DRAG = False
    CAN_CHOSE_CHECKPOINT = False

    def __init__(self, content_data: ContentData, core, asset_detail_windows):
        """Content Item represent the UI of 1 content in the grid"""
        self._default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self.content_data = content_data
        self._core = core
        self._asset_detail_windows = asset_detail_windows
        self._is_usd_path_valid = False
        self._style = {}
        self.__background_image = None  # noqa PLW0238
        self.__checkpoint_zstack = None
        self.__checkpoint_combobox = None
        self.__overlay_wide_rectangle = None
        self.__overlay_highlight_rectangle = None
        self.__no_image_frame = None
        self.__no_usd_path_frame = None
        self.__title_frame = None
        self.__image_frame = None
        self.__label_message_no_image = None

        self.__create_ui()

        self._primary_thumbnail_loaded_subscription = self._core.subscribe_primary_thumbnail_loaded(
            self._on_primary_thumbnail_loaded
        )

    @property
    def style(self):
        return {
            "Label::Title": {"color": 0xFF9C9C9C, "font_size": self.TITLE_FONT_SIZE},
            "Label::NoImage": {"font_size": self.NO_FONT_SIZE, "margin": 5},
            "Label::NoUSDPath": {"font_size": self.NO_FONT_SIZE, "color": 0xDB0000FF},
            "Rectangle::NoImage": {"background_color": 0x80464646},
            "Rectangle.Overlay": {"background_color": 0x00FFFFFF, "border_width": 1.0, "border_color": 0x20FFFFFF},
            "Rectangle.Overlay:hovered": {"background_color": 0x21FFFFFF},
            "Rectangle.Overlay_NoUSDPath": {"background_color": 0x400000FF},
            "Rectangle.Overlay_NoUSDPath:hovered": {"background_color": 0x600000FF},
            "Rectangle::Wide": {"background_color": 0x00FFFFFF},
            "Rectangle::Wide:selected": {
                "border_color": 0xFFC5911A,
                "border_width": 1.0,
                "background_color": 0x70C5911A,
            },
            "Rectangle::Wide_NoUSDPath:selected": {
                "border_color": 0xDB0000FF,
                "border_width": 1.0,
                "background_color": 0x400000FF,
            },
        }

    @property
    def default_attr(self):
        return {"_asset_detail_windows": None, "_core": None}

    @property
    def is_usd_path_valid(self):
        """Check is the USD path exist"""
        return is_path_readable(self.content_data.path)

    @handle_exception
    async def __deferred_primary_image(self, callback):
        wrapped_fn = async_wrap(callback)
        result = await wrapped_fn()
        self._core.primary_thumbnail_loaded(self.content_data.path, result)

    @handle_exception
    async def __deferred_update_ui(self):
        def do_update_ui():
            result = self.is_usd_path_valid
            if not result:
                self.__no_usd_path_frame.clear()
                with self.__no_usd_path_frame:
                    ui.Label("Path not found on disk", alignment=ui.Alignment.CENTER, word_wrap=True, name="NoUSDPath")
            self.__no_usd_path_frame.visible = not result
            style_type_name_override = "Rectangle.Overlay_NoUSDPath" if not result else "Rectangle.Overlay"
            self.__overlay_highlight_rectangle.style_type_name_override = style_type_name_override
            with self.__no_image_frame:
                alignment = ui.Alignment.CENTER_BOTTOM if self.__no_usd_path_frame.visible else ui.Alignment.CENTER
                ui.Label(self.__label_message_no_image, alignment=alignment, name="NoImage")

        wrapped_fn = async_wrap(do_update_ui)
        await wrapped_fn()

    def _on_primary_thumbnail_loaded(self, path, thumbnail_path):
        if path != self.content_data.path:
            return
        if thumbnail_path:
            self.__no_image_frame.clear()
            self.__no_image_frame.visible = False
            self.__image_frame.visible = True
            with self.__image_frame:
                self.__background_image = ui.Image(  # noqa PLW0238
                    thumbnail_path, fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT, visible=True, name="Background"
                )
        else:
            self.__label_message_no_image = "No image"
            self.__no_image_frame.visible = True
            self.__no_image_frame.clear()
            with self.__no_image_frame:
                alignment = ui.Alignment.CENTER_BOTTOM if self.__no_usd_path_frame.visible else ui.Alignment.CENTER
                ui.Label(self.__label_message_no_image, alignment=alignment, name="NoImage")

    def on_resized_grid(self, grid_size):
        """Called when the grid is resized"""
        old_max = 200
        old_min = 0
        new_max = 140
        new_min = 60
        old_range = old_max - old_min
        new_range = new_max - new_min
        new_value = (((grid_size - old_min) * new_range) / old_range) + new_min
        self.style.update(
            {
                "Label::NoImage": {"font_size": (grid_size / 100) * self.NO_FONT_SIZE},
                "Label::NoUSDPath": {"font_size": (grid_size / 100) * self.NO_FONT_SIZE, "color": 0xDB0000FF},
                "Label::Title": {"color": 0xFF9C9C9C, "font_size": (new_value / 100) * self.TITLE_FONT_SIZE},
            }
        )
        self.__create_labels()

    def __create_labels(self):
        """Create all 'no' labels (no image, no usd...)"""
        if self.__no_image_frame is not None:
            self.__no_image_frame.clear()
            self.__no_image_frame.style = self.style
            with self.__no_image_frame:
                alignment = ui.Alignment.CENTER_BOTTOM if self.__no_usd_path_frame.visible else ui.Alignment.CENTER
                ui.Label(self.__label_message_no_image, alignment=alignment, name="NoImage")
        if self.__no_usd_path_frame is not None:
            self.__no_usd_path_frame.clear()
            self.__no_usd_path_frame.style = self.style
            with self.__no_usd_path_frame:
                ui.Label("Path not found on disk", alignment=ui.Alignment.CENTER, word_wrap=True, name="NoUSDPath")
        if self.__title_frame is not None:
            self.__title_frame.clear()
            self.__title_frame.style = self.style
            with self.__title_frame:
                ui.Label(self.content_data.title, alignment=ui.Alignment.CENTER, name="Title", height=0, word_wrap=True)

    def __create_ui(self):
        """Create the UI"""
        with ui.ZStack(style=self.style):
            with ui.HStack():
                ui.Spacer(width=ui.Fraction(1))
                with ui.VStack(width=ui.Fraction(30)):
                    ui.Spacer(height=ui.Fraction(1))
                    with ui.VStack(height=ui.Fraction(30), spacing=8):
                        with ui.ZStack():
                            # image frame
                            self.__image_frame = ui.Frame(visible=False)

                            # no image/loading frame for label
                            self.__no_image_frame = ui.Frame()
                            self.__label_message_no_image = "Loading..."

                            # no usd path frame for label
                            self.__no_usd_path_frame = ui.Frame(visible=False)

                            # highlight rectangle when the mouse is over it
                            self.__overlay_highlight_rectangle = ui.Rectangle(
                                style_type_name_override="Rectangle.Overlay"
                            )
                            if self.content_data.is_checkpointed():
                                result, entries = omni.client.list_checkpoints(self.content_data.path)
                                if result == omni.client.Result.OK:
                                    with ui.VStack():
                                        ui.Spacer()
                                        with ui.HStack(height=0):
                                            ui.Spacer()
                                            self.__checkpoint_zstack = ui.ZStack(width=60, tooltip=entries[-1].comment)
                                            with self.__checkpoint_zstack:
                                                if self.CAN_CHOSE_CHECKPOINT:
                                                    ui.Rectangle(
                                                        name="CheckPoint",
                                                        style={
                                                            "background_color": 0x00FFFFFF,
                                                            "border_width": 3.0,
                                                            "border_color": 0x20FFFFFF,
                                                        },
                                                    )
                                                    self.__checkpoint_combobox = ui.ComboBox(
                                                        0,
                                                        *reversed([f"v{entry.relative_path[1:]}" for entry in entries]),
                                                        mouse_pressed_fn=self._on_checkpoint_combobox_mouse_clicked,
                                                        mouse_released_fn=self._on_checkpoint_combobox_mouse_released,
                                                    )
                                                    self.__checkpoint_combobox.model.add_item_changed_fn(
                                                        self._on_checkpoint_changed
                                                    )
                                                else:
                                                    ui.Rectangle(
                                                        name="CheckPoint",
                                                        style={
                                                            "background_color": 0x00FFFFFF,
                                                            "border_width": 1.0,
                                                            "border_color": 0x20FFFFFF,
                                                        },
                                                    )
                                                    ui.Label(
                                                        [f"v{entry.relative_path[1:]}" for entry in entries][-1],
                                                        alignment=ui.Alignment.CENTER,
                                                    )
                        self.__title_frame = ui.Frame(height=0)
                    ui.Spacer(height=ui.Fraction(1))
                ui.Spacer(width=ui.Fraction(1))
            with ui.HStack():
                ui.Spacer(width=ui.Fraction(1))
                self.__overlay_wide_rectangle = ui.Rectangle(
                    name="Wide",
                    mouse_pressed_fn=self._on_mouse_clicked,
                    mouse_released_fn=self._on_mouse_released,
                    mouse_moved_fn=self._on_mouse_moved,
                    width=ui.Fraction(80),
                )
                if self.DRAG:
                    self.__overlay_wide_rectangle.set_drag_fn(self._on_drag)
                ui.Spacer(width=ui.Fraction(1))
        self.__create_labels()
        # get the primary image async for speed
        image_fn = self.content_data.image_path_fn
        if image_fn is not None:
            asyncio.ensure_future(self.__deferred_primary_image(image_fn))
        else:
            self._on_primary_thumbnail_loaded(self.content_data.path, None)
        # update the ui in async functions for speed (ui that need to check usd path for example, etc etc)
        asyncio.ensure_future(self.__deferred_update_ui())

    def _on_drag(self):
        return self.content_data.path

    def destroy(self):
        self.__background_image = None  # noqa PLW0238
        self.__checkpoint_zstack = None  # noqa PLW0238
        self.__checkpoint_combobox = None  # noqa PLW0238
        self.__overlay_wide_rectangle = None  # noqa PLW0238
        self.__overlay_highlight_rectangle = None  # noqa PLW0238
        self.__no_image_frame = None  # noqa PLW0238
        self.__no_usd_path_frame = None  # noqa PLW0238
        self.__title_frame = None  # noqa PLW0238
        self.__image_frame = None  # noqa PLW0238
        self.__label_message_no_image = None  # noqa PLW0238
        for attr, value in self.default_attr.items():
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

    def set_selected(self, value):
        """Select the item"""
        self.__overlay_wide_rectangle.selected = value

    def is_selected(self):
        return self.__overlay_wide_rectangle.selected

    def _on_checkpoint_changed(self, model, item):
        entry = self.get_current_checkpoint()
        if entry is not None:
            self.content_data.checkpoint_version = entry.relative_path[1:]
            self.__checkpoint_zstack.set_tooltip(entry.comment)

    def get_current_checkpoint(self) -> Optional[omni.client.ListEntry]:
        if self.CAN_CHOSE_CHECKPOINT and self.content_data.is_checkpointed():
            result, entries = omni.client.list_checkpoints(self.content_data.path)
            if result == omni.client.Result.OK:
                return entries[::-1][self.__checkpoint_combobox.model.get_item_value_model().as_int]
        return None

    def _on_checkpoint_combobox_mouse_clicked(self, x, y, b, m):  # noqa PLC0103
        self._core.set_block_selection(True)

    def _on_checkpoint_combobox_mouse_released(self, x, y, b, m):  # noqa PLC0103
        self._core.set_block_selection(False)

    def _on_mouse_clicked(self, x, y, b, m):  # noqa PLC0103
        """Called when the item is clicked on"""
        if self._core.is_selection_blocked():
            return
        if b == 1:
            if self._asset_detail_windows is not None:
                self._asset_detail_windows.show(self.content_data)
        elif b == 0 and self._asset_detail_windows is not None:
            self._asset_detail_windows.hide()
        self._core.set_item_was_clicked(True)
        key_mod = m & ~ui.Widget.FLAG_WANT_CAPTURE_KEYBOARD
        if key_mod == int(carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT) and self.MULTI_SELECTION:
            self._core.set_selection(self.content_data, append_in_between=True)
        elif key_mod == int(carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL) and self.MULTI_SELECTION:
            self._core.set_selection(self.content_data, append=True)
        else:
            self._core.set_selection(self.content_data)

    def _on_mouse_released(self, x, y, b, m):  # noqa PLC0103
        """Called when the mouse is released"""
        pass

    def _on_mouse_moved(self, x, y, b, m):  # noqa PLC0103
        """Called when the mouse is moved"""
        pass


class ContentViewer:

    WIDTH_BACKGROUND_SLIDER = 100
    HEIGHT_BACKGROUND_SLIDER = 60
    GRID_COLUMN_WIDTH = 110
    GRID_ROW_HEIGHT = 120
    SHOW_ASSET_DETAIL_WINDOW = True
    CONTENT_ITEM_TYPE = ContentItem
    ENABLE_ADD_ITEM = False

    def __init__(self, core: ContentViewerCore, extension_path: str):
        """Window to list all content"""
        self._extension_path = extension_path
        self._current_extension_path = None
        self._calling_extension_path = None
        self._style = None
        self._default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self._core = core
        if self.SHOW_ASSET_DETAIL_WINDOW:
            self._asset_detail_windows = AssetDetailWindow()

        self._model_subscription = self._core.subscribe_content_changed(self._on_content_changed)
        self._selection_subscription = self._core.subscribe_selection_changed(self._on_selection_changed)
        self._error_get_data_subscription = self._core.subscribe_error_get_data(self._on_error_get_data)

        self.__frame = None
        self.__label_error = None
        self.__action_search_attr = None
        self.__label_search = None
        self.__cross_image = None
        self.__scroll_frame = None
        self.__top_frame = None
        self.__left_frame = None
        self.__right_frame = None
        self.__bottom_frame = None
        self.__content_grid = None
        self.__on_scroll_frame_mouse_clicked_task = None
        self.__content_items = None
        self.__content_data = None
        self.__slider = None
        self.__filter_content_title_value = None

    def get_content_items(self):
        return self.__content_items

    def get_left_frame(self):
        return self.__left_frame

    def get_top_frame(self):
        return self.__top_frame

    def get_right_frame(self):
        return self.__right_frame

    def get_bottom_frame(self):
        return self.__bottom_frame

    @property
    def current_extension_path(self):
        current_path = Path(__file__).parent
        for _ in range(4):
            current_path = current_path.parent
        return current_path

    @property
    def calling_extension_path(self):
        return self.current_extension_path

    @property
    def default_attr(self):
        return {"_core": None, "_asset_detail_windows": None}

    @property
    def style(self):
        return {
            "Label::Error": {"font_size": 20, "color": 0xFF2C2CDB},
            "Label::Open": {"font_size": 20},
            "Label::Refresh": {"font_size": 14},
            "Label::Search": {"color": 0x908A8777},
            "Image::Cross": {"color": 0xFF8A8777, "margin": 3},
            "Image::Search": {"color": 0xFF8A8777},
            "Image::Refresh": {"color": 0xFF8A8777, "margin": 3},
            "Rectangle::Background": {"background_color": 0xFF23211F},
            "Rectangle::BackgroundSearch": {"border_width": 1, "border_color": 0x20FFFFFF, "background_color": 0x0},
            "Rectangle::Open": {"background_color": 0xFF292929},
            "Rectangle::Open:hovered": {"background_color": 0xFF9E9E9E},
            "Rectangle::Search": {"background_color": 0xFF23211F},
            "Rectangle::Slider": {"background_color": 0x50676767},
        }

    def _get_icon_path(self, name: str, from_base_extension=True):
        """Get an icon path form his name"""
        if from_base_extension:
            path = self.current_extension_path.joinpath("icons", f"{name}.svg")
        else:
            path = self.calling_extension_path.joinpath("icons", f"{name}.svg")
        if path.exists():
            return path
        return None

    def _on_selection_changed(self, contents_data: List[ContentData]):
        """Called when the selection of an item content is changed"""
        if self.__content_items is None:
            return
        for content_item in self.__content_items:
            content_item.set_selected(content_item.content_data in contents_data)

    def _on_error_get_data(self, message):
        """Called when there was an error getting data"""
        if message is not None:
            self.__label_error.text = message
        self.__label_error.visible = True

    def _on_content_changed(self, content_data: List[ContentData]):
        """Called when the content is changed"""
        self.__label_error.visible = False
        self.__frame.clear()
        self.__content_items = []
        self.__content_data = content_data
        with self.__frame:
            self.__content_grid = ui.VGrid(
                column_width=self.GRID_COLUMN_WIDTH, row_height=self.GRID_ROW_HEIGHT, spacing=50
            )
            with self.__content_grid:
                if self.ENABLE_ADD_ITEM:
                    self.__content_items.insert(0, ContentItemAdd(ContentDataAdd(), self._core))
                for data in content_data:
                    if (
                        self.__filter_content_title_value is not None
                        and self.__filter_content_title_value.lower() not in data.title.lower()
                    ):
                        continue
                    self.__content_items.append(self.CONTENT_ITEM_TYPE(data, self._core, self._asset_detail_windows))
        self._resize_grid()

    def _create_ui(self):
        """Create the main UI"""
        with ui.Frame():
            with ui.VStack(style=self.style, spacing=8):
                with ui.ZStack(height=22):
                    self.__top_frame = ui.Frame(width=0)
                    with ui.VStack():
                        ui.Spacer()
                        with ui.HStack(height=22):
                            ui.Spacer()
                            with ui.ZStack(width=ui.Percent(25)):
                                with ui.HStack():
                                    with ui.ZStack(width=20):
                                        ui.Rectangle(name="Search")
                                        ui.Image(str(self._get_icon_path("search")), name="Search")
                                    with ui.ZStack():
                                        self.__action_search_attr = ui.StringField()
                                        self.__action_search_attr.model.add_value_changed_fn(
                                            lambda m: self._filter_content()
                                        )
                                        with ui.HStack():
                                            ui.Spacer(width=8)
                                            self.__label_search = ui.Label("Search", name="Search")
                                    with ui.ZStack(width=20):
                                        ui.Rectangle(name="Search")
                                        self.__cross_image = ui.Image(
                                            str(self._get_icon_path("cross")),
                                            name="Cross",
                                            mouse_pressed_fn=lambda x, y, b, m: self._on_search_cross_clicked(),
                                            visible=False,
                                        )
                                ui.Rectangle(name="BackgroundSearch")
                            ui.Spacer()
                        ui.Spacer()
                with ui.HStack(spacing=8):
                    self.__left_frame = ui.Frame(width=0)
                    with ui.VStack():
                        with ui.ZStack(content_clipping=True):
                            self.__scroll_frame = ui.ScrollingFrame(
                                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                mouse_pressed_fn=lambda x, y, b, m: self._on_scroll_frame_mouse_clicked(),
                            )
                            with self.__scroll_frame:
                                with ui.ZStack():
                                    ui.Rectangle(name="Background")
                                    self.__frame = ui.Frame()
                            # slider for change the size of the grid
                            with ui.Frame(separate_window=True):
                                with ui.HStack():
                                    ui.Spacer(width=ui.Fraction(40))
                                    with ui.VStack(width=ui.Pixel(self.WIDTH_BACKGROUND_SLIDER)):
                                        ui.Spacer(height=ui.Fraction(40))
                                        with ui.ZStack(height=ui.Pixel(self.HEIGHT_BACKGROUND_SLIDER)):
                                            ui.Rectangle(name="Slider")
                                            with ui.VStack():
                                                ui.Spacer(height=ui.Fraction(1))
                                                with ui.HStack(height=ui.Fraction(10), content_clipping=True):
                                                    ui.Spacer(width=7)
                                                    ui.Label("Refresh", name="Refresh")
                                                    ui.Image(
                                                        str(self._get_icon_path("refresh")),
                                                        name="Refresh",
                                                        mouse_pressed_fn=lambda x, y, b, m: self._on_refresh_clicked(),
                                                    )
                                                with ui.HStack(height=ui.Fraction(10), content_clipping=True):
                                                    ui.Spacer(width=ui.Fraction(1))
                                                    self.__slider = ui.IntSlider(
                                                        min=0,
                                                        max=200,
                                                        alignment=ui.Alignment.CENTER,
                                                        width=ui.Pixel(self.WIDTH_BACKGROUND_SLIDER - 10),
                                                    )
                                                    self.__slider.model.set_value(100)
                                                    self.__slider.model.add_value_changed_fn(
                                                        lambda m: self._resize_grid()
                                                    )
                                                    ui.Spacer(width=ui.Fraction(1))
                                                ui.Spacer(height=ui.Fraction(1))
                                        ui.Spacer(height=ui.Fraction(2))
                                    ui.Spacer(width=ui.Fraction(1))
                            with ui.Frame(separate_window=True):
                                self.__label_error = ui.Label(
                                    "Error", name="Error", alignment=ui.Alignment.CENTER, visible=False
                                )
                        self.__bottom_frame = ui.Frame(height=0)
                    self.__right_frame = ui.Frame(width=0)

    def _filter_content(self):
        """Filter content by name"""
        self.__filter_content_title_value = self.__action_search_attr.model.as_string
        self.__label_search.visible = not bool(self.__filter_content_title_value)
        self.__cross_image.visible = bool(self.__filter_content_title_value)
        self._on_content_changed(self.__content_data)

    def _on_search_cross_clicked(self):
        """Called when the cross from the search box is clicked"""
        self.__action_search_attr.model.set_value("")
        self._filter_content()

    def _on_refresh_clicked(self):
        """Called when the ui is refreshed"""
        self._core.refresh_content()

    def _on_scroll_frame_mouse_clicked(self):
        """Called when we click in the UI but not on a content"""
        if self.__on_scroll_frame_mouse_clicked_task:
            self.__on_scroll_frame_mouse_clicked_task.cancel()
        self.__on_scroll_frame_mouse_clicked_task = asyncio.ensure_future(
            self.__deferred_on_scroll_frame_mouse_clicked()
        )

    @handle_exception
    async def __deferred_on_scroll_frame_mouse_clicked(self):
        await omni.kit.app.get_app().next_update_async()
        if self._core.is_selection_blocked():
            return
        if not self._core.was_item_clicked():
            self._core.set_selection(None)
            if self._asset_detail_windows is not None:
                self._asset_detail_windows.hide()
        self._core.set_item_was_clicked(False)

    def _resize_grid(self):
        """Called when the grid is resized"""
        if not self.__content_data and not self.ENABLE_ADD_ITEM:
            return
        value = self.__slider.model.as_int
        smoother = 2
        final_value = 100 - ((100 - value) / smoother)
        self.__content_grid.column_width = self.GRID_COLUMN_WIDTH * (final_value / 100)
        self.__content_grid.row_height = self.GRID_ROW_HEIGHT * (final_value / 100)
        for content_item in self.__content_items:
            content_item.on_resized_grid(value)

    def destroy(self):
        for attr, value in self.default_attr.items():
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
        if self.__content_items:
            for content_item in self.__content_items:
                content_item.destroy()
        self.__frame = None
        self.__label_error = None
        self.__action_search_attr = None
        self.__label_search = None
        self.__cross_image = None
        self.__slider = None
        self.__scroll_frame = None
        self.__top_frame = None
        self.__left_frame = None
        self.__bottom_frame = None
        self.__on_scroll_frame_mouse_clicked_task = None
        self.__content_grid = None
        self.__content_items = None
        self.__content_data = None
        self.__filter_content_title_value = None
        instance = super()
        if instance:
            del instance
