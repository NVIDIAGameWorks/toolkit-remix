"""
* Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.ui as ui
import omni.usd
from lightspeed.asset_capture_localizer.core import AssetCaptureLocalizerCore
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

HEADER_DICT = {0: "Reference path", 1: "Mesh name", 2: "Nickname", 3: "Capture layer path"}


def _get_nickname(prim):
    if prim.HasAttribute("nickname"):
        return prim.GetAttribute("nickname").Get()
    return ""


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, prim, ref, layer, capture_layer_path):
        super().__init__()
        self.prim = prim
        self.ref = ref
        self.layer = layer
        self.capture_layer_path = capture_layer_path
        self.ref_asset_path_model = ui.SimpleStringModel(self.ref.assetPath if self.ref else "None")
        self._nickname = None

    @property
    def nickname(self) -> str:
        return _get_nickname(self.prim)

    def __repr__(self):
        return f'"{self.ref.assetPath}"'


class ListModel(ui.AbstractItemModel):
    """List model of actions"""

    def __init__(self):
        super().__init__()
        self.default_attr = {"_core": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self._context = omni.usd.get_context()
        self._filter = None
        self._core = AssetCaptureLocalizerCore(self._context)
        self.__children = []
        self.__children_unfiltered = []

    def get_stage_selection(self):
        return self._context.get_selection().get_selected_prim_paths()

    def refresh(self):
        """Refresh the list"""
        items = []
        user_references = self._core.get_all_user_references()
        for prim, ref, layer, capture_layer_path in user_references:
            if (
                self._filter
                and self._filter.lower() not in prim.GetPath().pathString.lower()
                and ((ref and self._filter.lower() not in ref.assetPath.lower()) or not ref)
                and self._filter.lower() not in capture_layer_path.lower()
                and self._filter.lower() not in _get_nickname(prim).lower()
            ):
                continue
            items.append(Item(prim, ref, layer, capture_layer_path))
        items = sorted(items, key=lambda x: x.ref.assetPath if x.ref else "None")
        self.__children = items
        self.__children_unfiltered = items
        self._item_changed(None)

    def filter_items(self):
        items = []
        for item in self.__children_unfiltered:
            if (
                self._filter
                and self._filter.lower() not in item.prim.GetPath().pathString.lower()
                and ((item.ref and self._filter.lower() not in item.ref.assetPath.lower()) or not item.ref)
                and self._filter.lower() not in item.capture_layer_path.lower()
                and self._filter.lower() not in item.nickname.lower()
            ):
                continue
            items.append(item)
        items = sorted(items, key=lambda x: x.ref.assetPath if x.ref else "None")
        self.__children = items
        self._item_changed(None)

    def set_filter(self, filter_str):
        self._filter = filter_str

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__children
        return []

    def get_item_value_model_count(self, item):
        """The number of columns"""
        return len(HEADER_DICT.keys())

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        if column_id == 0:
            return item.ref_asset_path_model
        return None

    def destroy(self):
        _reset_default_attrs(self)
