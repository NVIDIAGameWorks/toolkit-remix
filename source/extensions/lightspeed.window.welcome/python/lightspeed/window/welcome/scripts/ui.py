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
from pathlib import Path
from typing import List, Optional

import carb
import omni.appwindow
import omni.client
import omni.kit.menu.utils
import omni.ui as ui
from lightspeed.event.save_recent.scripts.recent_saved_file_utils import get_instance
from lightspeed.widget.content_viewer.scripts.core import ContentData, ContentDataAdd
from lightspeed.widget.new_game.scripts.core import GameCore
from lightspeed.widget.new_game.scripts.ui import GameViewer
from lightspeed.widget.new_workspace.scripts.core import GameWorkspaceCore
from lightspeed.widget.new_workspace.scripts.new_core import NewGameWorkspaceCore
from lightspeed.widget.new_workspace.scripts.ui import GameWorkspaceViewer
from lightspeed.workspace import get_instance as lightspeed_workspace_instance
from omni.kit.menu.utils import MenuItemDescription
from omni.usd import handle_exception
from PIL import Image

from .recent_delegate import RecentDelegate
from .recent_model import RecentModel
from .usd_file_picker import open_file_picker


class WelcomeWindow:

    WINDOW_NAME = "Lightspeed Welcome"
    WINDOW_LOADING_NAME = "Loading"

    def __init__(self, extension_path):
        """Window to list all entities"""
        self._extension_path = extension_path
        self._style = {
            "Button::new": {"background_color": 0xFF23211F, "border_color": 0xFF606060, "border_width": 1},
            "Button::newDisabled": {"background_color": 0xFF606060, "border_color": 0xFF606060, "border_width": 1},
            "Button::new:hovered": {"background_color": 0xFF664B0C, "border_color": 0xFFBF8C15, "border_width": 1},
            "Image::new:hovered": {"color": 0xFFBF8C15},
            "Image::close": {"color": 0xFF909090, "margin": 5},
            "Image::close:hovered": {"color": 0xFFFFFFFF},
            "Label::letsget": {"color": 0xFF949494, "font_size": 18.0},
            "Label::RecentBasename": {"font_size": 16, "color": 0xFFD9D9D9},
            "Label::RecentDetailTitle": {"color": 0x50FFFFFF},
            "Label::RecentFullPath": {"color": 0x50FFFFFF},
            "Label::recent_work": {"color": 0xFF757575, "font_size": 22.0},
            "Rectangle::close": {"background_color": 0x00000000},
            "Rectangle::close:hovered": {"background_color": 0xFF000090},
            "Rectangle::item": {"background_color": 0x00000000},
            "Rectangle::item:selected": {"background_color": 0xFF664B0C, "border_color": 0xFFBF8C15, "border_width": 1},
            "Rectangle::main_frame": {"background_color": 0xFF23211F},
            "TreeView": {
                "background_color": 0xFF23211F,
                "background_selected_color": 0x664F4D43,
                "secondary_color": 0xFF403B3B,
            },
            "TreeView.ScrollingFrame": {"background_color": 0xFF23211F},
            "TreeView.Header": {"background_color": 0xFF343432, "color": 0xFFCCCCCC, "font_size": 13},
            "TreeView.Item": {"color": 0xFF8A8777},
        }
        self.__default_attr = {
            "_window": None,
            "_recent_game_workspace_tree_view": None,
            "_subcription_app_window_size_changed": None,
            "_window_loading": None,
            "_menus": None,
            "_frame_new_game": None,
            "_frame_new_game_workspace": None,
            "_main_frame": None,
            "_recent_game_workspace_frame_detail": None,
            "_model_recent_game_worksapce": None,
            "_delegate_recent_game_worksapce": None,
            "_selected_recent_work_path": None,
            "_game_core": None,
            "_game_viewer": None,
            "_game_workspace_core": None,
            "_new_game_workspace_core": None,
            "_game_workspace_viewer": None,
            "_select_this_game_button": None,
            "_delete_this_game_button": None,
        }
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self._model_recent_game_worksapce = RecentModel()
        self._delegate_recent_game_worksapce = RecentDelegate()

        self._game_core = GameCore()
        self._game_viewer = GameViewer(self._game_core, self._extension_path)

        self._game_workspace_core = GameWorkspaceCore()
        self._new_game_workspace_core = NewGameWorkspaceCore()
        self._game_workspace_viewer = GameWorkspaceViewer(self._game_workspace_core, self._extension_path)

        self.__create_ui()
        self.__create_loading_ui()
        self.__create_menu()

        self.__subcription_current_game_capture_folder_changed = self._game_core.subscribe_current_game_capture_folder_changed(  # noqa E501
            self._on_current_game_capture_folder_changed
        )

        self.__subcription_game_selection_changed = self._game_core.subscribe_selection_changed(
            self._on_game_selection_changed
        )

        self.__subcription_workspace_changed = lightspeed_workspace_instance().subscribe_workspace_restored(
            self._on_workspace_restored
        )

    def _on_tree_selection_changed(self, items):
        if items:
            self._preview_saved_usd_file(items[0].path)
        else:
            self._recent_game_workspace_frame_detail.clear()

    def _preview_saved_usd_file(self, path):
        data = get_instance().get_path_detail(path)
        with self._recent_game_workspace_frame_detail:
            with ui.VStack(spacing=8):
                with ui.HStack(height=ui.Percent(40), spacing=8):
                    for _ in range(2):
                        with ui.ZStack():
                            ui.Rectangle()
                            ui.Label("No image", alignment=ui.Alignment.CENTER)
                with ui.VStack(height=0):
                    for title, value in data.items():
                        with ui.HStack():
                            ui.Label(title, name="RecentDetailTitle", width=ui.Percent(34))
                            ui.Label(value, word_wrap=len(value) > 24)
                        ui.Spacer(height=5)
                ui.Spacer()
                ui.Button(
                    "Load this stage", clicked_fn=self._on_load_this_game_workspace, height=20, width=140, name="new"
                )

    def _get_icon(self, name) -> Optional[str]:
        """Get icon path"""
        icon_path = Path(self._extension_path).joinpath("icons", f"{name}.svg")
        if icon_path.exists():
            return str(icon_path)
        return None

    def _get_image(self, name) -> Optional[str]:
        """Get icon path"""
        icon_path = Path(self._extension_path).joinpath("data", f"{name}.png")
        if icon_path.exists():
            return str(icon_path)
        return None

    def center_window(self):
        window_width = ui.Workspace.get_main_window_width()
        window_height = ui.Workspace.get_main_window_height()
        width, height = self._generate_window_size()
        self._window.width = width
        self._window.height = height
        self._window.position_x = window_width / 2 - self._window.width / 2
        self._window.position_y = window_height / 2 - self._window.height / 2

    def _on_workspace_restored(self):
        self.center_window()

    def __create_loading_ui(self):
        """Create the main UI"""
        flags = ui.WINDOW_FLAGS_NO_RESIZE
        flags |= ui.WINDOW_FLAGS_NO_SCROLLBAR
        flags |= ui.WINDOW_FLAGS_MODAL
        flags |= ui.WINDOW_FLAGS_NO_TITLE_BAR
        self._window_loading = ui.Window(
            self.WINDOW_LOADING_NAME,
            name=self.WINDOW_LOADING_NAME,
            width=300,
            height=100,
            noTabBar=True,
            visible=False,
            flags=flags,
        )
        with self._window_loading.frame:
            ui.Label("Loading...", alignment=ui.Alignment.CENTER)

    def __create_main_ui(self, width):
        self._main_frame = ui.Frame()
        with self._main_frame:
            with ui.ZStack():
                ui.Rectangle(name="main_frame")
                with ui.VStack():
                    ui.Spacer(height=ui.Percent(5))
                    image_path = self._get_image("lightspeed")
                    with Image.open(image_path) as im:
                        image_size = im.size
                        image_ratio = image_size[0] / image_size[1]
                    ui.Image(image_path, height=(width / 1.5) / image_ratio)
                    ui.Spacer()
                with ui.HStack():
                    ui.Spacer(width=ui.Percent(6))
                    with ui.VStack(spacing=0):
                        # with ui.VStack(height=ui.Percent(25)):
                        #     ui.Label("Let's get going...", name="letsget")
                        #     ui.Spacer(height=ui.Percent(40))
                        ui.Spacer(height=ui.Percent(25))
                        with ui.HStack(height=ui.Percent(65)):
                            with ui.VStack(width=ui.Percent(58), spacing=8):
                                ui.Label("RECENT WORK", name="recent_work", height=ui.Percent(15))
                                with ui.HStack(spacing=8):
                                    with ui.ScrollingFrame(style_type_name_override="TreeView"):
                                        self._recent_game_workspace_tree_view = ui.TreeView(
                                            self._model_recent_game_worksapce,
                                            delegate=self._delegate_recent_game_worksapce,
                                            root_visible=False,
                                            header_visible=False,
                                        )
                                        self._recent_game_workspace_tree_view.set_selection_changed_fn(
                                            self._on_tree_selection_changed
                                        )
                                    self._recent_game_workspace_frame_detail = ui.Frame()
                            ui.Spacer(width=ui.Percent(5))
                            ui.Rectangle(width=3)
                            ui.Spacer(width=ui.Percent(5))
                            with ui.VStack():
                                ui.Label("New...", name="recent_work", height=ui.Percent(15))
                                ui.Button("Create...", height=20, name="new", clicked_fn=self._on_create_new_game)
                                ui.Spacer(height=ui.Percent(3))
                                ui.Label("Open...", name="recent_work", height=ui.Percent(15))
                                ui.Button(
                                    "Open from storage...",
                                    height=20,
                                    name="new",
                                    clicked_fn=self._on_open_game_workspace,
                                )
                                ui.Spacer()
                        ui.Spacer(height=ui.Percent(3))
                    ui.Spacer(width=ui.Percent(6))
                with ui.VStack(height=20):
                    with ui.HStack():
                        ui.Spacer()
                        image_path = self._get_icon("cross")
                        with ui.ZStack(height=20, width=20, mouse_released_fn=self.__cross_close):
                            ui.Rectangle(name="close")
                            ui.Image(image_path, name="close")

    def show_frame_first(self, value):
        self._main_frame.visible = value

    def show_frame_new_game(self, value):
        self._frame_new_game.visible = value

    def show_frame_new_game_workspace(self, value):
        self._frame_new_game_workspace.visible = value

    def __create_ui_new_game(self):
        self._frame_new_game = ui.Frame()
        border_percent = 5
        with self._frame_new_game:
            with ui.ZStack():
                ui.Rectangle(name="main_frame")
                with ui.VStack():
                    ui.Spacer(height=ui.Percent(border_percent))
                    with ui.HStack():
                        ui.Spacer(width=ui.Percent(border_percent))
                        with ui.VStack(spacing=16):
                            ui.Label("Game(s)", height=0)
                            self._game_viewer.create_ui()
                            with ui.HStack(height=20, spacing=8):
                                icon = self._get_icon("arrow-back")
                                ui.Image(
                                    str(icon), name="new", width=20, mouse_released_fn=self.___arrow_initialize_welcome
                                )
                                ui.Spacer()
                                self._delete_this_game_button = ui.Button(
                                    "Delete selected game(s)",
                                    name="new",
                                    width=ui.Percent(20),
                                    clicked_fn=self._on_delete_selected_game,
                                )
                                self._select_this_game_button = ui.Button(
                                    "Select this game",
                                    name="new",
                                    width=ui.Percent(20),
                                    clicked_fn=self._on_select_this_game,
                                )
                                ui.Button("Cancel", name="new", width=ui.Percent(20), clicked_fn=self.close)
                        ui.Spacer(width=ui.Percent(border_percent))
                    ui.Spacer(height=ui.Percent(border_percent))

    def __create_ui_new_game_workspace(self):
        self._frame_new_game_workspace = ui.Frame()
        border_percent = 5
        with self._frame_new_game_workspace:
            with ui.ZStack():
                ui.Rectangle(name="main_frame")
                with ui.VStack():
                    ui.Spacer(height=ui.Percent(border_percent))
                    with ui.HStack():
                        ui.Spacer(width=ui.Percent(border_percent))
                        with ui.VStack(spacing=16):
                            ui.Label("Game Workspace(s)", height=0)
                            self._game_workspace_viewer.create_ui()
                            with ui.HStack(height=20):
                                icon = self._get_icon("arrow-back")
                                ui.Image(
                                    str(icon), name="new", width=20, mouse_released_fn=self.___arrow_on_create_new_game
                                )
                                ui.Spacer()
                                ui.Button(
                                    "Create this game workspace",
                                    name="new",
                                    width=ui.Percent(24),
                                    clicked_fn=self._on_create_new_game_workspace,
                                )
                                ui.Button("Cancel", name="new", width=ui.Percent(20), clicked_fn=self.close)
                        ui.Spacer(width=ui.Percent(border_percent))
                    ui.Spacer(height=ui.Percent(border_percent))

    def _generate_window_size(self):
        window_width = ui.Workspace.get_main_window_width()
        window_height = ui.Workspace.get_main_window_height()
        percent = 55
        if window_width < window_height:
            height = window_height / 100 * percent
            width = height * 1.3
        else:
            width = window_width / 100 * percent
            height = width / 1.3
        return width, height

    def __create_ui(self):
        """Create the main UI"""
        width, height = self._generate_window_size()

        flags = ui.WINDOW_FLAGS_NO_RESIZE
        flags |= ui.WINDOW_FLAGS_NO_SCROLLBAR
        # flags |= ui.WINDOW_FLAGS_MODAL  # can't be modal, bug with file picker over it
        flags |= ui.WINDOW_FLAGS_NO_DOCKING
        flags |= ui.WINDOW_FLAGS_NO_TITLE_BAR
        self._window = ui.Window(
            self.WINDOW_NAME, name=self.WINDOW_NAME, width=width, height=height, flags=flags, style=self._style
        )
        self._window.set_visibility_changed_fn(self._on_visibility_changed)
        self.center_window()

        with self._window.frame:
            with ui.ZStack(style=self._style):
                self.__create_ui_new_game_workspace()
                self.__create_ui_new_game()
                self.__create_main_ui(width)

        appwindow_stream = omni.appwindow.get_default_app_window().get_window_resize_event_stream()
        self._subcription_app_window_size_changed = appwindow_stream.create_subscription_to_pop(
            self._on_app_window_size_changed, name="On app window resized", order=0
        )
        self._on_initialize_welcome()

    def _on_app_window_size_changed(self, event: carb.events.IEvent):
        self.center_window()

    def ___arrow_initialize_welcome(self, x, y, b, m):
        if b != 0:
            return
        self._on_initialize_welcome()

    def _on_initialize_welcome(self):
        self.show_frame_first(True)
        self.show_frame_new_game_workspace(False)
        self.show_frame_new_game(False)

    def ___arrow_on_create_new_game(self, x, y, b, m):
        if b != 0:
            return
        self._on_create_new_game()

    def _on_create_new_game(self):
        self.show_frame_first(False)
        self.show_frame_new_game_workspace(False)
        self.show_frame_new_game(True)
        self._game_core.refresh_content()
        self._game_core.set_selection(None)

    def _on_open_game_workspace(self):
        open_file_picker(functools.partial(self._on_load_this_game_workspace), lambda *args: None)

    def _end_new_game_workspace_creation(self):
        asyncio.ensure_future(self.__deferred_load_window_loading(False))
        carb.log_info("Game workspace created")

    def _on_load_this_game_workspace(self, force_path=None):
        if force_path:
            self._selected_recent_work_path = force_path
        else:
            selection = self._recent_game_workspace_tree_view.selection
            if not selection:
                carb.log_error("Please select a recent work from the list")
                return
            self._selected_recent_work_path = selection[0].path
        self.close()
        # self._window_loading.visible = True  # disable for now

        asyncio.ensure_future(self.__deferred_on_load_this_game_workspace())

    @handle_exception
    async def __deferred_on_load_this_game_workspace(self):
        # wait 1 frame after we show the waiting UI
        await omni.kit.app.get_app().next_update_async()
        self._new_game_workspace_core.load_game_workspace(
            self._selected_recent_work_path, callback=self._end_game_workspace_load
        )

    def _end_game_workspace_load(self):
        asyncio.ensure_future(self.__deferred_load_window_loading(False))
        self._selected_recent_work_path = None

    @handle_exception
    async def __deferred_load_window_loading(self, value):
        self._window_loading.visible = value

    def _on_delete_selected_game(self):
        self._game_core.delete_selected_game()
        self._game_core.set_selection(None)
        self._game_core.refresh_content()

    def _on_game_selection_changed(self, contents_data: List["ContentData"]):
        if contents_data and isinstance(contents_data[0], ContentDataAdd):
            self._delete_this_game_button.enabled = False
            self._delete_this_game_button.name = "newDisabled"
        else:
            self._delete_this_game_button.enabled = True
            self._delete_this_game_button.name = "new"

    def _on_current_game_capture_folder_changed(self, current_game_capture_folder: "ContentData"):
        if not current_game_capture_folder or (
            isinstance(current_game_capture_folder, ContentData) and not current_game_capture_folder.is_path_valid
        ):
            self._select_this_game_button.enabled = False
            self._select_this_game_button.name = "newDisabled"
            return
        if current_game_capture_folder and isinstance(current_game_capture_folder, ContentDataAdd):
            all_content = self._game_core.get_current_content()
            if current_game_capture_folder.title is None or current_game_capture_folder.path is None:
                self._select_this_game_button.enabled = False
                self._select_this_game_button.name = "newDisabled"
                return
            for item in all_content:
                if item.title == current_game_capture_folder.title:
                    self._select_this_game_button.enabled = False
                    self._select_this_game_button.name = "newDisabled"
                    carb.log_error("This game name already exist")
                    return
        self._select_this_game_button.name = "new"
        self._select_this_game_button.enabled = True

    def _on_select_this_game(self):
        current_game_capture_folder = self._game_core.get_current_game_capture_folder()
        if not current_game_capture_folder:
            carb.log_error("Please select a valid game capture folder or add a new one")
            return
        if isinstance(current_game_capture_folder, ContentData) and not current_game_capture_folder.is_path_valid:
            carb.log_error("Can't add a invalid game")
            return
        all_content = self._game_core.get_current_content()
        for item in all_content:
            if item.title == current_game_capture_folder.title and isinstance(
                current_game_capture_folder, ContentDataAdd
            ):
                carb.log_error("This game name already exist")
                return
        self.show_frame_first(False)
        self.show_frame_new_game(False)
        self.show_frame_new_game_workspace(True)
        self._game_workspace_core.set_current_game_capture_folder(current_game_capture_folder)
        self._game_workspace_core.refresh_content()
        self._game_core.save_current_game_capture_folder_in_json()
        current_selection_workspace = self._game_workspace_core.get_selection()
        if current_selection_workspace:
            self._game_workspace_core.set_selection(current_selection_workspace[0])

    def _on_create_new_game_workspace(self):
        current_capture = self._game_workspace_core.get_current_capture()
        if not current_capture:
            carb.log_warn('Please select a "capture"')
            return
        if not self._game_workspace_core.check_replacement_layer_path():
            return
        self.close()
        # self._window_loading.visible = True  # disable for now

        asyncio.ensure_future(self.__deferred_on_create_new_game_workspace())

    @handle_exception
    async def __deferred_on_create_new_game_workspace(self):
        # wait 1 frame after we show the waiting UI
        await omni.kit.app.get_app().next_update_async()
        current_capture = self._game_workspace_core.get_current_capture()
        use_existing_layer = self._game_workspace_core.get_current_use_existing_layer()
        replacement_layer_path = self._game_workspace_core.get_current_replacement_layer_usd_path()
        game = self._game_workspace_core.get_current_game_capture_folder()

        self._new_game_workspace_core.create_game_workspace(
            current_capture,
            use_existing_layer,
            replacement_layer_path,
            game,
            callback=self._end_new_game_workspace_creation,
        )

    def __cross_close(self, x, y, b, m):
        if b != 0:
            return
        self.close()

    def close(self):
        self._window.visible = False

    def show(self):
        self._window.visible = True

    def __create_menu(self):
        """Create the menu in Create"""
        self._menus = [
            MenuItemDescription(
                name="New Game Workspace",
                onclick_fn=self.__new_game_workspace_menu,
                glyph="none.svg",
                appear_after="New",
            )
        ]
        omni.kit.menu.utils.add_menu_items(self._menus, "File")

    def __new_game_workspace_menu(self):
        asyncio.ensure_future(self.__deferred_new_game_workspace_menu())

    @handle_exception
    async def __deferred_new_game_workspace_menu(self):
        # wait 1 frame
        await omni.kit.app.get_app().next_update_async()
        self._window.visible = True
        self._on_initialize_welcome()

    def _on_visibility_changed(self, visible):
        """Change the menu"""
        self.center_window()
        self._on_initialize_welcome()
        self._on_tree_selection_changed(self._recent_game_workspace_tree_view.selection)
        self._model_recent_game_worksapce.refresh_list()
        omni.kit.menu.utils.rebuild_menus()

    def _toggle_window(self):
        if self._window:
            self._window.visible = not self._window.visible

    def destroy(self):
        self.__subcription_workspace_changed = None
        self.__subcription_game_selection_changed = None
        self.__subcription_current_game_capture_folder_changed = None
        omni.kit.menu.utils.remove_menu_items(self._menus, "File")
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
