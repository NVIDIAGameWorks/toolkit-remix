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
import tempfile
import threading
from unittest.mock import AsyncMock, patch

import omni.kit.test
from omni.flux.asset_importer.core.data_models import TextureTypes
from omni.flux.asset_pipeline.core import PipelineStep, PipelineValidationError

import lightspeed.trex.asset_pipeline.core.pipeline.runner as pipeline_runner_module
from lightspeed.trex.asset_pipeline.core import (
    RemixAssetItem,
    RemixAssetPipelineConfig,
    RemixAssetPipelineContext,
    TextureAsset,
    build_remix_mesh_pipeline,
    run_remix_asset_pipeline,
)


class TestRemixAssetPipelineRunner(omni.kit.test.AsyncTestCase):
    """Test Remix pipeline workspace and publication behavior."""

    async def test_pipeline_step_descriptions_are_user_facing(self):
        """Progress descriptions explain work without exposing implementation formats."""
        # Arrange
        config = RemixAssetPipelineConfig(
            output_dir=pathlib.Path("/processed"),
            texture_type=TextureTypes.DIFFUSE,
        )
        # Act
        descriptions = [step.description for step in build_remix_mesh_pipeline(config, {})]

        # Assert
        self.assertEqual(
            descriptions,
            [
                "Prepare source files",
                "Remove orphaned materials and add fallback materials",
                "Prepare model materials",
                "Normalize legacy emissive intensity",
                "Apply processed textures",
                "Make asset paths and reference arcs relative",
                "Wrap processed model roots and normalize unit scale",
            ],
        )

    async def test_runner_cancellation_after_workspace_creation_removes_workspace(self):
        """The runner owns and removes a workspace before cancellation can be delivered."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            event_loop = asyncio.get_running_loop()
            event_loop_thread = threading.get_ident()
            test_task = asyncio.current_task()
            create_threads: list[int] = []
            create_directory = pathlib.Path.mkdir

            def create_then_cancel(path: pathlib.Path, *args, **kwargs) -> None:
                """Create the workspace and schedule cancellation of the active test task.

                Args:
                    path: Workspace path to create before scheduling cancellation.
                    *args: Positional arguments forwarded to ``Path.mkdir``.
                    **kwargs: Keyword arguments forwarded to ``Path.mkdir``.
                """
                create_directory(path, *args, **kwargs)
                if path.name.startswith("remix_asset_pipeline_"):
                    create_threads.append(threading.get_ident())
                    event_loop.call_soon_threadsafe(test_task.cancel)

            # Act
            with (
                patch.object(pathlib.Path, "mkdir", autospec=True, side_effect=create_then_cancel),
                self.assertRaises(asyncio.CancelledError) as error_context,
            ):
                await run_remix_asset_pipeline(
                    RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                    RemixAssetPipelineContext(),
                    steps=[],
                )

            # Assert
            self.assertIsInstance(error_context.exception, asyncio.CancelledError)
            self.assertEqual(len(create_threads), 1)
            self.assertNotEqual(create_threads[0], event_loop_thread)
            self.assertEqual(_remaining_work_dirs(temp_path), [])

    async def test_runner_reports_publication_as_final_step(self):
        """The final publish phase is included after all configured processing steps."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            context = RemixAssetPipelineContext(items=[RemixAssetItem.from_model(temp_path / "chair.fbx")])
            progress: list[tuple[str, str, int, int]] = []

            async def on_step_started(step: PipelineStep, index: int, total: int) -> None:
                """Record a reported pipeline step and its progress counters.

                Args:
                    step: Pipeline step that started.
                    index: One-based position of the started step.
                    total: Total number of pipeline steps.
                """
                progress.append((step.name, step.description, index, total))

            # Act
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                context,
                steps=[_write_many_outputs_step()],
                on_step_started=on_step_started,
            )

            # Assert
            self.assertEqual(
                progress,
                [
                    ("write_many_outputs", "Write several final files from one item", 1, 2),
                    ("publish_outputs", "Save processed assets", 2, 2),
                ],
            )

    async def test_runner_publishes_off_event_loop(self):
        """Blocking publication runs on a worker thread rather than Kit's event loop."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            context = RemixAssetPipelineContext()
            event_loop_thread = threading.get_ident()
            publish_threads: list[int] = []
            publish_outputs = pipeline_runner_module._publish_outputs

            def record_publish_thread(*args, **kwargs) -> None:
                """Record the publication thread before forwarding the call.

                Args:
                    *args: Positional arguments forwarded to the publisher.
                    **kwargs: Keyword arguments forwarded to the publisher.
                """
                publish_threads.append(threading.get_ident())
                publish_outputs(*args, **kwargs)

            # Act
            with patch.object(pipeline_runner_module, "_publish_outputs", side_effect=record_publish_thread):
                await run_remix_asset_pipeline(
                    RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                    context,
                    steps=[],
                )

            # Assert
            self.assertEqual(len(publish_threads), 1)
            self.assertNotEqual(publish_threads[0], event_loop_thread)

    async def test_runner_cancellation_settles_publication_before_cleanup(self):
        """Cancellation waits for in-flight publication before deleting its workspace."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            context = RemixAssetPipelineContext(items=[RemixAssetItem.from_model(temp_path / "chair.fbx")])
            publish_outputs = pipeline_runner_module._publish_outputs
            publication_started = threading.Event()
            release_publication = threading.Event()

            def slow_publish(*args, **kwargs) -> None:
                """Block publication until the test releases it.

                Args:
                    *args: Positional arguments forwarded to the publisher.
                    **kwargs: Keyword arguments forwarded to the publisher.
                """
                publication_started.set()
                release_publication.wait()
                publish_outputs(*args, **kwargs)

            # Act
            with patch.object(pipeline_runner_module, "_publish_outputs", side_effect=slow_publish):
                task = asyncio.create_task(
                    run_remix_asset_pipeline(
                        RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                        context,
                        steps=[_write_many_outputs_step()],
                    )
                )
                publication_started_in_time = await asyncio.to_thread(publication_started.wait, 2)
                task.cancel()
                await asyncio.sleep(0)
                task_was_pending = not task.done()
                release_publication.set()
                with self.assertRaises(asyncio.CancelledError) as error_context:
                    await task

            # Assert
            self.assertTrue(publication_started_in_time)
            self.assertTrue(task_was_pending)
            self.assertIsInstance(error_context.exception, asyncio.CancelledError)
            self.assertTrue((output_dir / "chair.usd").exists())
            self.assertIsNone(context.work_dir)
            self.assertIsNone(context.output_dir)
            self.assertEqual(_remaining_work_dirs(temp_path), [])

    async def test_runner_returns_the_ingestion_context_lease_on_exit(self):
        """The runner owns ingestion cleanup before deleting the temporary workspace."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            context = RemixAssetPipelineContext()
            context._close_ingestion_context = AsyncMock()

            # Act
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                context,
                steps=[],
            )

            # Assert
            context._close_ingestion_context.assert_awaited_once()
            self.assertIsNone(context.work_dir)
            self.assertIsNone(context.output_dir)
            self.assertEqual(_remaining_work_dirs(temp_path), [])

    async def test_runner_publishes_multiple_outputs_and_metadata_from_one_input(self):
        """One item can publish several final files and sidecars from one temporary run."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            item = RemixAssetItem.from_model(temp_path / "chair.fbx")
            context = RemixAssetPipelineContext(items=[item])

            # Act
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                context,
                steps=[_write_many_outputs_step()],
            )

            # Assert
            final_model = output_dir / "chair.usd"
            final_texture = output_dir / "chair_albedo.dds"
            self.assertEqual(item.value, final_model)
            self.assertEqual(item.textures[0].path, final_texture)
            self.assertTrue(final_model.exists())
            self.assertTrue(final_model.with_suffix(".usd.meta").exists())
            self.assertTrue(final_texture.exists())
            self.assertTrue(final_texture.with_suffix(".dds.meta").exists())
            self.assertFalse((output_dir / "intermediate.tmp").exists())
            self.assertIsNone(context.work_dir)
            self.assertIsNone(context.output_dir)
            self.assertEqual(_remaining_work_dirs(temp_path), [])

    async def test_item_progress_runs_stateful_steps_for_every_item(self):
        """Per-item progress cannot let one item's execution state skip the next item."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            items = [
                RemixAssetItem.from_texture(temp_path / "first.png", TextureTypes.DIFFUSE),
                RemixAssetItem.from_texture(temp_path / "second.png", TextureTypes.DIFFUSE),
            ]
            context = RemixAssetPipelineContext(items=items)
            step = _stateful_per_item_output_step()

            # Act
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                context,
                steps=[step],
            )

            # Assert
            self.assertEqual(step.processed_names, ["first.png", "second.png"])
            self.assertEqual({path.name for path in output_dir.glob("*.dds")}, {"first.dds", "second.dds"})

    async def test_runner_validates_complete_batch_before_processing(self):
        """An invalid later item cannot leave earlier caller-owned items mutated."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            first = RemixAssetItem.from_texture(temp_path / "first.png", TextureTypes.DIFFUSE)
            second = RemixAssetItem.from_texture(temp_path / "invalid.png", TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[first, second])
            original_values = [(item.value, item.textures[0].path) for item in context.items]
            completed_items: list[pathlib.Path] = []

            async def on_item_completed(item: RemixAssetItem, _completed: int, _total: int) -> None:
                """Record an item reported complete by the runner.

                Args:
                    item: Item reported complete.
                    _completed: One-based completed count.
                    _total: Total item count.
                """
                completed_items.append(item.source_path)

            # Act
            with self.assertRaises(PipelineValidationError):
                await run_remix_asset_pipeline(
                    RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                    context,
                    steps=[_reject_invalid_batch_step()],
                    on_item_completed=on_item_completed,
                )

            # Assert
            self.assertEqual([(item.value, item.textures[0].path) for item in context.items], original_values)
            self.assertEqual(completed_items, [])
            self.assertEqual(list(output_dir.iterdir()), [])
            self.assertEqual(_remaining_work_dirs(temp_path), [])

    async def test_runner_rolls_back_published_outputs_when_publish_fails(self):
        """A publish failure rolls back final files and item output paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            context = RemixAssetPipelineContext(
                items=[
                    RemixAssetItem.from_texture(temp_path / "first.png", TextureTypes.DIFFUSE),
                    RemixAssetItem.from_texture(temp_path / "second.png", TextureTypes.DIFFUSE),
                ]
            )
            real_move = pipeline_runner_module.shutil.move

            def failing_move(src: str, dst: str) -> str:
                if pathlib.Path(dst).name == "second.dds":
                    raise OSError("disk full")
                return real_move(src, dst)

            with patch.object(pipeline_runner_module.shutil, "move", side_effect=failing_move):
                # Act
                with self.assertRaises(OSError) as error:
                    await run_remix_asset_pipeline(
                        RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                        context,
                        steps=[_write_distinct_outputs_step()],
                    )

            # Assert
            self.assertIn("disk full", str(error.exception))
            self.assertEqual(sorted(output_dir.glob("*.dds")), [])
            self.assertNotEqual(context.items[0].textures[0].path.parent, output_dir)
            self.assertNotEqual(context.items[1].textures[0].path.parent, output_dir)
            self.assertIsNone(context.work_dir)
            self.assertIsNone(context.output_dir)
            self.assertEqual(_remaining_work_dirs(temp_path), [])

    async def test_runner_deduplicates_distinct_outputs_with_same_filename(self):
        """Two source outputs with the same filename are published to unique final names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            context = RemixAssetPipelineContext(
                items=[
                    RemixAssetItem.from_texture(temp_path / "first.png", TextureTypes.DIFFUSE),
                    RemixAssetItem.from_texture(temp_path / "second.png", TextureTypes.DIFFUSE),
                ]
            )

            # Act
            await run_remix_asset_pipeline(
                RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                context,
                steps=[_write_colliding_outputs_step()],
            )

            # Assert
            self.assertEqual(context.items[0].textures[0].path.parent, output_dir)
            self.assertEqual(context.items[1].textures[0].path.parent, output_dir)
            self.assertNotEqual(context.items[0].textures[0].path, context.items[1].textures[0].path)
            self.assertEqual(
                {path.read_bytes() for path in output_dir.glob("albedo*.dds")},
                {b"first", b"second"},
            )
            self.assertIsNone(context.work_dir)
            self.assertIsNone(context.output_dir)
            self.assertEqual(_remaining_work_dirs(temp_path), [])

    async def test_runner_rejects_orphan_metadata_without_primary_output(self):
        """Metadata sidecars are not published when the primary output is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            item = RemixAssetItem.from_texture(temp_path / "albedo.png", TextureTypes.DIFFUSE)
            context = RemixAssetPipelineContext(items=[item])

            # Act
            with self.assertRaises(FileNotFoundError):
                await run_remix_asset_pipeline(
                    RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                    context,
                    steps=[_write_orphan_metadata_step()],
                )

            # Assert
            self.assertFalse((output_dir / "albedo.dds.meta").exists())
            self.assertIsNone(context.work_dir)
            self.assertIsNone(context.output_dir)
            self.assertEqual(_remaining_work_dirs(temp_path), [])

    async def test_runner_rejects_duplicate_publish_destination(self):
        """Distinct workspace outputs cannot publish to one final destination."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Arrange
            temp_path = pathlib.Path(temp_dir)
            output_dir = temp_path / "processed"
            context = _CollidingOutputPathContext(
                items=[
                    RemixAssetItem.from_texture(temp_path / "first.png", TextureTypes.DIFFUSE),
                    RemixAssetItem.from_texture(temp_path / "second.png", TextureTypes.DIFFUSE),
                ]
            )

            # Act
            with self.assertRaises(RuntimeError) as error:
                await run_remix_asset_pipeline(
                    RemixAssetPipelineConfig(output_dir=output_dir, texture_type=TextureTypes.DIFFUSE),
                    context,
                    steps=[_write_colliding_outputs_step()],
                )

            # Assert
            self.assertIn("destination is already published", str(error.exception))
            self.assertIsNone(context.work_dir)
            self.assertIsNone(context.output_dir)
            self.assertEqual(_remaining_work_dirs(temp_path), [])


class _FakeStep(PipelineStep):
    """A single parameterized fake step: behavior comes from test-supplied callables."""

    item_types = (RemixAssetItem,)

    def __init__(self, name, description, run, *, validate=None, should_run=None) -> None:
        super().__init__()
        self._name = name
        self._description = description
        self._run = run
        self._validate = validate
        self._should_run = should_run

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def validate(self, context: RemixAssetPipelineContext) -> list[str]:
        return self._validate(context) if self._validate else []

    def should_run(self, context: RemixAssetPipelineContext) -> bool:
        return self._should_run(self, context) if self._should_run else True

    async def run(self, context: RemixAssetPipelineContext) -> None:
        await self._run(self, context)


async def _write_many_outputs(_step: _FakeStep, context: RemixAssetPipelineContext) -> None:
    model_path = context.reserve_output_path(context.items[0].source_path, suffix=".usd").work_path
    texture_path = context.reserve_output_path(pathlib.Path("/textures/chair_albedo.png"), suffix=".dds").work_path
    model_path.write_bytes(b"usd")
    texture_path.write_bytes(b"dds")
    model_path.with_suffix(".usd.meta").write_text("model metadata")
    texture_path.with_suffix(".dds.meta").write_text("texture metadata")
    (context.work_dir / "intermediate.tmp").write_bytes(b"temporary")

    item = context.items[0]
    item.value = model_path
    item.textures.append(TextureAsset(path=texture_path, texture_type=TextureTypes.DIFFUSE))


def _write_many_outputs_step() -> _FakeStep:
    return _FakeStep("write_many_outputs", "Write several final files from one item", _write_many_outputs)


def _reject_invalid_batch(context: RemixAssetPipelineContext) -> list[str]:
    """Reject a batch containing the invalid test item."""
    return ["invalid input"] if any(item.source_path.name == "invalid.png" for item in context.items) else []


async def _mutate_current_item(_step: _FakeStep, context: RemixAssetPipelineContext) -> None:
    """Mutate the current item to expose processing before complete validation."""
    item = context.items[0]
    item.value = context.work_dir / "mutated.dds"
    item.textures[0].path = item.value


def _reject_invalid_batch_step() -> _FakeStep:
    return _FakeStep(
        "reject_invalid_batch", "Reject invalid batch", _mutate_current_item, validate=_reject_invalid_batch
    )


def _stateful_should_run(step: _FakeStep, context: RemixAssetPipelineContext) -> bool:
    """Run unless this execution-state snapshot already completed the step."""
    state = context.execution_state.get(step.name)
    return state is None or not state.did_run


async def _stateful_per_item_output(step: _FakeStep, context: RemixAssetPipelineContext) -> None:
    item = context.items[0]
    output_path = context.reserve_output_path(item.source_path, suffix=".dds").work_path
    output_path.write_bytes(item.source_path.name.encode())
    item.textures[0].path = output_path
    step.processed_names.append(item.source_path.name)


def _stateful_per_item_output_step() -> _FakeStep:
    """Build a fake step that writes one output per item and refuses to rerun in one state."""
    step = _FakeStep(
        "stateful_per_item_output",
        "Write one output for each item",
        _stateful_per_item_output,
        should_run=_stateful_should_run,
    )
    step.processed_names = []
    return step


async def _write_colliding_outputs(_step: _FakeStep, context: RemixAssetPipelineContext) -> None:
    item = context.items[0]
    source_path = pathlib.Path(f"/{item.source_path.stem}/albedo.png")
    output_path = context.reserve_output_path(source_path, suffix=".dds").work_path
    output_path.write_bytes(item.source_path.stem.encode())
    item.textures[0].path = output_path


def _write_colliding_outputs_step() -> _FakeStep:
    return _FakeStep("write_colliding_outputs", "Write two outputs with the same filename", _write_colliding_outputs)


async def _write_distinct_outputs(_step: _FakeStep, context: RemixAssetPipelineContext) -> None:
    item = context.items[0]
    output_path = context.reserve_output_path(item.source_path, suffix=".dds").work_path
    output_path.write_bytes(item.source_path.stem.encode())
    item.textures[0].path = output_path


def _write_distinct_outputs_step() -> _FakeStep:
    return _FakeStep("write_distinct_outputs", "Write two outputs with distinct filenames", _write_distinct_outputs)


async def _write_orphan_metadata(_step: _FakeStep, context: RemixAssetPipelineContext) -> None:
    texture_path = context.reserve_output_path(pathlib.Path("/textures/albedo.png"), suffix=".dds").work_path
    texture_path.with_suffix(".dds.meta").write_text("orphan metadata")
    context.items[0].textures[0].path = texture_path


def _write_orphan_metadata_step() -> _FakeStep:
    return _FakeStep("write_orphan_metadata", "Write metadata without the primary file", _write_orphan_metadata)


class _CollidingOutputPathContext(RemixAssetPipelineContext):
    def get_output_path(
        self,
        work_path: pathlib.Path,
        *,
        source_path: pathlib.Path | None = None,
    ) -> pathlib.Path:
        return self.output_dir / "same.dds"


def _remaining_work_dirs(parent: pathlib.Path) -> list[pathlib.Path]:
    return sorted(path for path in parent.iterdir() if path.name.startswith("remix_asset_pipeline_"))
