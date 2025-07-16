"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["HomePageWidget"]

import platform
import webbrowser
from functools import partial
from typing import Any, Callable

import carb
import omni.kit.app
from lightspeed.common import constants
from omni import ui
from omni.flux.info_icon.widget import InfoIconWidget
from omni.flux.utils.common import Event, EventSubscription, reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.common.path_utils import open_file_using_os_default
from omni.flux.utils.common.version import get_app_version
from omni.flux.utils.widget.tree_widget import TreeWidget

from .recent_tree import RecentProjectDelegate, RecentProjectModel


class HomePageWidget:
    _TINY_SPACING = ui.Pixel(8)
    _SMALL_SPACING = ui.Pixel(12)
    _MEDIUM_SPACING = ui.Pixel(16)
    _LARGE_SPACING = ui.Pixel(48)
    _BUTTON_HEIGHT = ui.Pixel(48)
    _INFO_ICON_SIZE = 24

    _ACTION_PANEL_WIDTH = ui.Pixel(500)

    def __init__(self, context_name: str = ""):
        self._default_attr = {
            "_context_name": None,
            "_recent_model": None,
            "_recent_delegate": None,
            "_recent_tree": None,
            "_resume_button": None,
            "_project_count_label": None,
            "_credits_window": None,
            "_item_remove_from_recent_sub": None,
            "_item_project_opened_sub": None,
            "_item_show_in_explorer_sub": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name

        self._recent_model = RecentProjectModel()
        self._recent_delegate = RecentProjectDelegate()

        self._recent_tree = None
        self._resume_button = None
        self._project_count_label = None
        self._credits_window = None

        self.__on_new_project_clicked = Event()
        self.__on_open_project_clicked = Event()
        self.__on_resume_clicked = Event()
        self.__on_load_project_clicked = Event()
        self.__on_remove_from_recent_clicked = Event()

        self._item_remove_from_recent_sub = self._recent_delegate.subscribe_item_remove_from_recent(
            lambda: self.__on_remove_from_recent_clicked(
                [i.path for i in self._recent_tree.selection] if self._recent_tree else []
            )
        )
        self._item_project_opened_sub = self._recent_delegate.subscribe_item_open_project(
            # A lambda is required, or we get a crash because the event is not hashable
            lambda path: self.__on_load_project_clicked(path)  # noqa PLW0108
        )
        self._item_show_in_explorer_sub = self._recent_delegate.subscribe_item_show_in_explorer(self._show_in_explorer)

        self._build_ui()

    @property
    def _url_labels(self) -> list:
        """
        List of tuples containing the label and the function to call when the label is clicked
        """
        return [
            ("Credits", self._show_credits),
            ("License Agreement", partial(self._open_url, constants.LICENSE_AGREEMENT_URL)),
            ("Release Notes", partial(self._open_url, constants.RELEASE_NOTES_URL)),
            ("Documentation", partial(self._open_url, constants.DOCUMENTATION_URL)),
            ("Tutorials", partial(self._open_url, constants.TUTORIALS_URL)),
            ("Community", partial(self._open_url, constants.COMMUNITY_SUPPORT_URL)),
            ("GitHub", partial(self._open_url, constants.GITHUB_URL)),
            ("Report an Issue", partial(self._open_url, constants.REPORT_ISSUE_URL)),
            ("Show Logs", self._show_logs),
            ("Show Install Directory", self._show_install_dir),
        ]

    def set_resume_enabled(self, enabled: bool):
        """
        Enable or disable the resume button. Will also update the tooltip if the button is disabled

        Args:
            enabled: Whether the resume button should be enabled or disabled
        """
        if not self._resume_button:
            return
        self._resume_button.enabled = enabled
        self._resume_button.tooltip = "" if enabled else "A project must first be loaded for this option to be enabled"

    def set_recent_items(self, items: list[tuple[str, str, dict]]):
        """
        Set the list of recent projects in the recent projects tree
        """
        if not self._recent_model:
            return

        if self._project_count_label:
            self._project_count_label.text = str(len(items))

        self._recent_model.refresh(items)

    def subscribe_new_project_clicked(self, callback: Callable[[], Any]) -> EventSubscription:
        """
        Subscribe to the event triggered when the new project button is clicked
        """
        return EventSubscription(self.__on_new_project_clicked, callback)

    def subscribe_open_project_clicked(self, callback: Callable[[], Any]) -> EventSubscription:
        """
        Subscribe to the event triggered when the open project button is clicked
        """
        return EventSubscription(self.__on_open_project_clicked, callback)

    def subscribe_resume_clicked(self, callback: Callable[[], Any]) -> EventSubscription:
        """
        Subscribe to the event triggered when the resume button is clicked
        """
        return EventSubscription(self.__on_resume_clicked, callback)

    def subscribe_load_project_clicked(self, callback: Callable[[str], Any]) -> EventSubscription:
        """
        Subscribe to the event triggered when a project should be opened.

        The callback will receive the project path.
        """
        return EventSubscription(self.__on_load_project_clicked, callback)

    def subscribe_remove_from_recent_clicked(self, callback: Callable[[list[str]], Any]) -> EventSubscription:
        """
        Subscribe to the event triggered when projects should be removed from the recent projects list.

        The callback will receive a list of project paths to remove.
        """
        return EventSubscription(self.__on_remove_from_recent_clicked, callback)

    def _build_ui(self):
        with ui.HStack():
            # Left Panel
            with ui.ZStack(width=self._ACTION_PANEL_WIDTH):
                ui.Rectangle(name="TabBackground")

                with ui.HStack(spacing=self._LARGE_SPACING):
                    ui.Spacer(width=0)
                    with ui.VStack(name="WorkspaceBackground", spacing=self._LARGE_SPACING):
                        ui.Spacer(height=0)

                        with ui.VStack():
                            # App Logo
                            ui.Image("", name="NvidiaShort", height=ui.Pixel(60))

                            ui.Spacer(height=self._LARGE_SPACING)

                            # Primary Buttons
                            with ui.VStack(spacing=self._MEDIUM_SPACING):
                                with ui.VStack(spacing=ui.Pixel(4), height=0):
                                    self._build_button(
                                        "New",
                                        "Launch the project wizard to:\n"
                                        "- Create a new mod\n"
                                        "- Edit existing mods\n"
                                        "- Remaster existing mods",
                                        self.__on_new_project_clicked,
                                    )
                                    self._build_button(
                                        "Open",
                                        "Open an existing project",
                                        self.__on_open_project_clicked,
                                    )
                                    # Initialize the UI with the right state
                                    stage = omni.usd.get_context(self._context_name).get_stage()
                                    project_opened = stage and not bool(stage.GetRootLayer().anonymous)
                                    self._resume_button = self._build_button(
                                        "Resume",
                                        "Resume editing the currently opened project",
                                        self.__on_resume_clicked,
                                    )
                                    self.set_resume_enabled(project_opened)

                                ui.Rectangle(name="WizardSeparator", height=ui.Pixel(1))

                                self._build_button(
                                    "Quick Start Guide",
                                    "Open the Quick Start Guide documentation page in your browser",
                                    partial(self._open_url, constants.QUICK_START_GUIDE_URL),
                                )

                            ui.Spacer()

                            # URL Labels
                            with ui.VStack(height=0, spacing=self._TINY_SPACING):
                                for url_label in self._url_labels:
                                    text, callback = url_label
                                    ui.Label(text, mouse_pressed_fn=callback, name="FooterLabel")

                            ui.Spacer(height=self._LARGE_SPACING)

                            # App Version & Kit Version
                            app_version = get_app_version()
                            kit_version = omni.kit.app.get_app().get_kit_version()

                            with ui.HStack(height=0, spacing=self._SMALL_SPACING):
                                ui.Label(
                                    app_version,
                                    tooltip="Copy app version to clipboard",
                                    name="VersionLabel",
                                    width=0,
                                    mouse_pressed_fn=partial(self._copy_to_clipboard, app_version),
                                )
                                ui.Rectangle(name="WizardSeparator", width=ui.Pixel(2))
                                ui.Label(
                                    kit_version,
                                    tooltip="Copy Kit version to clipboard",
                                    name="VersionLabel",
                                    width=0,
                                    mouse_pressed_fn=partial(self._copy_to_clipboard, kit_version),
                                )

                        ui.Spacer(height=0)
                    ui.Spacer(width=0)

            # Right Panel
            with ui.ZStack():
                ui.Rectangle(name="WorkspaceBackground")

                with ui.HStack(spacing=self._LARGE_SPACING):
                    ui.Spacer(width=0)
                    with ui.VStack(spacing=self._LARGE_SPACING):
                        ui.Spacer(height=0)

                        with ui.VStack(spacing=self._MEDIUM_SPACING):
                            with ui.HStack(height=0, spacing=self._SMALL_SPACING):
                                ui.Label("Recent Projects", name="HomeLabel", width=0)
                                with ui.VStack():
                                    ui.Spacer()
                                    InfoIconWidget(
                                        "Double click any project to open it.\n"
                                        'Right click any projects or click on the "..." icon to get more options.',
                                        icon_size=self._INFO_ICON_SIZE,
                                    )
                                    ui.Spacer()
                            with ui.ZStack():
                                ui.Rectangle(name="TabBackground")
                                with ui.ScrollingFrame(name="PropertiesPaneSection"):
                                    self._recent_tree = TreeWidget(
                                        self._recent_model,
                                        self._recent_delegate,
                                        select_all_children=False,
                                        header_visible=True,
                                        columns_resizable=False,
                                        column_widths=[
                                            ui.Pixel(100),
                                            ui.Fraction(4),
                                            ui.Fraction(3),
                                            ui.Fraction(1),
                                            ui.Fraction(2),
                                            ui.Pixel(50),
                                        ],
                                    )
                            with ui.HStack(height=0, spacing=ui.Pixel(4)):
                                ui.Label("Projects Available:", name="HomeEmphasizedLabel", width=0)
                                self._project_count_label = ui.Label("0", name="HomeDiscreteLabel", width=0)

                        ui.Spacer(height=0)
                    ui.Spacer(width=0)

    def _build_button(self, text: str, tooltip: str, clicked_fn: Callable) -> ui.Button:
        """
        A utility function to build the large home screen buttons.

        Args:
            text: The button label
            tooltip: The button tooltip
            clicked_fn: The function to call when the button is clicked

        Returns:
            The button widget
        """
        with ui.HStack(height=self._BUTTON_HEIGHT, spacing=self._MEDIUM_SPACING):
            button = ui.Button(text, clicked_fn=clicked_fn, name="HomeButton")
            with ui.VStack(width=0):
                ui.Spacer()
                InfoIconWidget(tooltip, icon_size=self._INFO_ICON_SIZE)
                ui.Spacer()

        return button

    def _show_logs(self, x: float, y: float, b: int, m: int):
        """
        A callback to open the logs directory when the left mouse button is clicked.

        Args:
            x: The mouse x position
            y: The mouse y position
            b: The mouse button
            m: The mouse modifier
        """
        if b != 0:
            return

        open_file_using_os_default(carb.tokens.get_tokens_interface().resolve("${logs}"))

    def _show_install_dir(self, x: float, y: float, b: int, m: int):
        """
        A callback to open the installation directory when the left mouse button is clicked.

        Args:
            x: The mouse x position
            y: The mouse y position
            b: The mouse button
            m: The mouse modifier
        """
        if b != 0:
            return

        # <INSTALL_DIR>/apps
        app_directory = carb.tokens.get_tokens_interface().resolve("${app}")
        # lightspeed.trex.app
        app_name = carb.tokens.get_tokens_interface().resolve("${app_filename}")
        # .bat
        extension = ".bat" if platform.system().lower() == "windows" else ".sh"

        # <INSTALL_DIR>/lightspeed.trex.app.bat
        complete_directory = str(OmniUrl(OmniUrl(app_directory).parent_url) / app_name) + extension

        open_file_using_os_default(complete_directory)

    def _show_credits(self, x: float, y: float, b: int, m: int):
        """
        A callback to show the credits window when the left mouse button is clicked.

        Args:
            x: The mouse x position
            y: The mouse y position
            b: The mouse button
            m: The mouse modifier
        """
        if b != 0:
            return

        self._credits_window = ui.Window(
            "RTX Remix Credits",
            visible=True,
            width=400,
            height=500,
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_COLLAPSE
                | ui.WINDOW_FLAGS_NO_MOVE
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_NO_CLOSE
                | ui.WINDOW_FLAGS_MODAL
            ),
        )

        def hide_window():
            self._credits_window.visible = False

        with self._credits_window.frame:
            with ui.VStack(spacing=self._SMALL_SPACING):
                ui.Spacer(height=0)
                with ui.HStack(spacing=self._SMALL_SPACING):
                    ui.Spacer(width=0)
                    with ui.ZStack():
                        ui.Rectangle(name="WorkspaceBackground")
                        ui.StringField(multiline=True, read_only=True).model.set_value(constants.CREDITS)
                    ui.Spacer(width=0)
                with ui.HStack(height=ui.Pixel(24)):
                    ui.Spacer()
                    ui.Button("Close", clicked_fn=hide_window)
                    ui.Spacer()
                ui.Spacer(height=0)

    def _open_url(self, url: str, *args):
        """
        A callback to open a URL when the left mouse button is clicked.

        Args:
            url: The URL to open
            args: Additional arguments
                - x: The mouse x position
                - y: The mouse y position
                - b: The mouse button
                - m: The mouse modifier
        """

        if args and len(args) == 4 and args[2] != 0:
            return
        webbrowser.open(url, new=0, autoraise=True)

    def _show_in_explorer(self):
        """
        A callback to show the current project in explorer when the event is triggered in the delegate.
        """
        for item in self._recent_tree.selection:
            open_file_using_os_default(item.path)

    def _copy_to_clipboard(self, label: str, x: float, y: float, b: int, m: int):
        """
        A callback to copy text to the clipboard when the left mouse button is clicked.
        """
        if b != 0:
            return

        omni.kit.clipboard.copy(label)

    def destroy(self):
        reset_default_attrs(self)
