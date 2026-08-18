"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
import pathlib
from dataclasses import dataclass, field

import omni.kit.test
from omni.flux.asset_pipeline.core import (
    PipelineContext,
    PipelineItem,
    PipelineStep,
    PipelineValidationError,
    run_pipeline,
    validate_pipeline,
)


class _PathItem(PipelineItem[pathlib.Path]):
    """Path-backed item used by generic pipeline tests."""


class _StringItem(PipelineItem[str]):
    """String-backed item used by generic pipeline tests."""


class _SceneItem(PipelineItem[dict[str, str]]):
    """Non-file item used by generic pipeline tests."""


class _TextureOnlyItem(_PathItem):
    """Typed test item used for validation."""


class _SuffixRenameStep(PipelineStep):
    """Test step that renames items matching a given suffix to a new suffix."""

    item_types = (_PathItem,)

    def __init__(self, from_suffix: str, to_suffix: str):
        super().__init__()
        self._from_suffix = from_suffix
        self._to_suffix = to_suffix

    @property
    def name(self) -> str:
        return f"rename_{self._from_suffix}_to_{self._to_suffix}"

    @property
    def description(self) -> str:
        return f"Rename {self._from_suffix} files to {self._to_suffix}"

    def should_run(self, context: PipelineContext) -> bool:
        return any(item.value.suffix == self._from_suffix for item in context.items)

    def skip_reason(self, context: PipelineContext) -> str:
        return f"no {self._from_suffix} items"

    async def run(self, context: PipelineContext) -> None:
        """Rename items that match from_suffix."""
        for item in context.items:
            if item.value.suffix == self._from_suffix:
                item.value = item.value.with_suffix(self._to_suffix)


class _SkipStep(PipelineStep):
    """Test step that declares no work."""

    item_types = (PipelineItem,)

    @property
    def name(self) -> str:
        return "skip_step"

    @property
    def description(self) -> str:
        return "Skip"

    def should_run(self, context: PipelineContext) -> bool:
        return False

    def skip_reason(self, context: PipelineContext) -> str:
        return "test skip"

    async def run(self, context: PipelineContext) -> None:
        raise AssertionError("skip step should not run")


class _FailingStep(PipelineStep):
    """Test step that mutates one item and then fails."""

    item_types = (_PathItem,)

    @property
    def name(self) -> str:
        return "failing_step"

    @property
    def description(self) -> str:
        return "Fail"

    async def run(self, context: PipelineContext) -> None:
        context.items[0].value = context.items[0].value.with_suffix(".failed")
        raise RuntimeError("partial failure")


class _UndeclaredItemTypesStep(_SuffixRenameStep):
    """Step that intentionally omits item_types to test validation."""

    item_types = ()


class _TextureOnlyStep(_SuffixRenameStep):
    """Test step that only accepts _TextureOnlyItem."""

    item_types = (_TextureOnlyItem,)


class _CountingStep(_TextureOnlyStep):
    """Step that records whether should_run was called."""

    def __init__(self):
        super().__init__(".png", ".dds")
        self.should_run_called = False

    @property
    def name(self) -> str:
        return "counting_step"

    def should_run(self, context: PipelineContext) -> bool:
        self.should_run_called = True
        return True


class _SceneTagStep(PipelineStep):
    """Test step that updates a non-file item payload."""

    item_types = (_SceneItem,)

    @property
    def name(self) -> str:
        return "scene_tag_step"

    @property
    def description(self) -> str:
        return "Update scene tag"

    async def run(self, context: PipelineContext) -> None:
        context.items[0].value = {**context.items[0].value, "tag": "processed"}


class TestPipeline(omni.kit.test.AsyncTestCase):
    """Test generic pipeline validation and execution behavior."""

    async def test_run_pipeline_awaits_progress_callback_before_step(self):
        """A runnable step starts only after its async progress callback completes."""
        # Arrange
        context = PipelineContext(items=[_PathItem(value=pathlib.Path("/textures/albedo.png"))])
        step = _SuffixRenameStep(".png", ".dds")
        callback_events: list[tuple[str, str, int, int]] = []
        observed_suffixes: list[str] = []

        async def on_step_started(progress_step: PipelineStep, index: int, total: int) -> None:
            """Record callback order and item state before step execution.

            Args:
                progress_step: Pipeline step whose execution is starting.
                index: One-based configured position of the step.
                total: Total number of configured pipeline steps.
            """
            callback_events.append(("started", progress_step.name, index, total))
            await asyncio.sleep(0)
            observed_suffixes.append(context.items[0].value.suffix)
            callback_events.append(("finished", progress_step.name, index, total))

        # Act
        await run_pipeline([step], context, on_step_started=on_step_started)

        # Assert
        self.assertEqual(
            callback_events,
            [
                ("started", step.name, 1, 1),
                ("finished", step.name, 1, 1),
            ],
        )
        self.assertEqual(observed_suffixes, [".png"])
        self.assertEqual(context.items[0].value.suffix, ".dds")

    async def test_run_pipeline_reports_only_runnable_configured_positions(self):
        """Skipped steps omit callbacks without renumbering later configured positions."""
        # Arrange
        progress: list[tuple[str, int, int]] = []
        context = PipelineContext(items=[_PathItem(value=pathlib.Path("/textures/albedo.png"))])
        disabled_step = _SuffixRenameStep(".png", ".tga")
        disabled_step.enabled = False
        skipped_step = _SkipStep()
        runnable_step = _SuffixRenameStep(".png", ".dds")

        async def on_step_started(progress_step: PipelineStep, index: int, total: int) -> None:
            """Record the configured position reported for a runnable step.

            Args:
                progress_step: Pipeline step whose execution is starting.
                index: One-based configured position of the step.
                total: Total number of configured pipeline steps.
            """
            progress.append((progress_step.name, index, total))

        # Act
        await run_pipeline(
            [disabled_step, skipped_step, runnable_step],
            context,
            on_step_started=on_step_started,
        )

        # Assert
        self.assertEqual(progress, [(runnable_step.name, 3, 3)])
        self.assertEqual(context.items[0].value.suffix, ".dds")

    async def test_run_pipeline_progress_failure_prevents_step(self):
        """A progress callback failure is recorded before the step can mutate data."""
        # Arrange
        context = PipelineContext(items=[_PathItem(value=pathlib.Path("/textures/albedo.png"))])
        step = _SuffixRenameStep(".png", ".dds")

        async def on_step_started(_step: PipelineStep, _index: int, _total: int) -> None:
            """Raise a representative progress reporting failure.

            Args:
                _step: Pipeline step whose execution would start.
                _index: One-based configured position of the step.
                _total: Total number of configured pipeline steps.

            Raises:
                RuntimeError: Always, to simulate a progress reporting failure.
            """
            raise RuntimeError("progress unavailable")

        # Act
        with self.assertRaises(RuntimeError):
            await run_pipeline([step], context, on_step_started=on_step_started)

        # Assert
        self.assertEqual(context.items[0].value.suffix, ".png")
        self.assertIn("progress unavailable", context.execution_state[step.name].error)

    async def test_step_run_transforms_items_in_place(self):
        """Step updates item.value and keeps the same item object."""
        # Arrange
        items = [
            _PathItem(value=pathlib.Path("/textures/albedo.png")),
            _PathItem(value=pathlib.Path("/textures/normal.jpg")),
        ]
        context = PipelineContext(items=items)
        step = _SuffixRenameStep(".png", ".dds")
        original_item = items[0]

        # Act
        await step.run(context)

        # Assert
        self.assertIs(items[0], original_item)
        self.assertEqual(items[0].value, pathlib.Path("/textures/albedo.dds"))
        self.assertEqual(items[1].value, pathlib.Path("/textures/normal.jpg"))

    async def test_disabled_step_skipped_leaves_items_unchanged(self):
        """When enabled=False, an executor skips the step and the next step sees the original value."""
        # Arrange
        items = [_PathItem(value=pathlib.Path("/textures/albedo.png"))]
        context = PipelineContext(items=items)
        step_a = _SuffixRenameStep(".png", ".tga")
        step_a.enabled = False
        step_b = _SuffixRenameStep(".png", ".dds")

        # Act
        await run_pipeline([step_a, step_b], context)

        # Assert
        self.assertEqual(items[0].value, pathlib.Path("/textures/albedo.dds"))
        self.assertEqual(context.execution_state[step_a.name].skip_reason, "disabled")
        self.assertTrue(context.execution_state[step_b.name].did_run)

    async def test_run_pipeline_records_skip_reason(self):
        """Executor records explicit per-step state instead of silently skipping."""
        # Arrange
        context = PipelineContext(items=[_PathItem(value=pathlib.Path("/textures/albedo.png"))])
        skip_step = _SkipStep()

        # Act
        await run_pipeline([skip_step], context)

        # Assert
        self.assertFalse(context.execution_state[skip_step.name].did_run)
        self.assertTrue(context.execution_state[skip_step.name].was_skipped)
        self.assertEqual(context.execution_state[skip_step.name].skip_reason, "test skip")

    async def test_run_pipeline_records_errors_after_partial_mutation(self):
        """Failed steps retain the mutation and record the execution error."""
        # Arrange
        items = [_PathItem(value=pathlib.Path("/textures/albedo.png"))]
        context = PipelineContext(items=items)
        step = _FailingStep()

        # Act
        with self.assertRaises(RuntimeError):
            await run_pipeline([step], context)

        # Assert
        self.assertEqual(items[0].value, pathlib.Path("/textures/albedo.failed"))
        self.assertFalse(context.execution_state[step.name].did_run)
        self.assertIn("partial failure", context.execution_state[step.name].error)

    async def test_item_value_stores_exactly_what_the_caller_provides(self):
        """PipelineItem leaves value semantics to the item author."""
        # Arrange
        value = "/textures/albedo.png"

        # Act
        item = _StringItem(value=value)

        # Assert
        self.assertIs(item.value, value)

    async def test_run_pipeline_updates_non_file_items(self):
        """Pipeline execution supports non-file item payloads."""
        # Arrange
        artifact = {"kind": "usd_scene", "id": "scene_01"}
        context = PipelineContext(items=[_SceneItem(value=artifact)])

        # Act
        await run_pipeline([_SceneTagStep()], context)

        # Assert
        self.assertEqual(context.items[0].value, {"kind": "usd_scene", "id": "scene_01", "tag": "processed"})

    async def test_context_subclass_preserves_base_fields(self):
        """Subclassing PipelineContext preserves items and execution state while adding fields."""
        # Arrange

        @dataclass
        class CustomContext(PipelineContext):
            context_name: str = ""
            prim_paths: list[str] = field(default_factory=list)

        items = [_PathItem(value=pathlib.Path("/textures/albedo.png"))]

        # Act
        ctx = CustomContext(items=items, context_name="test", prim_paths=["/World/Mesh"])

        # Assert
        self.assertEqual(len(ctx.items), 1)
        self.assertEqual(ctx.execution_state, {})
        self.assertEqual(ctx.context_name, "test")
        self.assertEqual(ctx.prim_paths, ["/World/Mesh"])

    async def test_validate_pipeline_rejects_duplicate_step_names(self):
        """Duplicate names are invalid because execution state is keyed by name."""
        # Arrange
        context = PipelineContext(items=[_PathItem(value=pathlib.Path("/textures/albedo.png"))])
        steps = [_SuffixRenameStep(".png", ".dds"), _SuffixRenameStep(".png", ".dds")]

        # Act
        with self.assertRaises(PipelineValidationError) as error_context:
            validate_pipeline(steps, context)

        # Assert
        self.assertIn("duplicate step name", str(error_context.exception))

    async def test_validate_pipeline_rejects_incompatible_item_types(self):
        """Step item declarations are validated before any mutation."""
        # Arrange
        context = PipelineContext(items=[_PathItem(value=pathlib.Path("/textures/albedo.png"))])
        step = _TextureOnlyStep(".png", ".dds")

        # Act
        with self.assertRaises(PipelineValidationError) as error_context:
            validate_pipeline([step], context)

        # Assert
        self.assertIn("expected _TextureOnlyItem", str(error_context.exception))

    async def test_validate_pipeline_requires_declared_item_types(self):
        """Steps declare item classes instead of relying on an implicit artifact type field."""
        # Arrange
        context = PipelineContext(items=[_PathItem(value=pathlib.Path("/textures/albedo.png"))])
        step = _UndeclaredItemTypesStep(".png", ".dds")

        # Act
        with self.assertRaises(PipelineValidationError) as error_context:
            validate_pipeline([step], context)

        # Assert
        self.assertIn("must declare supported PipelineItem types", str(error_context.exception))

    async def test_run_pipeline_does_not_call_should_run_after_validation_failure(self):
        """Validation errors fail before no-op checks can hide malformed input."""
        # Arrange
        context = PipelineContext(items=[_PathItem(value=pathlib.Path("/textures/albedo.png"))])
        step = _CountingStep()

        # Act
        with self.assertRaises(PipelineValidationError):
            await run_pipeline([step], context)

        # Assert
        self.assertFalse(step.should_run_called)
        self.assertEqual(context.execution_state, {})
