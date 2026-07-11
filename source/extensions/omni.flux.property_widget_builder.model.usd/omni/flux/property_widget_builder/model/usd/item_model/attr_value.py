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
import copy
from typing import Any
from collections.abc import Callable

import carb
import omni.client
import omni.kit.commands
import omni.kit.undo
import omni.usd
from omni.flux.property_widget_builder.widget import ItemValueModel as _ItemValueModel
from omni.flux.property_widget_builder.widget import Serializable as _Serializable
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common.interactive_usd_notices import defer_usd_notices as _defer_usd_notices
from pxr import Gf, Sdf, Usd

from ..mapping import GF_TO_PYTHON_TYPE, MULTICHANNEL_BUILDER_TABLE, VEC_TYPES, VecType
from ..utils import get_default_attribute_value as _get_default_attribute_value
from ..utils import get_item_attributes as _get_item_attributes
from ..utils import get_metadata as _get_metadata
from ..utils import get_type_name as _get_type_name
from ..utils import is_item_overriden as _is_item_overriden

_CHANNEL_NAMES = ("X", "Y", "Z", "W")


def _get_channel_name(channel_index: int) -> str:
    """Get the display name for a multichannel value index."""
    try:
        return _CHANNEL_NAMES[channel_index]
    except IndexError:
        return str(channel_index)


def _safe_deepcopy(value):
    """
    Deepcopy that handles USD types (like Vt arrays) that don't support pickling.

    Args:
        value: The value to copy

    Returns:
        A deep copy of the value, or a type-constructed copy for non-picklable USD types
    """
    try:
        return copy.deepcopy(value)
    except (TypeError, RuntimeError):
        # Vt arrays and some other USD types don't support pickling.
        # Try to create a copy using the type constructor.
        try:
            return type(value)(value)
        except Exception:  # noqa: BLE001
            # If all else fails, return the original value.
            # Caller should be aware this may not be a true copy.
            return value


class UsdAttributeBase(_Serializable, abc.ABC):
    """
    The model mixin to watch USD attribute paths.
    """

    _is_virtual = False

    def __init__(
        self,
        context_name: str,
        attribute_paths: list[Sdf.Path],
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
        tooltip_display_name: str | None = None,
        tooltip_channel_name: str | None = None,
        related_override_paths: list[Sdf.Path] | None = None,
    ):
        """
        Base model of a USD attribute value.

        Subclasses should call `init_attributes` at the end of their init.

        Args:
            context_name: the context name
            attribute_paths:  the path(s) of the attribute
            read_only: if the attribute is read only or not
            value_type_name: the type name of the attribute
            tooltip_display_name: optional display name used to prefix value widget tooltips
            tooltip_channel_name: optional channel suffix used to identify multichannel value widget tooltips
            related_override_paths: optional related properties that should receive specs with this value write
        """
        super().__init__()
        self._context_name = context_name
        self._stage = omni.usd.get_context(context_name).get_stage()
        self._attribute_paths = attribute_paths
        self._related_override_paths = list(dict.fromkeys(related_override_paths or []))
        self._read_only = read_only
        self._is_mixed = False
        self._tooltip_display_name = tooltip_display_name
        self._tooltip_channel_name = tooltip_channel_name

        if not value_type_name:
            value_type_name = self._get_type_name(self.metadata)
        self._value_type_name: Sdf.ValueTypeName = value_type_name
        self._convert_type = GF_TO_PYTHON_TYPE.get(self._value_type_name)

        self._value = None  # The value that will be represented by the widget
        self._values = []  # The values of all the attribute paths
        self._summary_limit = 25  # max amount of values to display in a tooltip
        self._ignore_refresh = False
        self._attributes: list[Usd.Attribute] = None
        self._is_batch_editing = False

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
            # Always emit the authored path. The hook is intentionally not a strict
            # mirror of deserialize_asset_path: serialize captures what USD was given
            # at the source (relative, absolute, or unresolved-pending-ingest), and
            # deserialize re-anchors that string against the destination's edit target.
            # Using value.resolvedPath here would drop paths whose target isn't on disk
            # yet — the original bug this hook is fixing.
            return value.path.replace("\\", "/")

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

    @property
    def supports_batch_edit(self) -> bool:
        return True

    @property
    def is_batch_editing(self) -> bool:
        return self._is_batch_editing

    def get_tool_tip(self):
        """Get the value tooltip, prefixed with field identity when available."""
        should_use_separate_lines = len(str(self.get_value())) > 10

        if self.is_mixed:
            values = self._values[: self._summary_limit]
            more = "..." if len(self._values) > self._summary_limit else ""
            separator = "\n" if should_use_separate_lines else ", "
            summary_suffix = "\n" if should_use_separate_lines else ""
            value_text = separator.join(str(v) for v in values)
            value_tooltip = f"Mixed Values: {summary_suffix}{value_text}{more}"
        else:
            value_tooltip = self._get_value_as_string()

        display_name = self._tooltip_display_name or (self._attribute_paths[0].name if self._attribute_paths else None)
        if not display_name:
            return value_tooltip

        if self._tooltip_channel_name:
            display_name = f"{display_name} {self._tooltip_channel_name}"
        return f"{display_name}: {value_tooltip}"

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
    def _set_attribute_value(self, attr: Usd.Attribute, new_value: Any, target_layer: Sdf.Layer | None = None) -> bool:
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
        """Read attribute values from USD and refresh cached mixed-value state.

        When multiple attribute paths contribute values, ``self._is_mixed``
        still reflects whether any value differs from the first one read, but
        the cached displayed value follows the last attribute encountered in
        iteration order.

        Returns:
            True if the cached value or mixed-value state changed; otherwise
            False.
        """
        if not self._stage:
            assert self._value is None
            return False

        first_value = None
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
                    first_value = value
                else:
                    is_mixed |= first_value != value
                last_value = value
                values_read += 1
                self._values.append(value)

        display_value_changed = values_read > 0 and (self._value is None or last_value != self._value)
        if display_value_changed:
            self._value = last_value
            value_was_set = True
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
        return bool(
            value is None
            or value == "."
            or isinstance(value, str)
            and value.strip() == ""
            and self._value_type_name not in {Sdf.ValueTypeNames.String, Sdf.ValueTypeNames.Asset}
        )

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

        if self._is_batch_editing:
            self._on_dirty()
            return True

        if not self._stage:
            return False

        if self._related_override_paths:
            with omni.kit.undo.group():
                wrote_value = self._write_value_to_usd()
        else:
            wrote_value = self._write_value_to_usd()

        if wrote_value:
            self.refresh()
            return True
        # value was not changed, but we do want to refresh the delegate
        self._on_dirty()
        return False

    def _write_value_to_usd(self) -> bool:
        """Write the current in-memory value to USD for all attribute paths.

        Returns True if at least one attribute was updated, False otherwise.
        """
        if not self._stage:
            return False
        wrote_any = False
        self._ignore_refresh = True
        try:
            with _defer_usd_notices(self._stage):
                for attribute_path in self._attribute_paths:
                    prim = self._stage.GetPrimAtPath(attribute_path.GetPrimPath())
                    if prim.IsValid():
                        attr = prim.GetAttribute(attribute_path.name)
                        if attr.IsValid():
                            current_value = self._get_attribute_value(attr)
                        elif self._is_virtual:
                            current_value = self._get_default_value(attr)
                        else:
                            continue
                        if current_value != self._value:
                            target_layer = self._get_target_layer(attr)
                            wrote_any = self._ensure_related_override_specs(attr, target_layer) or wrote_any
                            wrote_any = self._set_attribute_value(attr, self._value, target_layer) or wrote_any
        except Exception:
            if self._read_value_from_usd():
                self._on_dirty()
            raise
        finally:
            self._ignore_refresh = False
        return wrote_any

    def _get_target_layer(self, attr: Usd.Attribute) -> Sdf.Layer:
        """Get the layer that should receive a value write for the attribute."""
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
        return target_layer

    def _ensure_related_override_specs(self, attr: Usd.Attribute, target_layer: Sdf.Layer) -> bool:
        """Author missing related property specs in the same layer as a value write."""
        wrote_any = False
        attr_path = attr.GetPath()
        prim_path = attr_path.GetPrimPath()
        for related_path in self._related_override_paths:
            if related_path == attr_path or related_path.GetPrimPath() != prim_path:
                continue
            if target_layer.GetPropertyAtPath(related_path) is not None:
                continue
            related_attr = self._stage.GetAttributeAtPath(related_path)
            if not related_attr or not related_attr.IsValid():
                continue
            omni.kit.commands.execute(
                "ChangeProperty",
                prop_path=str(related_path),
                value=related_attr.Get(),
                target_layer=target_layer,
                prev=None,
                usd_context_name=self._context_name,
            )
            wrote_any = True
        return wrote_any

    def begin_batch_edit(self):
        """Start a drag batch so intermediate values stay in memory until release."""
        self._is_batch_editing = True
        omni.kit.undo.begin_group()

    def end_batch_edit(self):
        """Flush the final drag value to USD and close the undo group."""
        try:
            if not self._stage:
                return
            if self._write_value_to_usd():
                self.refresh()
        finally:
            self._is_batch_editing = False
            omni.kit.undo.end_group()

    def _cancel_batch_edit(self):
        try:
            if self._stage and self._read_value_from_usd():
                self._value_changed()
        finally:
            self._is_batch_editing = False
            omni.kit.undo.end_group()

    def _refresh_after_cancel_property_edit(self) -> None:
        pass

    def cancel_property_edit_interaction(self) -> None:
        first_error: Exception | None = None
        try:
            if self.is_batch_editing:
                self._cancel_batch_edit()
        except Exception as exc:  # noqa: BLE001 - parent cancel callbacks must still run.
            first_error = exc
        try:
            self._refresh_after_cancel_property_edit()
        except Exception as exc:  # noqa: BLE001 - parent cancel callbacks must still run.
            if first_error is None:
                first_error = exc
        try:
            super().cancel_property_edit_interaction()
        except Exception as exc:  # noqa: BLE001 - preserve the first lifecycle failure.
            if first_error is None:
                first_error = exc
        if first_error is not None:
            raise first_error


class UsdAttributeValueModel(UsdAttributeBase, _ItemValueModel):
    """
    The value model to watch USD attribute paths.
    """

    def __init__(
        self,
        context_name: str,
        attribute_paths: list[Sdf.Path],
        channel_index: int,
        default_value: Any = None,
        read_only: bool = False,
        value_type_name: Sdf.ValueTypeName | None = None,
        tooltip_display_name: str | None = None,
        related_override_paths: list[Sdf.Path] | None = None,
    ):
        """
        Value model of an attribute value

        Args:
            context_name: the context name
            attribute_paths:  the path(s) of the attribute
            channel_index: the channel index of the attribute
            read_only: if the attribute is read only or not
            value_type_name: the type name of the attribute
            tooltip_display_name: optional display name used to prefix value widget tooltips
            default_value: optional override for the default value
            related_override_paths: optional related properties that should receive specs with this value write
        """
        super().__init__(
            context_name,
            attribute_paths,
            read_only=read_only,
            value_type_name=value_type_name,
            tooltip_display_name=tooltip_display_name,
            related_override_paths=related_override_paths,
        )
        self._channel_index = channel_index
        # should we treat value as a "multi" value or by channel.
        self._is_multichannel = MULTICHANNEL_BUILDER_TABLE.get(self._value_type_name, False)
        self._tooltip_channel_name = _get_channel_name(channel_index) if self._is_multichannel else None
        self._has_wrong_value = False
        self._default_value = default_value
        self.init_attributes()

    def begin_paste(self):
        """Refresh ``self._value`` from USD before this channel's deserialize.

        ``Item.apply_serialized_data`` interleaves begin_paste/deserialize per channel,
        so by the time we're called the previous channel has already committed its
        write to USD. Re-reading here gives us the up-to-date full vector, ensuring
        the subsequent ``_write_value_to_usd`` (which writes the whole ``self._value``)
        doesn't clobber a sibling channel that was written earlier in the same paste
        tick. Single-channel models don't need the refresh, so ``begin_paste``
        skips the call entirely via the ``_is_multichannel`` guard.
        """
        if self._is_multichannel:
            self._read_value_from_usd()

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
            self._value[self._channel_index] = new_value
        else:
            self._value = new_value

    def _get_default_value(self, attr):
        """Get the USD default value, or the override if provided"""
        if self._default_value is not None:
            return _safe_deepcopy(self._default_value)
        return _safe_deepcopy(_get_default_attribute_value(attr))

    @property
    def is_default(self):
        """If the value model has the default USD value"""
        for index, attribute in enumerate(self.attributes):
            if not attribute:
                continue
            default_value = self._get_default_value(attribute)
            attribute_value = self.get_attributes_raw_value(index)
            if attribute_value is None:
                continue
            if default_value != attribute_value:
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
        first_error: Exception | None = None
        try:
            if self.is_batch_editing:
                self.end_batch_edit()
        except Exception as exc:  # noqa: BLE001 - parent end callback must still run.
            first_error = exc
        try:
            # we set back to the USD value
            should_refresh = self._has_wrong_value
            self._has_wrong_value = False
            if should_refresh and self._read_value_from_usd():
                self._value_changed()
        except Exception as exc:  # noqa: BLE001 - parent end callback must still run.
            if first_error is None:
                first_error = exc
        try:
            super().end_edit()
        except Exception as exc:  # noqa: BLE001 - preserve the first lifecycle failure.
            if first_error is None:
                first_error = exc
        if first_error is not None:
            raise first_error

    def _refresh_after_cancel_property_edit(self) -> None:
        should_refresh = self._has_wrong_value
        self._has_wrong_value = False
        if should_refresh and self._read_value_from_usd():
            self._value_changed()

    # TODO: Remove usages after dealing with Asset path type. Most cases would be better served with get_value().
    def get_attributes_raw_value(self, element_current_idx) -> Any | None:
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
        # If we have an override default and no value was authored, use the override default
        if self._default_value is not None and not attr.HasAuthoredValue():
            return _safe_deepcopy(self._default_value)
        return value

    def _prepare_attribute_value(self, new_value) -> tuple[bool, Any]:
        if self._value_type_name != Sdf.ValueTypeNames.Asset:
            self._has_wrong_value = False
            return True, new_value
        if isinstance(new_value, str):
            # Force textures to always use forward slashes, and check that the path is valid
            new_value = new_value.strip()
            if self.metadata and self.metadata.get("colorSpace"):
                edit_target_layer = self._stage.GetEditTarget().GetLayer()
                is_valid = new_value == "" or _path_utils.is_file_path_valid(new_value, layer=edit_target_layer)
                if not is_valid:
                    self._has_wrong_value = True
                    return False, new_value
                absolute_path = omni.client.normalize_url(edit_target_layer.ComputeAbsolutePath(new_value))
                new_value = Sdf.AssetPath(new_value.replace("\\", "/"), absolute_path.replace("\\", "/"))
        elif isinstance(new_value, Sdf.AssetPath):
            if self.metadata and self.metadata.get("colorSpace"):
                edit_target_layer = self._stage.GetEditTarget().GetLayer()
                if not _path_utils.is_file_path_valid(new_value.path, layer=edit_target_layer):
                    self._has_wrong_value = True
                    return False, new_value
        else:
            raise NotImplementedError(f"Unknown type {new_value}")
        self._has_wrong_value = False
        return True, new_value

    def _set_attribute_value(self, attr: Usd.Attribute, new_value: Any, target_layer: Sdf.Layer | None = None) -> bool:
        if not attr.IsValid():
            return False
        attribute_path = str(attr.GetPath())
        is_valid, new_value = self._prepare_attribute_value(new_value)
        if not is_valid:
            return False

        if target_layer is None:
            target_layer = self._get_target_layer(attr)

        omni.kit.commands.execute(
            "ChangeProperty",
            prop_path=attribute_path,
            value=new_value,
            target_layer=target_layer,
            prev=None,
            usd_context_name=self._context_name,
        )
        return True

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
        default_value: Any = None,
        read_only: bool = False,
        metadata: dict | None = None,
        create_callback: Callable[[Usd.Attribute, Any], None] | None = None,
        tooltip_display_name: str | None = None,
        related_override_paths: list[Sdf.Path] | None = None,
    ):
        self._create_callback = create_callback

        if not value_type_name:
            raise ValueError("value_type_name is required for virtual attribute value models")
        self._metadata = metadata or {Sdf.PrimSpec.TypeNameKey: str(value_type_name)}
        is_multichannel = MULTICHANNEL_BUILDER_TABLE.get(value_type_name, False)
        if is_multichannel and default_value is not None:
            default_value = default_value[channel_index]

        super().__init__(
            context_name,
            attribute_paths,
            channel_index,
            read_only=read_only,
            value_type_name=value_type_name,
            tooltip_display_name=tooltip_display_name,
            related_override_paths=related_override_paths,
        )

        # Set _default_value AFTER super().__init__() to avoid being overwritten by the parent class
        self._default_value = default_value

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

    def get_attributes_raw_value(self, element_current_idx: int) -> Any | None:
        attr = self._attributes[element_current_idx]
        if isinstance(attr, Usd.Attribute) and attr.IsValid() and not attr.IsHidden():
            raw_value = attr.Get()
            if raw_value is not None:
                return raw_value
        # If virtual attributes don't exist, they take on the default value.
        return self._default_value

    def _create_and_set_attribute_value(self, attr: Usd.Attribute, new_value: Any) -> bool:
        # If it's the default value, no need to create anything
        if new_value == self._default_value:
            return False
        is_valid, new_value = self._prepare_attribute_value(new_value)
        if not is_valid:
            return False
        # If a create_callback is set, use that
        if self._create_callback:
            self._create_callback(attr, new_value)
        # Otherwise use the default creation
        else:
            path = attr.GetPath()
            if not path.IsPropertyPath():
                raise ValueError(f"Cannot create virtual attribute from invalid property path: {path}")
            prim = self._stage.GetPrimAtPath(path.GetPrimPath())
            omni.kit.commands.execute(
                "CreateUsdAttributeCommand",
                prim=prim,
                attr_name=path.name,
                attr_type=self._value_type_name,
                attr_value=new_value,
            )
        return True

    def _set_attribute_value(self, attr: Usd.Attribute, new_value: Any, target_layer: Sdf.Layer | None = None) -> bool:
        """
        Override to set the attribute value.

        If a virtual attribute is changed we need to first create it.
        """
        if attr.IsValid():
            return super()._set_attribute_value(attr, new_value, target_layer)
        return self._create_and_set_attribute_value(attr, new_value)
