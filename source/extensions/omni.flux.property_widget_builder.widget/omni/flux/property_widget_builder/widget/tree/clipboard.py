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

__all__ = ("AttributeCopyPasteHelper", "PasteSummary")

import json
import traceback
from contextlib import ExitStack
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

import carb
import omni.kit.clipboard
import omni.kit.undo
import omni.usd
from omni.flux.utils.common.edit_result import EditResultType
from omni.flux.utils.common.path_utils import get_asset_path_for_attribute, is_absolute_path
from omni.flux.utils.dialog.error_popup import ErrorPopup
from omni.kit.notification_manager import NotificationButtonInfo, NotificationStatus, post_notification
from pxr import Sdf

_REJECTED_VALUE = object()


@dataclass
class PasteSummary:
    """Collect property outcomes and display one paste notification with optional details."""

    submitted_count: int = 0
    copied: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    error: str | None = None
    title: str = ""
    message: str = ""
    details: str = ""

    def show(self, *, show_unmatched_details: bool = False) -> None:
        """Present actionable outcomes, leaving deferred edits to their confirmation dialogs."""
        if self.error is not None:
            self.title = "Paste failed"
            self.message = (
                f"Paste failed after submitting {self.submitted_count} matching properties. "
                "Earlier changes have not been rolled back. See Details or the Console for error information."
            )
            self.details = f"Some changes may already have been applied.\n\n{self.error}"
        elif not self.copied:
            return
        elif self.diagnostics:
            self.title = "Skipped properties" if self.submitted_count else "Properties could not be pasted"
            self.message = (
                f"Submitted {self.submitted_count} matching properties; "
                f"skipped {len(self.unmatched) + len(self.diagnostics)} properties. "
                "Some values could not be accepted by the destination."
            )
            self.details = "Property issues:\n\n" + "\n\n".join(self.diagnostics)
            if self.unmatched:
                self.details += "\n\nOther unmatched properties:\n" + "\n".join(self.unmatched)
        elif not self.submitted_count and not self.deferred:
            self.title, self.message = "Properties do not match", "No matching attributes found."
        elif self.unmatched:
            self.title = "Skipped properties"
            self.message = (
                f"Submitted {self.submitted_count} matching properties; "
                f"skipped {len(self.unmatched)} unmatched properties."
            )
            if show_unmatched_details:
                self.details = (
                    "These properties had no compatible editable destination. "
                    "Attribute names must match exactly, even when display names are the same.\n\n"
                    + "\n".join(self.unmatched)
                )
        elif self.adjustments:
            self.title = "Adjusted values"
            self.message = "Pasted values were adjusted to the destination field limits. " + " ".join(self.adjustments)
        else:
            return
        if self.adjustments and (self.error is not None or self.diagnostics or self.unmatched):
            self.message += " Some values were adjusted to the destination field limits."
            if self.details:
                self.details += "\n\nAdjusted values:\n" + "\n".join(self.adjustments)
            else:
                self.message += " " + " ".join(self.adjustments)
        buttons = (
            [NotificationButtonInfo("Details", on_complete=lambda: AttributeCopyPasteHelper.show_paste_details(self))]
            if self.details
            else []
        )
        post_notification(self.message, status=NotificationStatus.WARNING, duration=8, button_infos=buttons)


@runtime_checkable
class _UsdRow(Protocol):
    """Identify USD row context without importing its concrete model extension."""

    attribute_paths: list[Sdf.Path]
    context_name: str
    metadata_key: str | None


@dataclass
class _CopiedRow:
    """Retain copied identities and optional USD type information."""

    properties: dict
    type_name: str | None = None
    errors: dict = field(default_factory=dict)


class AttributeCopyPasteHelper:
    """Clipboard ownership for property rows; models retain editing policy."""

    _paste_details_popup: ErrorPopup | None = None

    @classmethod
    def destroy_paste_details(cls) -> None:
        """Release the active Details dialog when its property panel is reset or destroyed."""
        if cls._paste_details_popup is not None:
            cls._paste_details_popup.destroy()
            cls._paste_details_popup = None

    @classmethod
    def show_paste_details(cls, summary: PasteSummary) -> None:
        """Display the collected property explanations in the existing error dialog."""
        cls.destroy_paste_details()
        cls._paste_details_popup = ErrorPopup(summary.title, summary.message, details=summary.details)
        cls._paste_details_popup.show()

    @staticmethod
    def _encode(value):
        """Encode a native value for JSON, normalizing asset path separators.

        Raises:
            TypeError: If the value has no supported JSON representation.
        """
        if isinstance(value, Sdf.AssetPath):
            return {"_key": "pxr.Sdf.AssetPath", "_value": (value.resolvedPath or value.path).replace("\\", "/")}
        if isinstance(value, Enum):
            return value.value
        # Native vectors and arrays become JSON sequences without changing their order.
        try:
            return list(value)
        except TypeError as error:
            raise TypeError(f"Unsupported property value: {type(value).__name__}") from error

    @classmethod
    def _decode(cls, value):
        """Decode native values from JSON containers.

        Raises:
            ValueError: If a typed record is unsupported or malformed.
        """
        if isinstance(value, list):
            return [cls._decode(component) for component in value]
        if not isinstance(value, dict):
            return value
        if "_key" not in value:
            return {key: cls._decode(component) for key, component in value.items()}
        return cls._decode_asset_path_record(value)

    @staticmethod
    def _decode_asset_path_record(value):
        """Decode a supported asset record or reject its malformed fields."""
        if (
            not {"_key", "_value"} <= value.keys()
            or value.keys() - {"_key", "_value", "_source_error"}
            or value["_key"] != "pxr.Sdf.AssetPath"
        ):
            raise ValueError("Unsupported serialized property type")
        if not isinstance(value["_value"], str):
            raise ValueError("Invalid serialized asset path")
        if "_source_error" in value and (not isinstance(value["_source_error"], str) or not value["_source_error"]):
            raise ValueError("Invalid serialized asset path diagnostic")
        return Sdf.AssetPath(value["_value"])

    @staticmethod
    def _properties(row):
        """Return eligible canonical identities and backing attributes using the existing row contracts."""
        if row.read_only:
            return []
        names = row.get_logical_row_attribute_names()
        if names is not None:
            stage = omni.usd.get_context(row.context_name).get_stage()
            if not stage:
                return []
            targets = row.get_target_paths()
            attributes = [
                [stage.GetAttributeAtPath(Sdf.Path(target).AppendProperty(name)) for target in targets]
                for name in names
            ]
            if not targets or any(not attribute for group in attributes for attribute in group):
                return []
            return [((name, None), group[-1]) for name, group in zip(names, attributes)]
        if isinstance(row, _UsdRow):
            stage = omni.usd.get_context(row.context_name).get_stage()
            if not stage or not row.attribute_paths:
                return []
            attributes = [stage.GetAttributeAtPath(path) for path in row.attribute_paths]
            if all(attributes):
                return [((row.attribute_paths[-1].name, row.metadata_key), attributes[-1])]
            if all(stage.GetRelationshipAtPath(path) for path in row.attribute_paths):
                return [((tuple(model.get_value() for model in row.name_models), None), None)]
            if not all(model.is_virtual for model in row.value_models) or not all(
                stage.GetPrimAtPath(path.GetPrimPath()) for path in row.attribute_paths
            ):
                return []
            return [((row.attribute_paths[-1].name, row.metadata_key), attributes[-1])]
        return [((tuple(model.get_value() for model in row.name_models), None), None)]

    @staticmethod
    def _read_value(row, identity, attribute):
        """Read the existing model representation while retaining raw source assets and logical values."""
        name, metadata_key = identity
        if row.get_logical_row_attribute_names() is not None:
            return attribute.Get()
        if isinstance(name, tuple):
            return [model.get_value() for model in row.value_models]
        if metadata_key:
            value = attribute.GetMetadata(metadata_key) if attribute else None
            return row.value_models[0].default_value if value is None else value
        if attribute and attribute.GetTypeName() == Sdf.ValueTypeNames.Asset:
            return row.value_models[0].get_attributes_raw_value(-1)
        values = []
        for model in row.value_models:
            model.refresh()
            values.append(
                model.get_attributes_raw_value(-1)
                if len(row.value_models) == 1 and (not attribute or model.is_virtual and attribute.Get() is None)
                else model.get_value()
            )
        return values[0] if len(values) == 1 else values

    @classmethod
    def _copy_record(cls, row, identity, attribute):
        """Read a property while retaining an asset's source identity or diagnostic."""
        name, metadata_key = identity
        value = cls._read_value(row, identity, attribute)
        record = {"name": name, "value": value}
        if (
            isinstance(value, Sdf.AssetPath)
            and value.path
            and not value.resolvedPath
            and not is_absolute_path(value.path)
        ):
            try:
                location = get_asset_path_for_attribute(attribute, value)
                record["value"] = Sdf.AssetPath(location)
            except ValueError as error:
                record["source_error"] = str(error)
        if metadata_key is not None:
            record["metadata_key"] = metadata_key
        return record

    @classmethod
    def copy(cls, *, source_rows) -> None:
        """Copy eligible rows using property identities rather than source prim paths."""
        data = []
        for row in source_rows:
            properties = cls._properties(row)
            if not properties:
                continue
            copied_row = {
                "properties": [cls._copy_record(row, identity, attribute) for identity, attribute in properties]
            }
            type_name = row.value_type_name
            if type_name:
                copied_row["type_name"] = type_name
            data.append(copied_row)
        omni.kit.clipboard.copy(json.dumps(data, default=cls._encode))

    @classmethod
    def _parse_record(cls, record):
        """Parse one property identity and value, rejecting malformed fields."""
        if not isinstance(record, dict) or not {"name", "value"} <= record.keys():
            return None
        if record.keys() - {"name", "value", "metadata_key", "source_error"}:
            return None
        name = record["name"]
        if isinstance(name, list) and name and all(isinstance(part, str) for part in name):
            name = tuple(name)
        elif not isinstance(name, str) or not name:
            return None
        key = record.get("metadata_key")
        if key is not None and (not isinstance(key, str) or not key):
            return None
        source_error = record.get("source_error")
        if source_error is None and isinstance(record["value"], dict):
            source_error = record["value"].get("_source_error")
        if source_error is not None and (not isinstance(source_error, str) or not source_error):
            return None
        try:
            return (name, key), cls._decode(record["value"]), source_error
        except ValueError:
            return None

    @classmethod
    def _parse_row(cls, row) -> _CopiedRow | None:
        """Parse a complete nonempty row without accepting partial or duplicate records."""
        if (
            not isinstance(row, dict)
            or "properties" not in row
            or row.keys() - {"properties", "type_name"}
            or not isinstance(row["properties"], list)
        ):
            return None
        type_name = row.get("type_name")
        if "type_name" in row and (
            not isinstance(type_name, str) or not type_name or not Sdf.ValueTypeNames.Find(type_name)
        ):
            return None
        records = {}
        errors = {}
        for record in row["properties"]:
            parsed = cls._parse_record(record)
            if parsed is None:
                return None
            identity, value, error = parsed
            if identity in records:
                return None
            records[identity] = value
            if error is not None:
                errors[identity] = error
        return _CopiedRow(records, type_name, errors) if records else None

    @classmethod
    def read(cls) -> list[_CopiedRow]:
        """Read one clipboard snapshot, rejecting malformed or duplicate property rows."""
        try:
            data = json.loads(omni.kit.clipboard.paste())
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        rows = [cls._parse_row(row) for row in data]
        return [row for row in rows if row is not None]

    @staticmethod
    def _convert_native_value(value, current, type_name):
        """Restore native vector and enum values without coercing unrelated scalar types."""
        if type_name == str(Sdf.ValueTypeNames.Int) and isinstance(current, str) and not isinstance(value, str):
            return _REJECTED_VALUE
        if type_name and isinstance(value, list) and current is not None and not isinstance(current, (list, tuple)):
            try:
                value = type(current)(value)
            except (TypeError, ValueError):
                return _REJECTED_VALUE
        if isinstance(current, Enum):
            try:
                value = type(current)(value)
            except ValueError:
                return _REJECTED_VALUE
        return value

    @classmethod
    def _convert_for_models(cls, row, identities, records, type_name):
        """Prepare assets once per backing value and arrange native destination model values."""
        if row.get_logical_row_attribute_names() is not None:
            return tuple(cls._prepare_asset(records[identity], row) for identity in identities)
        value = cls._prepare_asset(records[identities[0]], row)
        if isinstance(identities[0][0], tuple) or len(row.value_models) > 1:
            if not isinstance(value, (list, tuple)) or len(value) != len(row.value_models):
                return None
            values = tuple(value)
        else:
            values = (value,)
        prepared = []
        for model, incoming in zip(row.value_models, values):
            value = cls._prepare_asset(incoming, row) if isinstance(incoming, Sdf.AssetPath) else incoming
            value = cls._convert_native_value(value, model.get_value(), type_name)
            if value is _REJECTED_VALUE:
                return None
            prepared.append(value)
        return tuple(prepared)

    @classmethod
    def _prepare(cls, rows, data, *, allow_name_mismatch: bool = False):
        """Yield per-source diagnostics and the first successful match for each destination row."""
        for row in rows:
            properties = cls._properties(row)
            identities = [identity for identity, _ in properties]
            if not identities:
                continue
            for source_index, source in enumerate(data):
                records = source.properties
                if set(records) != set(identities):
                    if not (
                        allow_name_mismatch
                        and len(data) == len(records) == len(identities) == 1
                        and source.type_name
                        and source.type_name == row.value_type_name
                    ):
                        continue
                    records = {identities[0]: next(iter(records.values()))}
                if source.errors:
                    for identity, error in source.errors.items():
                        yield row, source_index, None, f"{cls._describe([identity])}: {error}"
                    continue
                try:
                    values = cls._convert_for_models(row, identities, records, source.type_name)
                except ValueError as error:
                    yield row, source_index, None, f"{cls._describe(records)}: {error}"
                    continue
                if values is not None:
                    yield row, source_index, values, None
                    break

    @staticmethod
    def _prepare_asset(value, row):
        """Convert a preserved asset identity without rebasing unknown source paths.

        Raises:
            ValueError: If the source asset location is unknown.
        """
        if not isinstance(value, Sdf.AssetPath):
            return value
        path = value.resolvedPath or value.path
        is_usd = isinstance(row, _UsdRow)
        if path and is_usd and not is_absolute_path(path):
            raise ValueError(f"Source asset path could not be resolved or anchored. Authored path: {value.path}")
        return path

    @classmethod
    def can_paste(cls, *, target_rows, allow_name_mismatch: bool = False, data=None) -> bool:
        """Check row eligibility using a supplied snapshot or one fresh clipboard read."""
        return (
            cls.get_paste_unavailable_reason(
                target_rows=target_rows, allow_name_mismatch=allow_name_mismatch, data=data
            )
            is None
        )

    @classmethod
    def get_paste_unavailable_reason(cls, *, target_rows, allow_name_mismatch: bool = False, data=None) -> str | None:
        """Return the matching explanation, or None when a destination can accept a paste attempt."""
        data = cls.read() if data is None else data
        if not data:
            return "Copy properties before pasting."
        reason = "No matching attributes found."
        for _, _, _, error in cls._prepare(target_rows, data, allow_name_mismatch=allow_name_mismatch):
            if error is None:
                return None
            reason = error
        return reason

    @staticmethod
    def _describe(identities) -> str:
        """Format canonical property identities for paste feedback."""
        return ", ".join(
            f"{' / '.join(name) if isinstance(name, tuple) else name}{f' ({key})' if key else ''}"
            for name, key in identities
        )

    @staticmethod
    def _row_label(row) -> str:
        """Return the displayed property label used in diagnostics and adjustments."""
        return " / ".join(str(model.get_value()) for model in row.name_models)

    @classmethod
    def paste(
        cls,
        *,
        target_rows,
        allow_name_mismatch: bool = False,
        data=None,
    ) -> PasteSummary:
        """Submit grouped row edits and return the summary, including any logged setter failure.

        Setters retain ownership of validation and delayed writes; submission does not confirm authoring.
        A supplied parsed snapshot is reused, while omitted data reads the current clipboard once.
        """
        result = PasteSummary()
        try:
            data = cls.read() if data is None else data
            rows = list(target_rows)
            result.copied = [cls._describe(source.properties) for source in data]
            matched = set()
            failed = set()
            with ExitStack() as undo_scope:
                group_open = False
                for row, source_index, values, error in cls._prepare(
                    rows, data, allow_name_mismatch=allow_name_mismatch
                ):
                    if error is not None:
                        result.diagnostics.append(error)
                        failed.add(source_index)
                        continue
                    if not group_open:
                        undo_scope.enter_context(omni.kit.undo.group(remove_if_empty=True))
                        group_open = True
                    was_linked = row.linked_edit_enabled
                    row.set_linked_edit_enabled(False)
                    outcomes = row.set_row_values(values)
                    accepted = outcomes is None or not outcomes
                    pending = False
                    for incoming, outcome in zip(values, outcomes or ()):
                        if outcome.status == EditResultType.REJECTED:
                            result.diagnostics.append(f"{cls._row_label(row)}: {outcome.reason}")
                            failed.add(source_index)
                        elif outcome.status == EditResultType.DEFERRED:
                            pending = True
                            matched.add(source_index)
                        else:
                            accepted = True
                            if outcome.status == EditResultType.CLAMPED:
                                result.adjustments.append(
                                    f"{cls._row_label(row)}: {incoming} -> {outcome.value} (destination field limits)."
                                )
                    if accepted:
                        result.submitted_count += 1
                        matched.add(source_index)
                    elif not pending:
                        row.set_linked_edit_enabled(was_linked)
                    if pending:
                        result.deferred.append(cls._row_label(row))
            result.unmatched = [
                text for index, text in enumerate(result.copied) if index not in matched and index not in failed
            ]
        except Exception as error:
            result.error = traceback.format_exc()
            carb.log_warn(f"Property paste failed: {result.error}")
            if not isinstance(error, (RuntimeError, TypeError, ValueError)):
                raise
        finally:
            result.show(show_unmatched_details=not allow_name_mismatch)
        return result
