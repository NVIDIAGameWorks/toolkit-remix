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

from __future__ import annotations

__all__ = (
    "DEFAULT_FIELD_BUILDERS",
    "USDBuilderList",
)

from typing import TYPE_CHECKING
from collections.abc import Callable, Iterable

import carb
import omni.kit.commands
import omni.kit.undo
import omni.ui as ui
import omni.usd
from omni.flux.property_widget_builder.delegates.default import DefaultField
from omni.flux.property_widget_builder.delegates.float_value.color import ColorField
from omni.flux.property_widget_builder.delegates.float_value.color_gradient import ColorGradientField
from omni.flux.property_widget_builder.delegates.string_value.default_label import DefaultLabelField
from omni.flux.property_widget_builder.widget import FieldBuilder, FieldBuilderList, claim_each
from pxr import Gf, Sdf, Vt

from .. import mapping
from ..item_delegates.combobox_delegate import ComboboxField
from ..item_delegates.drag import USDFloatDragField, USDIntDragField
from ..item_delegates.file_texture_picker import FileTexturePicker
from ..items import USDAttributeItem as _USDAttributeItem
from ..items import USDAttrListItem as _USDAttrListItem
from ..items import USDMetadataListItem as _USDMetadataListItem
from ..items import VirtualUSDAttrListItem as _VirtualUSDAttrListItem
from ..utils import get_type_name as _get_type_name

if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import Item as _Item


class USDBuilderList(FieldBuilderList):
    """
    An extension of the FieldBuilderList that has some additional USD specific registration helpers for
    constructing FieldBuilder instances.
    """

    @staticmethod
    def claim_by_name(*names: str):
        """
        Get a FieldBuilder claim_func that will claim items whose USD attribute name matches ``names``.
        """

        def _predicate(item: _Item) -> bool:
            return (
                isinstance(item, _USDAttributeItem)
                and item._attribute_paths  # noqa: SLF001
                and any(x.name in names for x in item._attribute_paths)  # noqa: SLF001
            )

        return claim_each(_predicate)

    def _build_func_decorator(self, claim_func) -> Callable:
        def _deco(
            build_func: Callable[[_Item], ui.Widget | list[ui.Widget] | None],
        ) -> Callable[[_Item], ui.Widget | list[ui.Widget] | None]:
            self.append(FieldBuilder(claim_func=claim_func, build_func=build_func))
            return build_func

        return _deco

    def register_by_type(self, *types):
        """
        Decorator to simplify registering a build function for USDAttributeItem of specific type(s).
        """

        def _predicate(item: _USDAttributeItem) -> bool:
            try:
                metadata = item.value_models[0].metadata
            except (IndexError, AttributeError):
                return False
            return _get_type_name(metadata) in types

        return self._build_func_decorator(claim_each(_predicate))

    def register_by_name(self, *names):
        """
        Decorator to simplify registering a build function for USDAttributeItem for specific attribute name(s).
        """
        return self._build_func_decorator(self.claim_by_name(*names))

    def append_builder_by_attr_name(
        self, names: str | Iterable[str], build_func: Callable[[_Item], ui.Widget | list[ui.Widget] | None]
    ):
        """
        A simple helper which allows users to register a FieldBuilder with just attribute names and a build_func.
        """
        if isinstance(names, str):
            names = [names]

        self.append(FieldBuilder(claim_func=self.claim_by_name(*names), build_func=build_func))


def _generate_identifier(item) -> str:
    return ",".join(
        [str(attribute_path) for name_model in item.value_models for attribute_path in name_model.attribute_paths]
    )


DEFAULT_FIELD_BUILDERS = USDBuilderList()


@DEFAULT_FIELD_BUILDERS.register_build(lambda _: True)
def _fallback_builder(item) -> None:
    carb.log_warn(f"No widget builder found for {item}")
    try:
        type_name = _get_type_name(item.value_models[0].metadata)
    except (IndexError, AttributeError):
        type_name = "<unknown>"
    builder = DefaultLabelField(type_name, identifier=_generate_identifier(item))
    return builder(item)


@DEFAULT_FIELD_BUILDERS.register_by_type(
    mapping.tf_half,
    mapping.tf_float,
    mapping.tf_double,
    mapping.tf_gf_vec2f,
    mapping.tf_gf_vec2d,
    mapping.tf_gf_vec3f,
    mapping.tf_gf_vec3d,
    mapping.tf_gf_vec4f,
    mapping.tf_gf_vec4d,
)
def _floating_point_builder(item) -> list[ui.Widget]:
    builder = USDFloatDragField(identifier=_generate_identifier(item))
    return builder(item)


@DEFAULT_FIELD_BUILDERS.register_by_type(
    mapping.tf_uchar,
    mapping.tf_uint,
    mapping.tf_int,
    mapping.tf_int64,
    mapping.tf_uint64,
    mapping.tf_gf_vec2i,
    mapping.tf_gf_vec2h,
    mapping.tf_gf_vec3i,
    mapping.tf_gf_vec3h,
    mapping.tf_gf_vec4i,
    mapping.tf_gf_vec4h,
)
def _integer_builder(item) -> list[ui.Widget]:
    builder = USDIntDragField(identifier=_generate_identifier(item))
    return builder(item)


@DEFAULT_FIELD_BUILDERS.register_by_type(
    mapping.tf_bool,
)
def _bool_builder(item) -> list[ui.Widget]:
    builder = DefaultField(ui.CheckBox, style_name="PropertiesWidgetFieldBool", identifier=_generate_identifier(item))
    return builder(item)


@DEFAULT_FIELD_BUILDERS.register_by_type(
    mapping.tf_string,
)
def _string_builder(item) -> list[ui.Widget]:
    builder = DefaultField(ui.StringField, identifier=_generate_identifier(item))
    return builder(item)


@DEFAULT_FIELD_BUILDERS.register_by_type(
    mapping.tf_tf_token,
)
def _tftoken_builder(item) -> list[ui.Widget]:
    builder = DefaultField(ui.StringField, identifier=_generate_identifier(item))
    return builder(item)


@DEFAULT_FIELD_BUILDERS.register_by_type(
    mapping.tf_sdf_asset_path,
)
def _sdf_asset_path_builder(item) -> list[ui.Widget]:
    builder = FileTexturePicker()
    return builder(item)


@DEFAULT_FIELD_BUILDERS.register_by_type(
    mapping.tf_gf_col3d,
    mapping.tf_gf_col3f,
    mapping.tf_gf_col3h,
    mapping.tf_gf_col4d,
    mapping.tf_gf_col4f,
    mapping.tf_gf_col4h,
)
def _color_builder(item):
    builder = ColorField()
    return builder(item)


@DEFAULT_FIELD_BUILDERS.register_by_type(
    mapping.tf_sdf_time_code,
)
def _time_code_builder(item):
    builder = DefaultLabelField("time code", identifier=_generate_identifier(item))
    return builder(item)


@DEFAULT_FIELD_BUILDERS.register_build(
    lambda item: isinstance(item, (_USDMetadataListItem, _USDAttrListItem, _VirtualUSDAttrListItem))
)
def _build_combo(item):
    builder = ComboboxField()
    return builder(item)


# ---------------------------------------------------------------------------
# Color-gradient builder (paired *:times / *:values array attributes)
# ---------------------------------------------------------------------------


_VALUES_SUFFIX = ":values"
_TIMES_SUFFIX = ":times"


def _read_gradient_keyframes(stage, times_path, values_path):
    """Read paired USD arrays and return keyframe tuples for ColorGradientWidget."""
    times_attr = stage.GetAttributeAtPath(times_path)
    values_attr = stage.GetAttributeAtPath(values_path)
    times_val = times_attr.Get() if times_attr else None
    values_val = values_attr.Get() if values_attr else None

    if times_val is None and values_val is None:
        return []

    if times_val is None or values_val is None:
        carb.log_warn(
            f"Color gradient attribute missing or unset — expected paired :times and :values for {values_path}: "
            f"times={'unset' if times_val is None else len(times_val)} entries, "
            f"values={'unset' if values_val is None else len(values_val)} entries"
        )
        return []

    if len(times_val) != len(values_val):
        carb.log_warn(
            f"Color gradient array length mismatch: "
            f"times has {len(times_val)} entries, values has {len(values_val)} "
            f"for {values_path}. Truncating to shorter."
        )

    return [(float(t), (float(c[0]), float(c[1]), float(c[2]), float(c[3]))) for t, c in zip(times_val, values_val)]


def _is_color_gradient_values_attr(item) -> bool:
    """Claim any ``color4f[]`` attribute ending in ``:values`` whose prim also has a companion ``:times``."""
    if not isinstance(item, _USDAttributeItem):
        return False
    try:
        attr_paths = item._attribute_paths  # noqa: SLF001
    except AttributeError:
        return False
    if not attr_paths:
        return False

    attr_name = attr_paths[0].name
    if not attr_name.endswith(_VALUES_SUFFIX):
        return False

    stage = omni.usd.get_context(item.context_name).get_stage()
    if not stage:
        return False
    prim = stage.GetPrimAtPath(attr_paths[0].GetPrimPath())
    if not prim:
        return False

    values_attr = prim.GetAttribute(attr_name)
    if not values_attr or values_attr.GetTypeName() != Sdf.ValueTypeNames.Color4fArray:
        return False

    times_name = attr_name[: -len(_VALUES_SUFFIX)] + _TIMES_SUFFIX
    times_attr = prim.GetAttribute(times_name)
    return bool(times_attr and times_attr.GetTypeName() == Sdf.ValueTypeNames.FloatArray)


def _is_color_gradient_times_attr(item) -> bool:
    """Claim any ``float[]`` attribute ending in ``:times`` whose prim also has a companion ``:values``."""
    if not isinstance(item, _USDAttributeItem):
        return False
    try:
        attr_paths = item._attribute_paths  # noqa: SLF001
    except AttributeError:
        return False
    if not attr_paths:
        return False

    attr_name = attr_paths[0].name
    if not attr_name.endswith(_TIMES_SUFFIX):
        return False

    stage = omni.usd.get_context(item.context_name).get_stage()
    if not stage:
        return False
    prim = stage.GetPrimAtPath(attr_paths[0].GetPrimPath())
    if not prim:
        return False

    times_attr = prim.GetAttribute(attr_name)
    if not times_attr or times_attr.GetTypeName() != Sdf.ValueTypeNames.FloatArray:
        return False

    values_name = attr_name[: -len(_TIMES_SUFFIX)] + _VALUES_SUFFIX
    values_attr = prim.GetAttribute(values_name)
    return bool(values_attr and values_attr.GetTypeName() == Sdf.ValueTypeNames.Color4fArray)


@DEFAULT_FIELD_BUILDERS.register_build(_is_color_gradient_values_attr)
def _color_gradient_builder(item):
    value_model = item.value_models[0]
    values_path: Sdf.Path = value_model.attribute_paths[0]
    context_name = item.context_name

    attr_name = values_path.name
    times_path = values_path.ReplaceName(attr_name[: -len(_VALUES_SUFFIX)] + _TIMES_SUFFIX)

    stage = omni.usd.get_context(context_name).get_stage()
    keyframes = _read_gradient_keyframes(stage, times_path, values_path)
    read_only = getattr(value_model, "read_only", False)

    values_attr = stage.GetAttributeAtPath(values_path) if stage else None
    display_name = values_attr.GetDisplayName() if values_attr else ""
    title = display_name or attr_name[: -len(_VALUES_SUFFIX)].split(":")[-1]

    # Use the first keyframe colour as the default (e.g. for the "add marker" swatch).
    # Deriving this from keyframes avoids attr.Get() which returns None for time-sampled
    # attributes that have no authored default opinion.
    default_color = keyframes[0][1] if keyframes else None

    def on_changed(times, values):
        with omni.kit.undo.group():
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=str(times_path),
                value=Vt.FloatArray(times),
                prev=None,
                usd_context_name=context_name,
            )
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=str(values_path),
                value=Vt.Vec4fArray([Gf.Vec4f(*v) for v in values]),
                prev=None,
                usd_context_name=context_name,
            )

    def get_keyframes():
        s = omni.usd.get_context(context_name).get_stage()
        return _read_gradient_keyframes(s, times_path, values_path) if s else []

    builder = ColorGradientField(
        keyframes=keyframes,
        on_gradient_changed_fn=on_changed,
        get_keyframes_fn=get_keyframes,
        default_color=default_color,
        read_only=read_only,
        title=title,
    )
    return builder(item)


@DEFAULT_FIELD_BUILDERS.register_build(_is_color_gradient_times_attr)
def _color_gradient_times_builder(item):
    """The companion :times attribute is managed by the gradient widget — show a read-only label."""
    builder = DefaultLabelField("(gradient times)", identifier=_generate_identifier(item))
    return builder(item)
