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

__all__ = ("TestClipboard", "TestPasteSummary")

import json
from enum import Enum
from types import SimpleNamespace
from unittest import mock

import omni.kit.clipboard
import omni.kit.test
import omni.kit.undo
import omni.usd
from pxr import Sdf
from omni.flux.property_widget_builder.widget.tree import clipboard
from omni.flux.property_widget_builder.widget.tree.clipboard import AttributeCopyPasteHelper, PasteSummary
from omni.flux.utils.common.edit_result import EditResult, EditResultType
from omni.flux.property_widget_builder.widget.tests.ui_components import TestItem, TestItemModel


class TestClipboard(omni.kit.test.AsyncTestCase):
    def setUp(self):
        """Keep paste feedback at the terminal notification boundary."""
        patcher = mock.patch.object(clipboard, "post_notification")
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_paste_multiple_destination_errors_preserves_distinct_diagnostics(self):
        """Count each rejected destination even when its reason matches another destination."""
        # Arrange
        rows = [TestItem([("Field", "original")]) for _ in range(3)]
        for row, message in zip(rows, ("First rejection", "Second rejection", "First rejection")):

            def reject(_setter, value, message=message):
                return EditResult(EditResultType.REJECTED, value, message)

            row.value_models[0].set_callback_pre_set_value(reject)
        raw = '[{"properties": [{"name": ["Field"], "value": ["copied"]}]}]'
        with mock.patch.object(omni.kit.clipboard, "paste", return_value=raw):
            # Act
            result = AttributeCopyPasteHelper.paste(target_rows=rows)

        # Assert
        self.assertEqual(
            result.diagnostics, ["Field: First rejection", "Field: Second rejection", "Field: First rejection"]
        )
        self.assertEqual(result.unmatched, [])
        self.assertIn("skipped 3 properties", result.message)
        self.assertEqual([row.get_value() for row in rows], [["original"]] * 3)

    async def test_paste_unresolved_asset_reports_source_error_before_rejecting_row_shape(self):
        """Keep source diagnostics even when a generic row expects a value sequence."""
        # Arrange
        row = TestItem([("Texture", "original.dds")])
        raw = json.dumps(
            [
                {
                    "properties": [
                        {
                            "name": ["Texture"],
                            "value": {
                                "_key": "pxr.Sdf.AssetPath",
                                "_value": "./missing.dds",
                                "_source_error": "Unknown source layer",
                            },
                        }
                    ]
                }
            ]
        )
        with (
            mock.patch.object(omni.kit.clipboard, "paste", return_value=raw),
            mock.patch.object(omni.kit.undo, "group") as group,
        ):
            # Act
            result = AttributeCopyPasteHelper.paste(target_rows=[row])

        # Assert
        self.assertEqual(result.diagnostics, ["Texture: Unknown source layer"])
        self.assertEqual(result.unmatched, [])
        self.assertEqual(row.get_value(), ["original.dds"])
        group.assert_not_called()

    async def test_paste_enum_type_error_returns_failure_summary(self):
        """Preserve unexpected constructor failures instead of treating them as an unmatched value."""

        # Arrange
        class Choice(Enum):
            """Represent a model whose native converter fails unexpectedly."""

            FIRST = "first"

            @classmethod
            def _missing_(cls, value):
                """Reject missing values with the converter's original failure."""
                raise TypeError("Choice converter failed")

        row = TestItem([("Choice", Choice.FIRST)])
        raw = '[{"properties": [{"name": ["Choice"], "value": ["other"]}]}]'
        with (
            mock.patch.object(omni.kit.clipboard, "paste", return_value=raw),
            mock.patch.object(omni.kit.undo, "group"),
            mock.patch.object(PasteSummary, "show", autospec=True) as show,
        ):
            # Act
            result = AttributeCopyPasteHelper.paste(target_rows=[row])

        # Assert
        show.assert_called_once()
        self.assertIs(show.call_args.args[0], result)
        self.assertIn("TypeError: Choice converter failed", result.error)
        self.assertEqual(row.get_value(), [Choice.FIRST])

    async def test_parsed_clipboard_is_reused_even_when_empty(self):
        """Reuse supplied parsed data without reading a newer clipboard value."""
        operations = {
            "availability": AttributeCopyPasteHelper.can_paste,
            "paste": AttributeCopyPasteHelper.paste,
        }
        for operation_name, operation in operations.items():
            for has_data in (False, True):
                with self.subTest(operation=operation_name, has_data=has_data):
                    # Arrange
                    row = TestItem([("Field", "original")])
                    raw = '[{"properties": [{"name": ["Field"], "value": ["copied"]}]}]' if has_data else "[]"
                    with mock.patch.object(omni.kit.clipboard, "paste", return_value=raw):
                        data = AttributeCopyPasteHelper.read()
                    with (
                        mock.patch.object(omni.kit.clipboard, "paste") as read,
                        mock.patch.object(omni.kit.undo, "group"),
                    ):
                        # Act
                        result = operation(target_rows=[row], data=data)

                    # Assert
                    read.assert_not_called()
                    if operation_name == "availability":
                        self.assertEqual(result, has_data)
                    self.assertEqual(
                        row.get_value(), ["copied" if operation_name == "paste" and has_data else "original"]
                    )

    async def test_copy_keeps_generic_name_and_value_cardinalities_independent(self):
        """Copy generic rows without requiring equal name and value counts."""
        # Arrange
        row = TestItem([("Resolution", "1920 px")])
        row.value_models.append(TestItemModel("1080 px"))
        with mock.patch.object(omni.kit.clipboard, "copy") as copy:
            # Act
            AttributeCopyPasteHelper.copy(source_rows=[row])

        # Assert
        self.assertEqual(
            json.loads(copy.call_args.args[0]),
            [{"properties": [{"name": ["Resolution"], "value": ["1920 px", "1080 px"]}]}],
        )

    async def test_copy_preserves_native_primitive_choice_types(self):
        """Keep integer, boolean, and string choices distinct in copied data."""
        # Arrange
        rows = [TestItem([("Choice", value)]) for value in (2, False, "01")]
        with mock.patch.object(omni.kit.clipboard, "copy") as copy:
            # Act
            AttributeCopyPasteHelper.copy(source_rows=rows)

        # Assert
        values = [row["properties"][0]["value"][0] for row in json.loads(copy.call_args.args[0])]
        self.assertEqual(values, [2, False, "01"])
        self.assertEqual([type(value) for value in values], [int, bool, str])

    async def test_paste_availability_explains_matching_identity_without_writing(self):
        """Match editable row identities without changing values or undo history."""
        for name, read_only, expected in (("Field", False, True), ("Other", False, False), ("Field", True, False)):
            with self.subTest(title=f"name={name}, read_only={read_only}"):
                # Arrange
                row = TestItem([(name, "original")])
                row.value_models[0]._read_only = read_only
                raw = '[{"properties": [{"name": ["Field"], "value": ["copied"]}]}]'
                with (
                    mock.patch.object(omni.kit.clipboard, "paste", return_value=raw),
                    mock.patch.object(row, "set_row_values") as apply,
                    mock.patch.object(omni.kit.undo, "group") as group,
                ):
                    # Act
                    reason = AttributeCopyPasteHelper.get_paste_unavailable_reason(target_rows=[row])

                # Assert
                self.assertEqual(reason, None if expected else "No matching attributes found.")
                apply.assert_not_called()
                group.assert_not_called()
                self.assertEqual(row.get_value(), ["original"])

    async def test_paste_preserves_native_enum_choice_type(self):
        """Convert serialized enum values back to the destination's native choice type."""

        # Arrange
        class Choice(Enum):
            """Represent typed native choices whose labels differ from stored values."""

            FIRST = "first_choice"
            SECOND = "second_choice"

        row = TestItem([("Choice", Choice.FIRST)])
        raw = '[{"properties": [{"name": ["Choice"], "value": ["second_choice"]}]}]'
        with (
            mock.patch.object(omni.kit.clipboard, "paste", return_value=raw),
            mock.patch.object(omni.kit.undo, "group"),
        ):
            # Act
            AttributeCopyPasteHelper.paste(target_rows=[row])

        # Assert
        self.assertIs(row.get_value()[0], Choice.SECOND)

    async def test_paste_rejects_invalid_payload_without_group_or_link_change(self):
        """Reject malformed or unmatched data without opening a group or disabling linking."""
        invalid_payloads = (
            None,
            "not JSON",
            "{}",
            "[]",
            '[{"names": ["Field"], "values": [1]}]',
            '[{"properties": null}]',
            *(
                json.dumps([{"properties": [{"name": ["Field"], "value": [1]}], "type_name": type_name}])
                for type_name in (None, "", "not_a_usd_type", 4, ["float"])
            ),
            '[{"properties": [null]}]',
            '[{"properties": [{"name": 5, "value": [1]}]}]',
            '[{"properties": [{"name": ["Field"], "value": [1], "extra": true}]}]',
            '[{"properties": [{"name": ["Field"], "metadata_key": 1, "value": [1]}]}]',
            '[{"properties": [{"name": ["Field"], "value": [{"_key": "unknown", "_value": "x"}]}]}]',
            '[{"properties": [{"name": ["Field"], "value": [{"_key": "pxr.Sdf.AssetPath", "_value": 3}]}]}]',
            *(
                json.dumps(
                    [
                        {
                            "properties": [
                                {
                                    "name": ["Field"],
                                    "value": [{"_key": "pxr.Sdf.AssetPath", "_value": "./missing.dds", **extra}],
                                }
                            ]
                        }
                    ]
                )
                for extra in (
                    {"_source_error": None},
                    {"_source_error": ""},
                    {"_source_error": 3},
                    {"_source_error": "unresolved", "extra": True},
                )
            ),
            '[{"properties": [{"name": ["Field"]}]}]',
            '[{"properties": [{"name": ["Field"], "value": 1}]}]',
            '[{"properties": [{"name": ["Field"], "value": []}]}]',
            '[{"properties": [{"name": ["Field"], "value": [1, 2]}]}]',
            '[{"properties": [{"name": ["Other"], "value": [1]}]}]',
            '[{"properties": [{"name": ["Field"], "value": [1]}, {"name": ["Field"], "value": [2]}]}]',
        )
        for raw in invalid_payloads:
            with self.subTest(title=f"clipboard={raw!r}"):
                # Arrange
                row = TestItem([("Field", "original")])
                row.set_linked_edit_enabled(True)
                with (
                    mock.patch.object(omni.kit.clipboard, "paste", return_value=raw),
                    mock.patch.object(omni.kit.undo, "group") as group,
                ):
                    # Act
                    AttributeCopyPasteHelper.paste(target_rows=[row])

                # Assert
                self.assertEqual(row.get_value(), ["original"])
                self.assertTrue(row.linked_edit_enabled)
                group.assert_not_called()

    async def test_paste_reads_once_and_applies_in_destination_order_in_one_group(self):
        """Read one clipboard snapshot and apply matching destinations in one undo group."""
        # Arrange
        rows = [TestItem([("B", 0)]), TestItem([("A", 0)]), TestItem([("A", 0)])]
        raw = '[{"properties": [{"name": ["A"], "value": [1]}]}, {"properties": [{"name": ["B"], "value": [2]}]}]'
        calls = mock.Mock()
        with (
            mock.patch.object(omni.kit.clipboard, "paste", return_value=raw) as read,
            mock.patch.object(omni.kit.undo, "group") as group,
            mock.patch.object(rows[0], "set_row_values", return_value=None) as first,
            mock.patch.object(rows[1], "set_row_values", return_value=None) as second,
            mock.patch.object(rows[2], "set_row_values", return_value=None) as third,
        ):
            calls.attach_mock(group.return_value.__enter__, "enter")
            calls.attach_mock(first, "first")
            calls.attach_mock(second, "second")
            calls.attach_mock(third, "third")
            calls.attach_mock(group.return_value.__exit__, "exit")

            # Act
            AttributeCopyPasteHelper.paste(target_rows=rows)

        # Assert
        read.assert_called_once_with()
        group.assert_called_once_with(remove_if_empty=True)
        self.assertEqual(
            calls.mock_calls,
            [
                mock.call.enter(mock.ANY),
                mock.call.first((2,)),
                mock.call.second((1,)),
                mock.call.third((1,)),
                mock.call.exit(mock.ANY, None, None, None),
            ],
        )

    async def test_paste_ignores_invalid_row_and_applies_valid_row(self):
        """Skip invalid copied rows while applying valid matches."""
        for invalid in ([], [{"_key": "pxr.Sdf.AssetPath", "_value": 1}]):
            with self.subTest(value=invalid):
                # Arrange
                rows = [TestItem([("Invalid", "original")]), TestItem([("Valid", "original")])]
                raw = json.dumps(
                    [
                        {"properties": [{"name": ["Invalid"], "value": invalid}]},
                        {"properties": [{"name": ["Valid"], "value": ["copied"]}]},
                    ]
                )
                with (
                    mock.patch.object(omni.kit.clipboard, "paste", return_value=raw),
                    mock.patch.object(omni.kit.undo, "group") as group,
                ):
                    # Act
                    AttributeCopyPasteHelper.paste(target_rows=rows)

                # Assert
                self.assertEqual([row.get_value() for row in rows], [["original"], ["copied"]])
                group.assert_called_once_with(remove_if_empty=True)

    async def test_paste_setter_failure_keeps_prior_writes_and_stops_later_rows(self):
        """Stop on setter failure without rolling back earlier writes."""
        # Arrange
        rows = [TestItem([(name, 0)]) for name in ("First", "Failing", "Last")]
        raw = json.dumps([{"properties": [{"name": [name], "value": [1]}]} for name in ("First", "Failing", "Last")])
        with (
            mock.patch.object(omni.kit.clipboard, "paste", return_value=raw),
            mock.patch.object(omni.kit.undo, "group"),
            mock.patch.object(omni.kit.undo, "undo") as undo,
            mock.patch.object(rows[1].value_models[0], "set_value", side_effect=ValueError("setter rejected value")),
            mock.patch.object(PasteSummary, "show", autospec=True) as show,
            mock.patch("carb.log_warn") as log,
        ):
            # Act
            result = AttributeCopyPasteHelper.paste(target_rows=rows)

        # Assert
        self.assertEqual([row.get_value() for row in rows], [[1], [0], [0]])
        undo.assert_not_called()
        show.assert_called_once()
        self.assertIs(show.call_args.args[0], result)
        log.assert_called_once()
        self.assertIn(result.error, log.call_args.args[0])
        self.assertEqual(result.submitted_count, 1)
        self.assertIn("setter rejected value", result.error)
        self.assertIn("Traceback", result.error)

    async def test_paste_leaves_deferred_callback_write_to_existing_model_owner(self):
        """Leave delayed writes with model callbacks after the paste group closes."""
        for value in ("accepted", {"_key": "pxr.Sdf.AssetPath", "_value": "accepted"}):
            with self.subTest(title=f"value={value}"):
                # Arrange
                row = TestItem([("Texture", "original")])
                continuations = []
                row.value_models[0].set_callback_pre_set_value(
                    lambda setter, value, continuations=continuations: continuations.append((setter, value))
                )
                raw = json.dumps([{"properties": [{"name": ["Texture"], "value": [value]}]}])
                with (
                    mock.patch.object(omni.kit.clipboard, "paste", return_value=raw),
                    mock.patch.object(omni.kit.undo, "group") as group,
                ):
                    # Act
                    result = AttributeCopyPasteHelper.paste(target_rows=[row])

                # Assert
                self.assertEqual(row.get_value(), ["original"])
                self.assertEqual(len(continuations), 1)
                self.assertEqual(continuations[0][1], "accepted")
                self.assertEqual(result.deferred, ["Texture"])
                self.assertEqual(result.submitted_count, 0)
                clipboard.post_notification.assert_not_called()
                group.return_value.__exit__.assert_called_once_with(mock.ANY, None, None, None)

    async def test_can_paste_logical_outlet_honors_backing_attributes_and_read_only_state(self):
        """Allow empty-display outlets only when their backing properties are editable and complete."""
        for read_only, missing, expected in ((False, False, True), (True, False, False), (False, True, False)):
            with self.subTest(title=f"read_only={read_only}, missing={missing}"):
                # Arrange
                row = SimpleNamespace(
                    read_only=read_only,
                    linked_edit_enabled=False,
                    value_models=[],
                    value_type_name=None,
                    name_models=[],
                    context_name="outlet_context",
                    get_target_paths=lambda: [Sdf.Path("/A"), Sdf.Path("/B")],
                    get_logical_row_attribute_names=lambda: ["curve:times", "curve:values"],
                    set_row_values=mock.Mock(return_value=None),
                )
                stage = mock.Mock()
                stage.GetAttributeAtPath.side_effect = lambda path, missing=missing: (
                    None if missing and str(path) == "/B.curve:values" else mock.Mock()
                )
                raw = (
                    '[{"properties": [{"name": "curve:times", "value": [0]}, {"name": "curve:values", "value": [1]}]}]'
                )
                with (
                    mock.patch.object(omni.kit.clipboard, "paste", return_value=raw),
                    mock.patch.object(omni.usd, "get_context") as context,
                ):
                    context.return_value.get_stage.return_value = stage

                    # Act
                    result = AttributeCopyPasteHelper.can_paste(target_rows=[row])

                # Assert
                self.assertEqual(result, expected)
                row.set_row_values.assert_not_called()

    async def test_paste_logical_membership_accepts_reordering_without_reordering_array_elements(self):
        """Require complete logical membership while preserving array values and declaration order."""
        records = [
            {"name": "legacy", "value": 9},
            {"name": "curve:values", "value": [7, 5]},
            {"name": "curve:times", "value": [0, 1]},
        ]
        for variation in ("reordered", "missing", "extra", "duplicate"):
            with self.subTest(title=variation):
                # Arrange
                properties = list(records)
                if variation == "missing":
                    properties.pop()
                elif variation == "extra":
                    properties.append({"name": "unowned", "value": 0})
                elif variation == "duplicate":
                    properties.append(records[0])
                row = SimpleNamespace(
                    read_only=False,
                    linked_edit_enabled=False,
                    value_models=[],
                    value_type_name=None,
                    name_models=[],
                    context_name="outlet_context",
                    get_target_paths=lambda: [Sdf.Path("/A"), Sdf.Path("/B")],
                    get_logical_row_attribute_names=lambda: ["curve:times", "curve:values", "legacy"],
                    set_linked_edit_enabled=mock.Mock(),
                    set_row_values=mock.Mock(return_value=None),
                )
                with (
                    mock.patch.object(
                        omni.kit.clipboard, "paste", return_value=json.dumps([{"properties": properties}])
                    ),
                    mock.patch.object(omni.usd, "get_context"),
                    mock.patch.object(omni.kit.undo, "group") as group,
                ):
                    # Act
                    AttributeCopyPasteHelper.paste(target_rows=[row])

                # Assert
                if variation == "reordered":
                    row.set_row_values.assert_called_once_with(([0, 1], [7, 5], 9))
                    group.assert_called_once_with(remove_if_empty=True)
                else:
                    row.set_row_values.assert_not_called()
                    row.set_linked_edit_enabled.assert_not_called()
                    group.assert_not_called()

    async def test_copy_usd_metadata_and_fallbacks_preserves_last_source_without_authoring(self):
        """Copy last-source metadata, model fallbacks, and relationship values without authoring."""
        cases = (
            ("schema_fallback", None, 1, 8, {"name": "weight", "value": 8}),
            (
                "metadata",
                "colorSpace",
                "sRGB",
                "raw",
                {"name": "weight", "metadata_key": "colorSpace", "value": "sRGB"},
            ),
            ("metadata", "colorSpace", None, "auto", {"name": "weight", "metadata_key": "colorSpace", "value": "auto"}),
            ("relationship", None, None, "/Target", {"name": ["Display label"], "value": ["/Target"]}),
        )
        for kind, metadata_key, native, default, expected in cases:
            with self.subTest(title=f"kind={kind}, native={native}"):
                # Arrange
                model = mock.Mock(is_virtual=False, default_value=default)
                model.get_value.return_value = default if kind == "relationship" else "stale"
                model.refresh.side_effect = lambda model=model, default=default: setattr(
                    model.get_value, "return_value", default
                )
                row = SimpleNamespace(
                    read_only=False,
                    linked_edit_enabled=False,
                    context_name="source_context",
                    attribute_paths=[Sdf.Path("/First.other"), Sdf.Path("/Last.weight")],
                    metadata_key=metadata_key,
                    name_models=[TestItemModel("Display label")],
                    value_models=[model],
                    value_type_name="float" if kind == "schema_fallback" else None,
                    get_logical_row_attribute_names=lambda: None,
                )
                stage = mock.Mock()
                first = mock.Mock()
                first.GetMetadata.return_value = "first source"
                last = mock.Mock()
                last.Get.return_value = native
                last.GetMetadata.return_value = native
                last.GetTypeName.return_value = Sdf.ValueTypeNames.Float
                attributes = {"/First.other": first, "/Last.weight": last}
                stage.GetAttributeAtPath.side_effect = lambda path, kind=kind, attributes=attributes: (
                    None if kind == "relationship" else attributes[str(path)]
                )
                stage.GetRelationshipAtPath.return_value = mock.Mock() if kind == "relationship" else None
                with (
                    mock.patch.object(omni.usd, "get_context") as context,
                    mock.patch.object(omni.kit.clipboard, "copy") as copy,
                ):
                    context.return_value.get_stage.return_value = stage

                    # Act
                    AttributeCopyPasteHelper.copy(source_rows=[row])

                # Assert
                expected_row = {"properties": [expected]}
                if kind == "schema_fallback":
                    expected_row["type_name"] = "float"
                self.assertEqual(json.loads(copy.call_args.args[0]), [expected_row])
                model.set_value.assert_not_called()
                last.Set.assert_not_called()
                first.Set.assert_not_called()

    async def test_paste_missing_attributes_requires_existing_virtual_model_allowance(self):
        """Accept missing attributes only for virtual models on existing destination prims."""
        for is_virtual, missing_prim in ((False, False), (True, False), (True, True)):
            with self.subTest(title=f"is_virtual={is_virtual}, missing_prim={missing_prim}"):
                # Arrange
                model = mock.Mock(is_virtual=is_virtual)
                model.get_value.return_value = 0
                row = SimpleNamespace(
                    read_only=False,
                    linked_edit_enabled=False,
                    context_name="virtual_context",
                    attribute_paths=[Sdf.Path("/First.weight"), Sdf.Path("/Last.weight")],
                    metadata_key=None,
                    name_models=[TestItemModel("Weight")],
                    value_models=[model],
                    value_type_name=None,
                    get_logical_row_attribute_names=lambda: None,
                    set_linked_edit_enabled=mock.Mock(),
                    set_row_values=mock.Mock(return_value=None),
                )
                raw = '[{"properties": [{"name": "weight", "value": 5}]}]'
                with (
                    mock.patch.object(omni.kit.clipboard, "paste", return_value=raw),
                    mock.patch.object(omni.usd, "get_context") as context,
                    mock.patch.object(omni.kit.undo, "group") as group,
                ):
                    stage = context.return_value.get_stage.return_value
                    stage.GetAttributeAtPath.return_value = None
                    stage.GetRelationshipAtPath.return_value = None
                    stage.GetPrimAtPath.side_effect = lambda path, missing_prim=missing_prim: (
                        None if missing_prim and str(path) == "/Last" else mock.Mock()
                    )

                    # Act
                    AttributeCopyPasteHelper.paste(target_rows=[row])

                # Assert
                if is_virtual and not missing_prim:
                    row.set_row_values.assert_called_once_with((5,))
                    group.assert_called_once_with(remove_if_empty=True)
                else:
                    row.set_row_values.assert_not_called()
                    row.set_linked_edit_enabled.assert_not_called()
                    group.assert_not_called()

    async def test_paste_metadata_identity_does_not_match_attribute_value_row(self):
        """Apply metadata only to the matching metadata row, not its attribute value."""
        # Arrange
        common = {
            "read_only": False,
            "linked_edit_enabled": False,
            "context_name": "metadata_context",
            "attribute_paths": [Sdf.Path("/Material.inputs:texture")],
            "name_models": [TestItemModel("Texture")],
            "value_models": [TestItemModel("original")],
            "value_type_name": None,
            "get_logical_row_attribute_names": lambda: None,
        }
        value_row = SimpleNamespace(
            **common,
            metadata_key=None,
            set_row_values=mock.Mock(return_value=None),
            set_linked_edit_enabled=mock.Mock(),
        )
        metadata_row = SimpleNamespace(
            **common,
            metadata_key="colorSpace",
            set_row_values=mock.Mock(return_value=None),
            set_linked_edit_enabled=mock.Mock(),
        )
        raw = '[{"properties": [{"name": "inputs:texture", "metadata_key": "colorSpace", "value": "sRGB"}]}]'
        with (
            mock.patch.object(omni.kit.clipboard, "paste", return_value=raw),
            mock.patch.object(omni.usd, "get_context"),
            mock.patch.object(omni.kit.undo, "group"),
        ):
            # Act
            AttributeCopyPasteHelper.paste(target_rows=[value_row, metadata_row])

        # Assert
        value_row.set_row_values.assert_not_called()
        metadata_row.set_row_values.assert_called_once_with(("sRGB",))


class TestPasteSummary(omni.kit.test.AsyncTestCase):
    """Pin paste feedback independently of notification widgets."""

    def setUp(self):
        """Keep summary display at the terminal notification boundary."""
        patcher = mock.patch.object(clipboard, "post_notification")
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_show_deferred_properties_leaves_feedback_to_confirmation_dialog(self):
        """Keep deferred-only and mixed successful edits quiet while confirmation owns completion."""
        for submitted_count in (0, 1):
            with self.subTest(submitted_count=submitted_count):
                # Arrange
                summary = PasteSummary(
                    copied=["Roughness", "Texture"], submitted_count=submitted_count, deferred=["Texture"]
                )

                # Act
                summary.show()

                # Assert
                clipboard.post_notification.assert_not_called()
                self.assertEqual(summary.deferred, ["Texture"])

    async def test_show_empty_error_takes_precedence_over_empty_clipboard(self):
        """Report failures even when no copied properties or traceback text are available."""
        # Arrange
        summary = PasteSummary(error="")

        # Act
        summary.show()

        # Assert
        self.assertEqual(summary.title, "Paste failed")
        self.assertIn("rolled back", summary.message)

    async def test_show_diagnostics_override_mismatches_and_retain_adjustments(self):
        """Keep rejected values, unmatched identities, and clamp explanations in one warning."""
        # Arrange
        summary = PasteSummary(
            copied=["Value", "MissingSourceAttribute"],
            submitted_count=1,
            diagnostics=["Bad path"],
            unmatched=["MissingSourceAttribute"],
            adjustments=["Value: 2 -> 1."],
            deferred=["Texture"],
        )

        # Act
        summary.show()

        # Assert
        self.assertEqual(summary.title, "Skipped properties")
        self.assertIn("could not be accepted", summary.message)
        self.assertNotIn("not been applied yet", summary.message)
        for detail in ("Bad path", "MissingSourceAttribute", "Value: 2 -> 1."):
            self.assertIn(detail, summary.details.splitlines())
