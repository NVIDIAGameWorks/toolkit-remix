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

import abc
from typing import Any, Callable, List, Optional

import carb
import omni.client
import omni.kit.commands
import omni.kit.undo
import omni.usd
from omni.flux.property_widget_builder.widget import ItemValueModel as _ItemValueModel
from omni.flux.property_widget_builder.widget import Serializable as _Serializable
from omni.flux.utils.common import path_utils as _path_utils
from pxr import Gf, Sdf, Usd

from ..mapping import GF_TO_PYTHON_TYPE, MULTICHANNEL_BUILDER_TABLE, VEC_TYPES, VecType
from ..utils import get_default_attribute_value as _get_default_attribute_value
from ..utils import get_item_attributes as _get_item_attributes
from ..utils import get_metadata as _get_metadata
from ..utils import get_type_name as _get_type_name
from ..utils import is_item_overriden as _is_item_overriden


class UsdAttributeBase(_Serializable, abc.ABC):
    """
    The model mixin to watch USD attribute paths.
    """

    _is_virtual = False

    def __init__(
        self,
        context_name: str,
        attribute_paths: List[Sdf.Path],
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
    ):
        """
        Base model of a USD attribute value.

        Subclasses should call `init_attributes` at the end of their init.

        Args:
            context_name: the context name
            attribute_paths:  the path(s) of the attribute
            read_only: if the attribute is read only or not
            value_type_name: the type name of the attribute
        """
        super().__init__()
        self._context_name = context_name
        self._stage = omni.usd.get_context(context_name).get_stage()
        self._attribute_paths = attribute_paths
        self._read_only = read_only
        self._is_mixed = False

        if not value_type_name:
            value_type_name = self._get_type_name(self.metadata)
        self._value_type_name: Sdf.ValueTypeName = value_type_name
        self._convert_type = GF_TO_PYTHON_TYPE.get(self._value_type_name)

        self._value = None  # The value that will be represented by the widget
        self._values = []  # The values of all the attribute paths
        self._summary_limit = 25  # max amount of values to display in a tooltip
        self._ignore_refresh = False
        self._attributes: list[Usd.Attribute] = None

    def init_attributes(self):
        # cache the attributes
        self._attributes = _get_item_attributes(self.stage, self.attribute_paths)
        # initial read of attribute values
        self._on_usd_changed()

    def register_serializer_hooks(self, serializer):
        super().register_serializer_hooks(serializer)

        @serializer.register_serialize_hook(lambda x: isinstance(x, VEC_TYPES), key="Gf.Vec*")
        def serialize_vec(value: VecType) -> dict[str, str | list[float]]:
            return {"type": value.__class__.__name__, "value": list(value)}

        @serializer.register_deserialize_hook(lambda x: isinstance(x, VEC_TYPES), key="Gf.Vec*")
        def deserialize_vec(value: dict[str, str | list[float]]) -> VecType:
            return getattr(Gf, value["type"])(*value["value"])

        @serializer.register_serialize_hook(Sdf.AssetPath)
        def serialize_asset_path(value: Sdf.AssetPath) -> str:
            return value.resolvedPath.replace("\\", "/")

        @serializer.register_deserialize_hook(Sdf.AssetPath)
        def deserialize_asset_path(value: str) -> str:
            return omni.client.normalize_url(
                omni.usd.make_path_relative_to_current_edit_target(value, stage=self.stage)
            ).replace("\\", "/")

    @property
    def context_name(self):
        return self._context_name

    @property
    def attribute_paths(self):
        return self._attribute_paths

    @property
    def stage(self):
        return self._stage

    @property
    def metadata(self):
        if not self._stage:
            carb.log_error("Can't find the stage")
            return {}
        return _get_metadata(self._context_name, self._attribute_paths)

    @property
    def read_only(self):
        return self._read_only

    @property
    def attributes(self):
        return self._attributes

    @abc.abstractmethod
    def _get_default_value(self, attr):
        pass

    @property
    @abc.abstractmethod
    def is_default(self):
        """If the value model has the default USD value"""
        pass

    @property
    def is_overriden(self):
        """If the value model has an override"""
        return _is_item_overriden(self.stage, self.attributes)

    @property
    def is_mixed(self):
        """Tell us if the model is "mixed". Meaning that the value has multiple values from multiple USD prims"""
        return self._is_mixed

    def get_tool_tip(self):
        """Get the tooltip that best represents the current value"""
        summary = ""
        more = ""
        should_use_separate_lines = len(str(self.get_value())) > 10

        if self.is_mixed:
            summary += "Mixed Values: "
            if should_use_separate_lines:
                summary += "\n"
        else:
            return self._get_value_as_string()

        values = self._values
        if len(self._values) > self._summary_limit:
            values = self._values[: self._summary_limit]
            more = "..."
        separator = "\n" if should_use_separate_lines else ", "
        value_text = separator.join(str(v) for v in values)
        return summary + value_text + more

    @staticmethod
    def _get_type_name(metadata):
        return _get_type_name(metadata)

    @abc.abstractmethod
    def reset_default_value(self):
        """Reset the model's value back to the USD default"""
        pass

    @abc.abstractmethod
    def _get_attribute_value(self, attr) -> Any:
        pass

    @abc.abstractmethod
    def _set_attribute_value(self, attr, new_value):
        pass

    def _get_value_as_string(self) -> str:
        if self._is_mixed:
            return "<Mixed>"  # string field is able to give useful information for this case
        value = self.get_value()
        if value is None:
            return ""
        # isinstance check for metadata that may have different value than type
        if self._value_type_name == Sdf.ValueTypeNames.Asset or isinstance(value, Sdf.AssetPath):
            # get path string to remove @...@ for display
            return str(value.path)
        return str(value)

    def _get_value_as_float(self) -> float:
        value = self.get_value()
        if value is None:
            return 0.0
        return float(value)

    def _get_value_as_bool(self) -> bool:
        value = self.get_value()
        if value is None:
            return False
        return bool(value)

    def _get_value_as_int(self) -> int:
        value = self.get_value()
        if value is None:
            return 0
        return int(value)

    def _set_internal_value(self, new_value):
        """Set internal value from a widget value"""
        self._value = new_value

    def _read_value_from_usd(self):
        """
        Return:
            True if the cached value was updated; false otherwise
        """
        if not self._stage:
            assert self._value is None
            return False

        last_value = None
        values_read = 0
        value_was_set = False
        is_mixed = False
        self._values = []
        for attribute_path in self._attribute_paths:
            prim = self._stage.GetPrimAtPath(attribute_path.GetPrimPath())
            if prim.IsValid():
                attr = prim.GetAttribute(attribute_path.name)
                if attr.IsHidden():
                    continue

                if attr.IsValid():
                    value = self._get_attribute_value(attr)
                elif self._is_virtual:
                    value = self._get_default_value(attr)
                else:
                    continue

                if values_read == 0:
                    # If this is the first prim with this attribute, use it for the cached value.
                    last_value = value
                    if self._value is None or value != self._value:
                        self._value = value  # we can set directly from the _get_attribute_value value
                        value_was_set = True
                else:
                    if last_value != value:
                        is_mixed = True
                values_read += 1
                self._values.append(value)

        if is_mixed != self._is_mixed:
            value_was_set = True
        self._is_mixed = is_mixed
        return value_was_set

    def _on_usd_changed(self):
        """Called with when an attribute in USD is changed"""
        self._read_value_from_usd()

    @abc.abstractmethod
    def _on_dirty(self):
        pass

    def refresh(self):
        if self._ignore_refresh:
            return
        self._on_usd_changed()
        self._on_dirty()

    def _skip_set_value(self, value):
        if self.read_only:
            return True
        if (
            value is None
            or value == "."
            or (
                isinstance(value, str)
                and value.strip() == ""
                and self._value_type_name not in [Sdf.ValueTypeNames.String, Sdf.ValueTypeNames.Asset]
            )
        ):
            return True
        return False

    def _set_value(self, value):
        """Override of ui.AbstractValueModel._set_value()"""
        if self._skip_set_value(value):
            return False

        new_value = value
        if self._convert_type is not None:
            try:
                new_value = self._convert_type(value)
            except (ValueError, TypeError):
                attribs_names = [attr.GetName() for attr in self.attributes]
                carb.log_warn(
                    f"Failed to use convert type: {self._convert_type} with value: "
                    f"{value} for attributes: {attribs_names}"
                )

        self._set_internal_value(new_value)

        if not self._stage:
            return False

        need_refresh = False
        for attribute_path in self._attribute_paths:
            prim = self._stage.GetPrimAtPath(attribute_path.GetPrimPath())
            if prim.IsValid():
                attr = prim.GetAttribute(attribute_path.name)
                if not attr.IsValid() and not self._is_virtual:
                    continue
                current_value = self._get_attribute_value(attr)
                if current_value != self._value:
                    need_refresh = True
                    self._ignore_refresh = True
                    self._set_attribute_value(attr, self._value)
                    self._ignore_refresh = False
        if need_refresh:
            self.refresh()
            return True
        # value was not changed, but we do want to refresh the delegate
        self._on_dirty()
        return False


class UsdAttributeValueModel(UsdAttributeBase, _ItemValueModel):
    """
    The value model to watch USD attribute paths.
    """

    def __init__(
        self,
        context_name: str,
        attribute_paths: List[Sdf.Path],
        channel_index: int,
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
    ):
        """
        Value model of an attribute value

        Args:
            context_name: the context name
            attribute_paths:  the path(s) of the attribute
            channel_index: the channel index of the attribute
            read_only: if the attribute is read only or not
            type_name: the type name of the attribute
        """
        super().__init__(
            context_name,
            attribute_paths,
            read_only=read_only,
            value_type_name=value_type_name,
        )
        self._channel_index = channel_index
        # should we treat value as a "multi" value or by channel.
        self._is_multichannel = MULTICHANNEL_BUILDER_TABLE.get(self._value_type_name, False)
        self._has_wrong_value = False
        self.init_attributes()

    def get_value(self):
        """Get the value for serialization and external consumption."""
        if self._value is None:
            return None  # not set yet...
        # TODO: Store path object in self._value instead.
        if self._value_type_name == Sdf.ValueTypeNames.Asset:
            # NOTE: Sdf.AssetPath are supported in the serializer
            return self.get_attributes_raw_value(self._channel_index)
        if self._is_multichannel:
            return self._value[self._channel_index]
        return self._value

    def _set_internal_value(self, new_value):
        """Inverse of get_value. Prep widget value for storing in self._value."""
        if self._is_multichannel:
            # may not always be a dict, since this is a USD type
            self._value[self._channel_index] = new_value
        else:
            self._value = new_value

    def _get_default_value(self, attr):
        """Get the USD default value"""
        return _get_default_attribute_value(attr)

    @property
    def is_default(self):
        """If the value model has the default USD value"""
        for index, attribute in enumerate(self.attributes):
            if not attribute:
                continue
            default_value = self._get_default_value(attribute)
            if default_value != self.get_attributes_raw_value(index):
                return False
        return True

    def reset_default_value(self):
        """Reset the model's value back to the USD default"""
        self.block_set_value(False)  # be sure that we set the value
        for index, attribute in enumerate(self.attributes):
            if not attribute:
                continue
            default_value = self._get_default_value(attribute)
            if default_value is None:
                continue
            # If the item is subscriptable, get the right value
            if self._is_multichannel:
                self.set_value(default_value[index])
            else:
                if self._value_type_name == Sdf.ValueTypeNames.Asset:
                    default_value = default_value.path
                self.set_value(default_value)

    def begin_edit(self):
        super().begin_edit()
        # In the case where widget A is currently editing, then user clicks directly
        # on Widget B to start editing, B's begin_edit will come through before A's end_edit.
        # Refresh to ensure that the cached _value is up-to-date, in the case that model updates are suppressed during
        # edit
        if self._read_value_from_usd():
            self._value_changed()

    def end_edit(self):
        # we set back to the USD value
        if self._has_wrong_value and self._read_value_from_usd():
            self._value_changed()
        super().end_edit()

    # TODO: Remove usages after dealing with Asset path type. Most cases would be better served with get_value().
    def get_attributes_raw_value(self, element_current_idx) -> Optional[Any]:
        prim = self._stage.GetPrimAtPath(self._attribute_paths[element_current_idx].GetPrimPath())
        if prim.IsValid():
            attr = prim.GetAttribute(self._attribute_paths[element_current_idx].name)
            if attr.IsValid() and not attr.IsHidden():
                return attr.Get()
        return None

    def _get_attribute_value(self, attr):
        value = attr.Get()
        if value is not None and self._value_type_name == Sdf.ValueTypeNames.Asset:
            return value.path
        return value

    def _set_attribute_value(self, attr, new_value):
        attribute_path = str(attr.GetPath())
        if self._value_type_name == Sdf.ValueTypeNames.Asset:  # noqa SIM102
            if isinstance(new_value, str):
                # Force textures to always use forward slashes, and check that the path is valid
                new_value = new_value.strip()
                if self.metadata and self.metadata.get("colorSpace"):
                    edit_target_layer = self._stage.GetEditTarget().GetLayer()
                    is_valid = new_value == "" or _path_utils.is_file_path_valid(new_value, layer=edit_target_layer)
                    if not is_valid:
                        self._has_wrong_value = True
                        return
                    absolute_path = omni.client.normalize_url(edit_target_layer.ComputeAbsolutePath(new_value))
                    new_value = Sdf.AssetPath(new_value.replace("\\", "/"), absolute_path.replace("\\", "/"))
            elif isinstance(new_value, Sdf.AssetPath):
                if self.metadata and self.metadata.get("colorSpace"):
                    edit_target_layer = self._stage.GetEditTarget().GetLayer()
                    if not _path_utils.is_file_path_valid(new_value.path, layer=edit_target_layer):
                        self._has_wrong_value = True
                        return
            else:
                raise NotImplementedError(f"Unknown type {new_value}")
        self._has_wrong_value = False

        # OM-75480: For props inside session layer, it will always change specs
        # in the session layer to avoid shadowing. Why it needs to be def is that
        # session layer is used for several runtime data for now as built-in cameras,
        # MDL material params, and etc. Not all of them create runtime prims inside
        # session layer. For those that are not defined inside session layer, we should
        # avoid leaving delta inside other sublayers as they are shadowed and useless after
        # stage close.
        target_layer, _ = omni.usd.find_spec_on_session_or_its_sublayers(
            self._stage, attr.GetPath().GetPrimPath(), lambda spec: spec.specifier == Sdf.SpecifierDef
        )
        if not target_layer:
            target_layer = self._stage.GetEditTarget().GetLayer()

        omni.kit.commands.execute(
            "ChangeProperty",
            prop_path=attribute_path,
            value=new_value,
            target_layer=target_layer,
            prev=None,
            usd_context_name=self._context_name,
        )

    def _on_dirty(self):
        self._value_changed()


class VirtualUsdAttributeValueModel(UsdAttributeValueModel):
    """
    The value model to watch USD attribute paths that may or may not exist yet.
    """

    _is_virtual = True

    def __init__(
        self,
        context_name: str,
        attribute_paths: list[Sdf.Path],
        channel_index: int,
        value_type_name: Sdf.ValueTypeName,
        read_only: bool = False,
        default_value: Any = None,
        metadata: dict | None = None,
        create_callback: Callable[[Usd.Attribute, Any], None] | None = None,
    ):
        self._create_callback = create_callback

        if not value_type_name:
            raise ValueError("type_name is required for virtual attribute value models")
        self._metadata = metadata or {Sdf.PrimSpec.TypeNameKey: str(value_type_name)}
        is_multichannel = MULTICHANNEL_BUILDER_TABLE.get(value_type_name, False)
        if is_multichannel and default_value is not None:
            default_value = default_value[channel_index]
        self._default_value = default_value

        super().__init__(
            context_name,
            attribute_paths,
            channel_index,
            read_only=read_only,
            value_type_name=value_type_name,
        )

    def _get_default_value(self, attr):
        # Since the attribute does not exist, we need to retrieve the stored value.
        return self._default_value

    @property
    def metadata(self):
        # Since the attribute does not exist, we need to retrieve the stored value.
        return self._metadata

    def get_value(self):
        """Get the value for serialization and external consumption."""
        if self._value is None and self._is_virtual:
            return self._default_value  # not set yet...
        return super().get_value()

    def get_attributes_raw_value(self, element_current_idx: int) -> Optional[Any]:
        attr = self._attributes[element_current_idx]
        if isinstance(attr, Usd.Attribute) and attr.IsValid() and not attr.IsHidden():
            raw_value = attr.Get()
            if raw_value is not None:
                return raw_value
        # If virtual attributes don't exist, they take on the default value.
        return self._default_value

    def _create_and_set_attribute_value(self, attr, new_value):
        # If it's the default value, no need to create anything
        if new_value == self._default_value:
            return
        # If a create_callback is set, use that
        if self._create_callback:
            self._create_callback(attr, new_value)
        # Otherwise use the default creation
        else:
            path = attr.GetPath()
            if not path.IsPropertyPath():
                return
            prim = self._stage.GetPrimAtPath(path.GetPrimPath())
            omni.kit.commands.execute(
                "CreateUsdAttributeCommand",
                prim=prim,
                attr_name=path.name,
                attr_type=self._value_type_name,
                attr_value=new_value,
            )

    def _set_attribute_value(self, attr, new_value):
        """
        Override to set the attribute value.

        If a virtual attribute is changed we need to first create it.
        """
        if attr:
            super()._set_attribute_value(attr, new_value)
        else:
            self._create_and_set_attribute_value(attr, new_value)
