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

import asyncio
import os
import re
import typing
from functools import partial
from typing import Callable

import omni.kit.clipboard
import omni.ui as ui
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.app.style.trex_style import DEFAULT_FIELD_EDITABLE_STYLE, DEFAULT_FIELD_READ_ONLY_STYLE
from lightspeed.trex.asset_replacements.core.shared.setup import Setup as _AssetReplacementsCoreSetup
from lightspeed.trex.utils.widget.dialogs import confirm_remove_prim_overrides as _confirm_remove_prim_overrides
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import deferred_destroy_tasks as _deferred_destroy_tasks
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.color import hex_to_color as _hex_to_color
from omni.flux.utils.widget.gradient import create_gradient as _create_gradient
from pxr import Sdf

from .model import HEADER_DICT
from .model import AnyItemType as _AnyItemType
from .model import ItemAddNewLiveLight as _ItemAddNewLiveLight
from .model import ItemAddNewReferenceFile as _ItemAddNewReferenceFileMesh
from .model import ItemAsset as _ItemAsset
from .model import ItemInstance as _ItemInstance
from .model import ItemInstancesGroup as _ItemInstancesGroup
from .model import ItemLiveLightGroup as _ItemLiveLightGroup
from .model import ItemPrim as _ItemPrim
from .model import ItemReferenceFile as _ItemReferenceFile

if typing.TYPE_CHECKING:
    from pxr import Usd


class Delegate(ui.AbstractItemDelegate):
    """Delegate of the action lister"""

    DEFAULT_IMAGE_ICON_SIZE = 24

    def __init__(self):
        super().__init__()

        self._default_attr = {
            "_path_scroll_frames": None,
            "_zstack_scroll": None,
            "_gradient_image_provider": None,
            "_gradient_image_with_provider": None,
            "_gradient_array": None,
            "_gradient_array_hovered": None,
            "_gradient_array_selected": None,
            "_primary_selection": None,
            "_secondary_selection": None,
            "_hovered_items": None,
            "_background_rectangle": None,
            "_item_fields": None,
            "_nickname_toggle_show": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self.__refresh_gradient_color_task = None
        self._primary_selection = []
        self._secondary_selection = []
        self._hovered_items = {}
        self._background_rectangle = {}

        self._path_scroll_frames = {}
        self._zstack_scroll = {}
        self._gradient_image_provider = {}
        self._gradient_image_with_provider = {}
        self._item_fields = {}

        self.__item_is_pressed = False  # noqa PLW0238

        # gradient
        style = ui.Style.get_instance()
        self.__gradient_color1 = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient"]["background_color"]
        )
        self.__gradient_color2 = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient"]["background_gradient_color"]
        )
        self.__gradient_color1_hovered = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient_hovered"]["background_color"]
        )
        self.__gradient_color2_hovered = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient_hovered"]["background_gradient_color"]
        )
        self.__gradient_color1_selected = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient_selected"]["background_color"]
        )
        self.__gradient_color2_selected = _hex_to_color(
            style.default["ImageWithProvider::SelectionGradient_selected"]["background_gradient_color"]
        )
        self.__gradient_width = 48
        self.__gradient_height = 1
        self._gradient_array = _create_gradient(
            self.__gradient_width,
            self.__gradient_height,
            self.__gradient_color1,
            self.__gradient_color2,
            (True, True, True, True),
        )
        self._gradient_array_list = self._gradient_array.ravel().tolist()
        self._gradient_array_hovered = _create_gradient(
            self.__gradient_width,
            self.__gradient_height,
            self.__gradient_color1_hovered,
            self.__gradient_color2_hovered,
            (True, True, True, True),
        )
        self._gradient_array_hovered_list = self._gradient_array_hovered.ravel().tolist()
        self._gradient_array_selected = _create_gradient(
            self.__gradient_width,
            self.__gradient_height,
            self.__gradient_color1_selected,
            self.__gradient_color2_selected,
            (True, True, True, True),
        )
        self._gradient_array_selected_list = self._gradient_array_selected.ravel().tolist()

        # Populated during a right click event within `_show_copy_menu` to avoid garbage collection
        self._context_menu: ui.Menu | None = None

        self.__on_delete_reference = _Event()
        self.__on_delete_prim = _Event()
        self.__on_duplicate_reference = _Event()
        self.__on_duplicate_prim = _Event()
        self.__on_frame_prim = _Event()

        self._asset_core = _AssetReplacementsCoreSetup(omni.usd.get_context().get_name())

        self._nickname_toggle_show = True

    def _duplicate_reference(self, item: _ItemReferenceFile):
        """Call the event object that has the list of functions"""
        self.__on_duplicate_reference(item)

    def subscribe_duplicate_reference(self, function: Callable[[_ItemReferenceFile], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_duplicate_reference, function)

    def _duplicate_prim(self, item: _ItemPrim):
        """Call the event object that has the list of functions"""
        self.__on_duplicate_prim(item)

    def subscribe_duplicate_prim(self, function: Callable[[_ItemPrim], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_duplicate_prim, function)

    def _delete_reference(self, item: _ItemReferenceFile):
        """Call the event object that has the list of functions"""
        self.__on_delete_reference(item)

    def subscribe_delete_reference(self, function: Callable[[_ItemReferenceFile], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_delete_reference, function)

    def _delete_prim(self, item: _ItemPrim):
        """Call the event object that has the list of functions"""
        self.__on_delete_prim(item)

    def subscribe_delete_prim(self, function: Callable[[_ItemPrim], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_delete_prim, function)

    def _frame_prim(self, prim: "Usd.Prim"):
        """Call the event object that has the list of functions"""
        self.__on_frame_prim(prim)

    def subscribe_frame_prim(self, function: Callable[["Usd.Prim"], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_frame_prim, function)

    def reset(self):
        self._primary_selection = []
        self._secondary_selection = []
        self._hovered_items = {}

        self._path_scroll_frames = {}
        self._zstack_scroll = {}
        self._gradient_image_provider = {}
        self._gradient_image_with_provider = {}
        self._background_rectangle = {}
        self._item_fields = {}

        self._context_menu = None

    def get_path_scroll_frames(self):
        return self._path_scroll_frames

    def __generate_tool_tip(self, item: _AnyItemType) -> str:
        if isinstance(item, _ItemAsset):
            return item.path
        if isinstance(item, _ItemReferenceFile):
            return f"Reference: {item.path}"
        if isinstance(
            item, (_ItemAddNewReferenceFileMesh, _ItemAddNewLiveLight, _ItemLiveLightGroup, _ItemInstancesGroup)
        ):
            return item.display
        if isinstance(item, _ItemInstance):
            return f"Instance: {item.path}"
        if isinstance(item, _ItemPrim):
            return f"Prim: {item.path}"
        return f"{item.__class__.__name__}: "

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        if column_id == 0:
            with ui.ZStack(mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, item)):
                if id(item) not in self._background_rectangle:
                    self._background_rectangle[id(item)] = []
                self._background_rectangle[id(item)].append(
                    ui.Rectangle(
                        height=self.DEFAULT_IMAGE_ICON_SIZE,
                        style_type_name_override=self.__get_item_background_style(item),
                    )
                )
                with ui.VStack():
                    ui.Spacer()
                    with ui.HStack(width=16 * (level + 2), height=self.DEFAULT_IMAGE_ICON_SIZE):
                        ui.Spacer(width=ui.Pixel(16 * (level + 1)))
                        if model.can_item_have_children(item):
                            # Draw the +/- icon
                            style_type_name_override = "TreeView.Item.Minus" if expanded else "TreeView.Item.Plus"
                            with ui.VStack(width=ui.Pixel(16)):
                                ui.Spacer(width=0)
                                ui.Image(
                                    "",
                                    width=10,
                                    height=10,
                                    style_type_name_override=style_type_name_override,
                                    identifier="Expand",
                                )
                                ui.Spacer(width=0)
                        else:
                            ui.Spacer(width=ui.Pixel(16))
                    ui.Spacer()

    # noinspection PyUnusedLocal
    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per item"""
        if item is None:
            return
        if column_id == 0:
            with ui.HStack(mouse_hovered_fn=lambda hovered: self._on_item_hovered(hovered, item)):
                with ui.ZStack():
                    if id(item) not in self._background_rectangle:
                        self._background_rectangle[id(item)] = []
                    self._background_rectangle[id(item)].append(
                        ui.Rectangle(style_type_name_override=self.__get_item_background_style(item))
                    )
                    with ui.HStack():
                        if isinstance(
                            item,
                            (
                                _ItemAsset,
                                _ItemReferenceFile,
                                _ItemAddNewReferenceFileMesh,
                                _ItemAddNewLiveLight,
                                _ItemLiveLightGroup,
                                _ItemInstancesGroup,
                                _ItemPrim,
                            ),
                        ):
                            with ui.HStack():
                                ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.VStack(width=ui.Pixel(16)):
                                    ui.Spacer(width=0)
                                    if isinstance(item, _ItemReferenceFile):
                                        ui.Image("", height=ui.Pixel(16), name="Collection")
                                    elif isinstance(item, _ItemAsset):
                                        ui.Image("", height=ui.Pixel(16), name="Mesh")
                                    elif isinstance(item, (_ItemAddNewReferenceFileMesh, _ItemAddNewLiveLight)):
                                        ui.Image("", height=ui.Pixel(16), name="Add")
                                    elif isinstance(item, _ItemInstancesGroup):
                                        ui.Image(
                                            "",
                                            height=ui.Pixel(16),
                                            name="FolderClosed",
                                            identifier="branch_instance_group",
                                        )
                                    elif isinstance(item, _ItemLiveLightGroup):
                                        ui.Image("", height=ui.Pixel(16), name="Light")
                                    elif isinstance(item, _ItemPrim):
                                        icon = ""
                                        if item.is_geomsubset():
                                            icon = "GeomSubset"
                                        elif item.is_mesh():
                                            icon = "Mesh"
                                        elif item.is_usd_light():
                                            icon = f"{item.prim.GetTypeName()}Static"
                                        elif item.is_xformable():
                                            icon = "Xform"
                                        elif item.is_scope():
                                            icon = "Scope"
                                        ui.Image("", height=ui.Pixel(16), name=icon)
                                    ui.Spacer(width=0)
                        else:
                            ui.Spacer(width=ui.Pixel(24))
                        ui.Spacer(height=0, width=ui.Pixel(8))
                        with ui.HStack():
                            tooltip = self.__generate_tool_tip(item)
                            with ui.HStack(
                                mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(b, item),
                                mouse_released_fn=lambda x, y, b, m: self._on_item_mouse_released(b, item),
                                mouse_double_clicked_fn=lambda x, y, b, m, item=item: self._nickname_action(
                                    item, x, y, b, m
                                ),
                                tooltip=tooltip,
                            ):
                                with ui.Frame(
                                    height=0,
                                    separate_window=True,  # to be able to select
                                ):
                                    self._zstack_scroll = ui.ZStack()
                                    with self._zstack_scroll:
                                        self._path_scroll_frames[id(item)] = ui.ScrollingFrame(
                                            name="TreePanelBackground",
                                            height=ui.Pixel(self.DEFAULT_IMAGE_ICON_SIZE),
                                            # width=ui.Percent(90),
                                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                            scroll_y_max=0,
                                        )
                                        with self._path_scroll_frames[id(item)]:
                                            with ui.HStack():
                                                if isinstance(item, _ItemAsset):
                                                    label_text = item.nickname if item.nickname else item.prim.GetName()
                                                    if item.nickname:
                                                        ui.Image(
                                                            "",
                                                            width=ui.Pixel(24),
                                                            height=ui.Pixel(24),
                                                            name="AsteriskBlue",
                                                            tooltip=("The asset has a nickname"),
                                                            identifier="has_nickname_state_widget_image",
                                                        )
                                                    else:
                                                        ui.Spacer(width=ui.Pixel(24))
                                                    field = ui.StringField(
                                                        read_only=True,
                                                        name="PropertiesPaneSectionTreeFieldItem",
                                                        tooltip=item.path,
                                                        identifier="item_asset",
                                                        style=DEFAULT_FIELD_READ_ONLY_STYLE,
                                                    )
                                                    field.model.set_value(label_text)
                                                    self._item_fields[id(item)] = {
                                                        "field": field,
                                                        "end_edit_fn": False,
                                                        "item": item,
                                                        "display_name": item.prim.GetName(),
                                                    }
                                                elif isinstance(item, (_ItemReferenceFile, _ItemPrim)):
                                                    label_text = (
                                                        item.nickname if item.nickname else os.path.basename(item.path)
                                                    )
                                                    if item.nickname:
                                                        ui.Image(
                                                            "",
                                                            width=ui.Pixel(24),
                                                            height=ui.Pixel(24),
                                                            name="AsteriskBlue",
                                                            tooltip=("The prim has a nickname"),
                                                            identifier="has_nickname_state_widget_image",
                                                        )
                                                    else:
                                                        ui.Spacer(width=ui.Pixel(24))
                                                    field = ui.StringField(
                                                        read_only=True,
                                                        name="PropertiesPaneSelectionTreeFieldItem",
                                                        tooltip=item.path,
                                                        identifier="item_prim",
                                                        style=DEFAULT_FIELD_READ_ONLY_STYLE,
                                                    )
                                                    field.model.set_value(label_text)
                                                    self._item_fields[id(item)] = {
                                                        "field": field,
                                                        "end_edit_fn": False,
                                                        "item": item,
                                                        "display_name": os.path.basename(item.path),
                                                    }
                                                elif isinstance(
                                                    item, (_ItemAddNewReferenceFileMesh, _ItemAddNewLiveLight)
                                                ):
                                                    ui.Label(
                                                        item.display,
                                                        name="PropertiesPaneSelectionTreeItem60",
                                                        identifier="item_add_button",
                                                    )
                                                elif isinstance(item, (_ItemInstancesGroup, _ItemLiveLightGroup)):
                                                    ui.Label(
                                                        item.display,
                                                        name="PropertiesPaneSectionTreeItem",
                                                        identifier="item_group",
                                                    )
                                                elif isinstance(item, _ItemInstance):
                                                    ui.Label(
                                                        os.path.basename(item.path),
                                                        name="PropertiesPaneSectionTreeItem",
                                                        tooltip=item.path,
                                                        identifier="item_instance",
                                                    )
                                                ui.Spacer(
                                                    height=0, width=ui.Pixel(self.__gradient_width / 2)
                                                )  # because of gradiant
                                        with ui.HStack():
                                            ui.Spacer()
                                            with ui.Frame(
                                                separate_window=True,
                                                width=ui.Pixel(self.__gradient_width),
                                            ):
                                                # add gradient
                                                self._gradient_image_provider[id(item)] = ui.ByteImageProvider()
                                                self._gradient_image_with_provider[id(item)] = ui.ImageWithProvider(
                                                    self._gradient_image_provider[id(item)],
                                                    height=self.DEFAULT_IMAGE_ICON_SIZE,
                                                    fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                                                    name="HeaderNvidiaBackground",
                                                )
                                                self.__do_refresh_gradient_color(item)
                            if isinstance(item, _ItemAsset):
                                ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.HStack(width=0, spacing=ui.Pixel(4)):
                                    with ui.VStack(
                                        width=ui.Pixel(16),
                                        content_clipping=True,
                                    ):
                                        ui.Spacer(width=0)
                                        ui.Image(
                                            "",
                                            height=ui.Pixel(16),
                                            name="Restore",
                                            tooltip="Restore the original asset",
                                            mouse_released_fn=lambda x, y, b, m: self._on_reset_mouse_released(b, item),
                                            identifier="restore",
                                        )
                                        ui.Spacer(width=0)
                                    ui.Spacer(width=0)
                                    with ui.VStack(
                                        width=ui.Pixel(16),
                                        content_clipping=True,
                                    ):
                                        ui.Spacer(width=0)
                                        ui.Image(
                                            "",
                                            height=ui.Pixel(16),
                                            name="Nickname",
                                            tooltip="Toggle the nickname of the asset",
                                            mouse_released_fn=lambda x, y, b, m: self._on_name_toggle_mouse_released(b),
                                            identifier="nickname_toggle",
                                        )
                                        ui.Spacer(width=0)
                            elif isinstance(item, _ItemReferenceFile):
                                ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.VStack(
                                    width=ui.Pixel(16 + 16 + 8),
                                    content_clipping=True,
                                ):
                                    ui.Spacer(width=0)
                                    with ui.HStack(height=ui.Pixel(16)):
                                        ui.Image(
                                            "",
                                            height=ui.Pixel(16),
                                            name="TrashCan",
                                            tooltip="Delete the asset",
                                            mouse_released_fn=lambda x, y, b, m: self._on_delete_ref_mouse_released(
                                                b, item
                                            ),
                                        )
                                        ui.Spacer(height=0, width=ui.Pixel(8))
                                        ui.Image(
                                            "",
                                            height=ui.Pixel(16),
                                            name="Duplicate",
                                            tooltip="Duplicate the asset",
                                            mouse_released_fn=lambda x, y, b, m: self._on_duplicate_ref_mouse_released(
                                                b, item
                                            ),
                                        )
                                    ui.Spacer(width=0)
                            elif isinstance(item, _ItemInstance):
                                ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.VStack(
                                    width=ui.Pixel(16),
                                    content_clipping=True,
                                ):
                                    ui.Spacer(width=0)
                                    ui.Image(
                                        "",
                                        height=ui.Pixel(16),
                                        name="Frame",
                                        tooltip="Frame instance in the viewport",
                                        mouse_released_fn=lambda x, y, b, m: self._on_frame_mouse_released(b, item),
                                    )
                                    ui.Spacer(width=0)
                            elif isinstance(item, _ItemPrim) and item.is_usd_light() and item.from_live_light_group:
                                ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.VStack(
                                    width=ui.Pixel(16 + 16 + 8),
                                    content_clipping=True,
                                ):
                                    ui.Spacer(width=0)
                                    with ui.HStack(height=ui.Pixel(16)):
                                        ui.Image(
                                            "",
                                            height=ui.Pixel(16),
                                            name="TrashCan",
                                            tooltip="Delete the prim",
                                            mouse_released_fn=lambda x, y, b, m: self._on_delete_prim_released(b, item),
                                        )
                                        ui.Spacer(height=0, width=ui.Pixel(8))
                                        ui.Image(
                                            "",
                                            height=ui.Pixel(16),
                                            name="Duplicate",
                                            tooltip="Duplicate the asset",
                                            mouse_released_fn=lambda x, y, b, m: self._on_duplicate_prim_mouse_released(
                                                b, item
                                            ),
                                        )
                                    ui.Spacer(width=0)
                            elif isinstance(item, _ItemPrim) and item.from_live_light_group:
                                ui.Spacer(height=0, width=ui.Pixel(8))
                                with ui.VStack(
                                    width=ui.Pixel(16),
                                    content_clipping=True,
                                ):
                                    ui.Spacer(width=0)
                                    ui.Image(
                                        "",
                                        height=ui.Pixel(16),
                                        name="TrashCan",
                                        tooltip="Delete the prim",
                                        mouse_released_fn=lambda x, y, b, m: self._on_delete_prim_released(b, item),
                                    )
                                    ui.Spacer(width=0)
                        ui.Spacer(height=0, width=ui.Pixel(8))

    def _on_item_hovered(self, hovered, item):
        if isinstance(item, _ItemAsset):
            return  # don't highlight top item because it can't be selected
        self._hovered_items[id(item)] = hovered
        for rectangle in self._background_rectangle.get(id(item), []):
            rectangle.style_type_name_override = self.__get_item_background_style(item, hovered)
        self.refresh_gradient_color(item)

    def _on_reset_mouse_released(self, button, item):
        if button != 0:
            return
        _confirm_remove_prim_overrides([item.prim.GetPath()])

    def _on_name_toggle_mouse_released(self, button):
        if button != 0:
            return
        self._nickname_toggle_show = not self._nickname_toggle_show
        for item_id in self._item_fields:
            field = self._item_fields.get(item_id)["field"]
            if field is None:
                continue
            display_name = self._item_fields.get(item_id)["display_name"]
            item = self._item_fields.get(item_id)["item"]
            if not self._nickname_toggle_show:
                field.model.set_value(display_name)
            else:
                field.model.set_value(item.nickname if item.nickname else display_name)

    def _nickname_action(self, item, x, y, button, modifiers):
        """
        Enable editing mode on double-click
        """
        if button != 0:
            return

        # Only allow renaming for items that have editable fields
        if not isinstance(item, (_ItemAsset, _ItemReferenceFile, _ItemPrim)):
            return
        field = self._item_fields.get(id(item))["field"]
        if field is None:
            return

        # Enable editing
        field.read_only = False
        field.focus_keyboard()
        field.set_style(DEFAULT_FIELD_EDITABLE_STYLE)

        # Subscribe to end edit (Enter key or focus lost)
        def on_end_edit(item, model):
            new_value = model.get_value_as_string()
            field.read_only = True
            field.set_style(DEFAULT_FIELD_READ_ONLY_STYLE)
            self._on_edit_complete(new_value, item)

        if not self._item_fields[id(item)]["end_edit_fn"]:
            self._item_fields[id(item)]["end_edit_fn"] = True
            field.model.add_end_edit_fn(partial(on_end_edit, item))

    def _on_edit_complete(self, new_value: str, item: _AnyItemType):
        """
        Called when editing is complete. Override this to handle the new value.
        """
        display_name = self._item_fields.get(id(item))["display_name"]
        if display_name == new_value:
            return

        if not item.prim or not item.prim.IsValid():
            return
        attr = item.prim.GetAttribute(constants.LSS_NICKNAME)
        prev_value = attr.Get() if attr else None
        self._asset_core.add_attribute(
            [item.prim.GetPath()], constants.LSS_NICKNAME, new_value, prev_value, Sdf.ValueTypeNames.String
        )

    def _on_delete_ref_mouse_released(self, button, item):
        if button != 0:
            return
        self._delete_reference(item)

    def _on_delete_prim_released(self, button, item):
        if button != 0:
            return
        self._delete_prim(item)

    def _on_duplicate_ref_mouse_released(self, button, item):
        if button != 0:
            return
        self._duplicate_reference(item)

    def _on_duplicate_prim_mouse_released(self, button, item):
        if button != 0:
            return
        self._duplicate_prim(item)

    def _on_frame_mouse_released(self, button, item):
        if button != 0:
            return
        self._frame_prim(item.prim)

    def _on_item_mouse_pressed(self, button, item):
        if button == 0:
            self.__item_is_pressed = True  # noqa PLW0238
            self.refresh_gradient_color(item)
        elif button == 1:
            self._show_copy_menu(item)

    def _on_item_mouse_released(self, button, item):
        if button != 0:
            return
        self.__item_is_pressed = False  # noqa PLW0238
        self.refresh_gradient_color(item)

    def _show_copy_menu(self, item):
        """
        Display a menu if the item was right-clicked to show clipboard copy options.
        """
        # Avoid menu if the item is not an applicable type
        if not isinstance(item, (_ItemInstance, _ItemAsset, _ItemPrim, _ItemReferenceFile)):
            return

        # NOTE: This menu is stored on the object to avoid garbage collection and being prematurely destroyed
        if self._context_menu is not None:
            self._context_menu.destroy()
        self._context_menu = ui.Menu("Context Menu")

        hash_match = re.match(constants.COMPILED_REGEX_HASH, str(item.prim.GetPath()))
        with self._context_menu:
            ui.MenuItem(
                "Copy Prim Name",
                identifier="copy_prim_name",
                triggered_fn=lambda: omni.kit.clipboard.copy(item.prim.GetName()),
            )
            ui.MenuItem(
                "Copy Prim Path",
                identifier="copy_prim_path",
                triggered_fn=lambda: omni.kit.clipboard.copy(str(item.prim.GetPath())),
            )
            ui.MenuItem(
                "Copy Reference Path",
                identifier="copy_reference_path",
                enabled=isinstance(item, _ItemReferenceFile),
                triggered_fn=lambda: omni.kit.clipboard.copy(item.absolute_path),
            )
            ui.MenuItem(
                "Copy Hash",
                enabled=hash_match is not None,
                identifier="copy_hash",
                triggered_fn=lambda: omni.kit.clipboard.copy(hash_match.group(3)),
            )

        self._context_menu.show()

    def refresh_gradient_color(self, item):
        self.__do_refresh_gradient_color(item)

    def __do_refresh_gradient_color(self, item):
        if id(item) not in self._gradient_image_provider or isinstance(
            item, (_ItemInstance, _ItemInstancesGroup, _ItemReferenceFile)
        ):
            return
        is_hovered = self._hovered_items.get(id(item), False)
        is_selected = item in self._primary_selection
        if is_selected:
            self._gradient_image_provider[id(item)].set_bytes_data(
                self._gradient_array_selected_list, [self.__gradient_width, self.__gradient_height]
            )
        elif is_hovered and not is_selected:
            self._gradient_image_provider[id(item)].set_bytes_data(
                self._gradient_array_hovered_list, [self.__gradient_width, self.__gradient_height]
            )
        else:
            self._gradient_image_provider[id(item)].set_bytes_data(
                self._gradient_array_list, [self.__gradient_width, self.__gradient_height]
            )

    def on_item_selected(self, primary_items, secondary_items, all_items):
        self._primary_selection = primary_items
        self._secondary_selection = secondary_items
        for item in all_items:
            self.refresh_gradient_color(item)
            for rectangle in self._background_rectangle.get(id(item), []):
                rectangle.style_type_name_override = self.__get_item_background_style(item)

    def __get_item_background_style(self, item, hovered=False):
        if item in self._primary_selection:
            if isinstance(item, _ItemReferenceFile):
                # make these less bright since they can't actually be selected on stage
                return "TreeView.Item.semi_selected"
            return "TreeView.Item.selected"
        if item in self._secondary_selection:
            return "TreeView.Item.semi_selected"
        if hovered:
            return "TreeView.Item.IsHovered"
        return "TreeView.Item"

    def build_header(self, column_id: int = 0):
        """Build the header"""
        style_type_name = "TreeView.Header"
        with ui.HStack():
            ui.Label(HEADER_DICT[column_id], style_type_name_override=style_type_name)

    def destroy(self):
        asyncio.ensure_future(self._deferred_destroy())

    @omni.usd.handle_exception
    async def _deferred_destroy(self):
        await _deferred_destroy_tasks([self.__refresh_gradient_color_task])
        _reset_default_attrs(self)
