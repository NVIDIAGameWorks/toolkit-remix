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

__all__ = (
    "USDBuilderList",
    "DEFAULT_FIELD_BUILDERS",
)

from typing import TYPE_CHECKING, Callable, Iterable

import carb
import omni.ui as ui
from omni.flux.property_widget_builder.delegates.default import DefaultField
from omni.flux.property_widget_builder.delegates.float_value.color import ColorField
from omni.flux.property_widget_builder.delegates.string_value.default_label import DefaultLabelField
from omni.flux.property_widget_builder.widget import FieldBuilder, FieldBuilderList

from .. import mapping
from ..item_delegates.combobox_delegate import ComboboxField
from ..item_delegates.file_texture_picker import FileTexturePicker
from ..items import USDAttributeItem as _USDAttributeItem
from ..items import USDAttrListItem as _USDAttrListItem
from ..items import USDMetadataListItem as _USDMetadataListItem
from ..utils import get_type_name as _get_type_name

if TYPE_CHECKING:
    from omni.flux.property_widget_builder.widget import Item as _Item


class USDBuilderList(FieldBuilderList):
    """
    An extension of the FieldBuilderList that has some additional USD specific registration helpers for
    constructing FieldBuilder instances.
    """

    @staticmethod
    def claim_by_name(*names: str) -> Callable[["_Item"], bool]:
        """
        Get a FieldBuilder claim_func that will claim items that use any USD attributes that match `names`.
        """

        def _claim(item: "_Item") -> bool:
            return (
                isinstance(item, _USDAttributeItem)
                and item._attribute_paths  # noqa PLW0212
                and any(x.name in names for x in item._attribute_paths)  # noqa PLW0212
            )

        return _claim

    def _build_func_decorator(self, claim_func) -> Callable:
        def _deco(
            build_func: Callable[["_Item"], ui.Widget | list[ui.Widget] | None]
        ) -> Callable[["_Item"], ui.Widget | list[ui.Widget] | None]:
            self.append(FieldBuilder(claim_func=claim_func, build_func=build_func))
            return build_func

        return _deco

    def register_by_type(self, *types):
        """
        Decorator to simplify registering a build function for USDAttributeItem of specific type(s).
        """

        def _claim(item: "_Item") -> bool:
            try:
                metadata = item.value_models[0].metadata
            except (IndexError, AttributeError):
                return False
            return _get_type_name(metadata) in types

        return self._build_func_decorator(_claim)

    def register_by_name(self, *names):
        """
        Decorator to simplify registering a build function for USDAttributeItem for specific attribute name(s).
        """
        return self._build_func_decorator(self.claim_by_name(*names))

    def append_builder_by_attr_name(
        self, names: str | Iterable[str], build_func: Callable[["_Item"], ui.Widget | list[ui.Widget] | None]
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
    builder = DefaultField(ui.FloatField, identifier=_generate_identifier(item))
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
    builder = DefaultField(ui.IntField, identifier=_generate_identifier(item))
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


@DEFAULT_FIELD_BUILDERS.register_build(lambda item: isinstance(item, (_USDMetadataListItem, _USDAttrListItem)))
def _build_combo(item):
    builder = ComboboxField()
    return builder(item)
