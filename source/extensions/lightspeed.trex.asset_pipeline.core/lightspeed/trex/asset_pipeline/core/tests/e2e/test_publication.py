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
from unittest import mock

import omni.client
import omni.kit.test

import lightspeed.trex.asset_pipeline.core.publication as publication_module


class TestAssetPublicationE2E(omni.kit.test.AsyncTestCase):
    """Exercise remote publication transactions through the real client boundary."""

    async def test_remote_batch_copy_failure_preserves_previous_directory(self):
        """A real client failure during staging leaves the complete previous batch untouched."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            local_dir = temp_path / "local"
            remote_dir = temp_path / "remote"
            local_dir.mkdir()
            remote_dir.mkdir()
            previous_file = remote_dir / "existing.dds"
            previous_file.write_bytes(b"previous")
            first_source = local_dir / "first.dds"
            first_source.write_bytes(b"first")
            missing_source = local_dir / "missing.dds"
            remote_url = omni.client.make_file_url(str(remote_dir))

            # Stage one real file followed by a missing file so the batch fails before its atomic commit.
            with self.assertRaises(RuntimeError) as error:
                await publication_module._publish_remote_batch([first_source, missing_source], local_dir, remote_url)

            # Rollback preserves the previous directory and removes every staged transaction path.
            self.assertIn("stage processed asset", str(error.exception))
            self.assertEqual(previous_file.read_bytes(), b"previous")
            self.assertFalse((remote_dir / "first.dds").exists())
            self.assertEqual(list(temp_path.glob("remote.asset_pipeline_*")), [])

    async def test_remote_batch_copy_failure_leaves_no_new_directory(self):
        """A failed real-client batch never exposes a partially created final directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            local_dir = temp_path / "local"
            local_dir.mkdir()
            first_source = local_dir / "first.dds"
            first_source.write_bytes(b"first")
            missing_source = local_dir / "missing.dds"
            remote_dir = temp_path / "remote"
            remote_url = omni.client.make_file_url(str(remote_dir))

            # Attempt the same incomplete batch when no previous destination exists.
            with self.assertRaises(RuntimeError):
                await publication_module._publish_remote_batch([first_source, missing_source], local_dir, remote_url)

            # A failed initial publication leaves neither a visible destination nor staging debris.
            self.assertFalse(remote_dir.exists())
            self.assertEqual(list(temp_path.glob("remote.asset_pipeline_*")), [])

    async def test_remote_commit_and_staging_cleanup_failure_restores_previous_directory(self):
        """A cleanup failure cannot prevent backup restoration after the final path moves."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            local_dir = temp_path / "local"
            remote_dir = temp_path / "remote"
            local_dir.mkdir()
            remote_dir.mkdir()
            previous_file = remote_dir / "existing.dds"
            previous_file.write_bytes(b"previous")
            new_source = local_dir / "new.dds"
            new_source.write_bytes(b"new")
            remote_url = omni.client.make_file_url(str(remote_dir))
            real_move_async = publication_module.move_async
            real_delete_remote_path = publication_module._delete_remote_path

            async def fail_commit(source_url, destination_url, behavior):
                """Fail only the staging-to-final swap after the final directory is backed up.

                Args:
                    source_url: Client source URL.
                    destination_url: Client destination URL.
                    behavior: Client collision behavior.

                Returns:
                    Real client result except for the injected commit failure.
                """
                if source_url.startswith(f"{remote_url}.asset_pipeline_staging_") and destination_url == remote_url:
                    return omni.client.Result.ERROR, False
                return await real_move_async(source_url, destination_url, behavior)

            async def fail_staging_cleanup(url: str, *, required: bool) -> None:
                """Fail only rollback cleanup of the staged new batch.

                Args:
                    url: Remote transaction URL.
                    required: Whether cleanup failure must fail the rollback.

                Raises:
                    RuntimeError: When rollback tries to remove the staging directory.
                """
                if url.startswith(f"{remote_url}.asset_pipeline_staging_"):
                    raise RuntimeError("injected staging cleanup failure")
                await real_delete_remote_path(url, required=required)

            with (
                mock.patch.object(publication_module, "move_async", side_effect=fail_commit),
                mock.patch.object(publication_module, "_delete_remote_path", side_effect=fail_staging_cleanup),
                self.assertRaises(RuntimeError) as error,
            ):
                # Fail the final swap and its staging cleanup after the previous directory has moved to backup.
                await publication_module._publish_remote_batch([new_source], local_dir, remote_url)

            # Restoration still returns the previous directory instead of exposing the uncommitted batch.
            self.assertIn("injected staging cleanup failure", str(error.exception))
            self.assertEqual(previous_file.read_bytes(), b"previous")
            self.assertFalse((remote_dir / "new.dds").exists())

    async def test_cancellation_after_backup_move_restores_previous_directory(self):
        """Cancellation after the backup move restores the previous output and removes transaction paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            local_dir = temp_path / "local"
            remote_dir = temp_path / "remote"
            local_dir.mkdir()
            remote_dir.mkdir()
            previous_file = remote_dir / "existing.dds"
            previous_file.write_bytes(b"previous")
            new_source = local_dir / "new.dds"
            new_source.write_bytes(b"new")
            remote_url = omni.client.make_file_url(str(remote_dir))
            real_move_async = publication_module.move_async
            backup_moved = asyncio.Event()
            release_backup_move = asyncio.Event()

            async def pause_after_backup_move(source_url, destination_url, behavior):
                """Pause the settled backup operation after the real move succeeds.

                Args:
                    source_url: Client source URL.
                    destination_url: Client destination URL.
                    behavior: Client collision behavior.

                Returns:
                    Real client move result.
                """
                result = await real_move_async(source_url, destination_url, behavior)
                if source_url == remote_url and destination_url.startswith(f"{remote_url}.asset_pipeline_backup_"):
                    backup_moved.set()
                    await release_backup_move.wait()
                return result

            with mock.patch.object(publication_module, "move_async", side_effect=pause_after_backup_move):
                # Pause immediately after backup creation, then cancel the in-flight publication.
                publication_task = asyncio.create_task(
                    publication_module._publish_remote_batch([new_source], local_dir, remote_url)
                )
                await backup_moved.wait()

                publication_task.cancel()
                release_backup_move.set()
                with self.assertRaises(asyncio.CancelledError):
                    await publication_task

            # Cancellation settles rollback before propagating and removes every transaction directory.
            self.assertEqual(previous_file.read_bytes(), b"previous")
            self.assertFalse((remote_dir / "new.dds").exists())
            self.assertEqual(list(temp_path.glob("remote.asset_pipeline_*")), [])

    async def test_cancellation_after_first_commit_removes_new_directory(self):
        """Cancellation after a first atomic commit leaves no unowned remote output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            local_dir = temp_path / "local"
            local_dir.mkdir()
            source = local_dir / "new.dds"
            source.write_bytes(b"new")
            remote_dir = temp_path / "remote"
            remote_url = omni.client.make_file_url(str(remote_dir))
            real_move_async = publication_module.move_async
            final_moved = asyncio.Event()
            release_final_move = asyncio.Event()

            async def pause_after_final_move(source_url, destination_url, behavior):
                """Pause after the real first staging-to-final move succeeds.

                Args:
                    source_url: Client source URL.
                    destination_url: Client destination URL.
                    behavior: Client collision behavior.

                Returns:
                    Real client move result.
                """
                result = await real_move_async(source_url, destination_url, behavior)
                if source_url.startswith(f"{remote_url}.asset_pipeline_staging_") and destination_url == remote_url:
                    final_moved.set()
                    await release_final_move.wait()
                return result

            with mock.patch.object(publication_module, "move_async", side_effect=pause_after_final_move):
                # Commit the first real batch remotely, then cancel before the settled result reaches the caller.
                publication_task = asyncio.create_task(
                    publication_module._publish_remote_batch([source], local_dir, remote_url)
                )
                await final_moved.wait()
                publication_task.cancel()
                release_final_move.set()
                with self.assertRaises(asyncio.CancelledError):
                    await publication_task

            # Cancellation rolls the committed first batch back and leaves no transaction directory.
            self.assertFalse(remote_dir.exists())
            self.assertEqual(list(temp_path.glob("remote.asset_pipeline_*")), [])

    async def test_cancellation_during_competing_first_commit_preserves_other_destination(self):
        """Cancellation cannot remove a destination created by a competing publisher."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            local_dir = temp_path / "local"
            local_dir.mkdir()
            source = local_dir / "new.dds"
            source.write_bytes(b"new")
            remote_dir = temp_path / "remote"
            remote_url = omni.client.make_file_url(str(remote_dir))
            real_move_async = publication_module.move_async
            final_move_finished = asyncio.Event()
            release_final_move = asyncio.Event()

            async def create_competing_destination(source_url, destination_url, behavior):
                """Create a competing destination before settling the final move.

                Args:
                    source_url: Client source URL.
                    destination_url: Client destination URL.
                    behavior: Client collision behavior.

                Returns:
                    Real client move result.
                """
                if source_url.startswith(f"{remote_url}.asset_pipeline_staging_") and destination_url == remote_url:
                    remote_dir.mkdir()
                    (remote_dir / "other.dds").write_bytes(b"other")
                    result = await real_move_async(source_url, destination_url, behavior)
                    final_move_finished.set()
                    await release_final_move.wait()
                    return result
                return await real_move_async(source_url, destination_url, behavior)

            with mock.patch.object(publication_module, "move_async", side_effect=create_competing_destination):
                # Let another publisher win the destination race, then cancel while this failed move settles.
                publication_task = asyncio.create_task(
                    publication_module._publish_remote_batch([source], local_dir, remote_url)
                )
                await final_move_finished.wait()
                publication_task.cancel()
                release_final_move.set()
                with self.assertRaises(asyncio.CancelledError):
                    await publication_task

            # Rollback removes only this transaction and preserves the competing publisher's directory.
            self.assertEqual((remote_dir / "other.dds").read_bytes(), b"other")
            self.assertFalse((remote_dir / "new.dds").exists())
            self.assertEqual(list(temp_path.glob("remote.asset_pipeline_*")), [])

    async def test_competing_replacement_preserves_other_destination(self):
        """Rollback cannot replace a destination created after this transaction makes its backup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            local_dir = temp_path / "local"
            remote_dir = temp_path / "remote"
            local_dir.mkdir()
            remote_dir.mkdir()
            (remote_dir / "previous.dds").write_bytes(b"previous")
            source = local_dir / "new.dds"
            source.write_bytes(b"new")
            remote_url = omni.client.make_file_url(str(remote_dir))
            real_move_async = publication_module.move_async

            async def create_competing_destination(source_url, destination_url, behavior):
                """Create a competing destination after the previous output moves to backup.

                Args:
                    source_url: Client source URL.
                    destination_url: Client destination URL.
                    behavior: Client collision behavior.

                Returns:
                    Real client move result.
                """
                if source_url.startswith(f"{remote_url}.asset_pipeline_staging_") and destination_url == remote_url:
                    remote_dir.mkdir()
                    (remote_dir / "other.dds").write_bytes(b"other")
                return await real_move_async(source_url, destination_url, behavior)

            with (
                mock.patch.object(publication_module, "move_async", side_effect=create_competing_destination),
                self.assertRaises(RuntimeError),
            ):
                # Let another publisher replace the destination after this transaction retains its previous version.
                await publication_module._publish_remote_batch([source], local_dir, remote_url)

            # Rollback discards only its own backup and staging data, leaving the competing destination untouched.
            self.assertEqual((remote_dir / "other.dds").read_bytes(), b"other")
            self.assertFalse((remote_dir / "previous.dds").exists())
            self.assertFalse((remote_dir / "new.dds").exists())
            self.assertEqual(list(temp_path.glob("remote.asset_pipeline_*")), [])

    async def test_remote_batch_commits_new_files_without_removing_existing_files(self):
        """A successful real-client batch atomically overlays the complete previous directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            local_dir = temp_path / "local"
            remote_dir = temp_path / "remote"
            local_dir.mkdir()
            remote_dir.mkdir()
            (remote_dir / "existing.dds").write_bytes(b"existing")
            new_source = local_dir / "new.dds"
            new_source.write_bytes(b"new")
            remote_url = omni.client.make_file_url(str(remote_dir))

            # Publish a complete new batch over a destination that already contains an asset.
            await publication_module._publish_remote_batch([new_source], local_dir, remote_url)

            # Atomic overlay retains existing assets, adds the new asset, and removes transaction paths.
            self.assertEqual((remote_dir / "existing.dds").read_bytes(), b"existing")
            self.assertEqual((remote_dir / "new.dds").read_bytes(), b"new")
            self.assertEqual(list(temp_path.glob("remote.asset_pipeline_*")), [])

    async def test_remote_batch_preserves_local_relative_directories(self):
        """A remote publication keeps the local output hierarchy intact."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            local_dir = temp_path / "local"
            source = local_dir / "textures" / "chair" / "albedo.diffuse.dds"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"processed")
            remote_dir = temp_path / "remote"
            remote_url = omni.client.make_file_url(str(remote_dir))

            # Publish a processed texture nested below the local output root.
            await publication_module._publish_remote_batch([source], local_dir, remote_url)

            # The remote output has the same source-relative hierarchy and no transaction debris.
            published = remote_dir / "textures" / "chair" / "albedo.diffuse.dds"
            self.assertEqual(published.read_bytes(), b"processed")
            self.assertEqual(list(temp_path.glob("remote.asset_pipeline_*")), [])
