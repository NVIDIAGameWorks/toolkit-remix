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

from contextlib import contextmanager
from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.utils.common import interactive_usd_notices as _interactive_usd_notices
from omni.flux.utils.common.interactive_usd_notices import InteractiveUsdNoticeService
from pxr import Sdf


class _FakeNotice:
    def __init__(self, changed_info_only_paths=(), resynced_paths=(), changed_fields_by_path=None):
        self._changed_info_only_paths = tuple(changed_info_only_paths)
        self._resynced_paths = tuple(resynced_paths)
        self._changed_fields_by_path = changed_fields_by_path or {}

    def get_changed_info_only_paths(self):
        return self._changed_info_only_paths

    def get_resynced_paths(self):
        return self._resynced_paths

    def get_changed_fields(self, path):
        return self._changed_fields_by_path.get(path, ())

    GetChangedInfoOnlyPaths = get_changed_info_only_paths
    GetResyncedPaths = get_resynced_paths
    GetChangedFields = get_changed_fields


class _FakeLayer:
    def __init__(self, identifier):
        self.identifier = identifier


class _FakeStage:
    def __init__(self, root_identifier="anon:root", session_identifier="anon:session"):
        self._root_layer = _FakeLayer(root_identifier)
        self._session_layer = _FakeLayer(session_identifier)

    def close(self):
        self._root_layer = None
        self._session_layer = None

    def get_root_layer(self):
        return self._root_layer

    def get_session_layer(self):
        return self._session_layer

    GetRootLayer = get_root_layer
    GetSessionLayer = get_session_layer


def _make_stage():
    stage = Mock()
    stage.GetRootLayer.return_value = Mock(identifier="anon:root")
    stage.GetSessionLayer.return_value = Mock(identifier="anon:session")
    return stage


@contextmanager
def _patch_service_dependencies(listener=None, *, register_side_effect=None):
    if listener is None and register_side_effect is None:
        listener = Mock()
    register_options = (
        {"side_effect": register_side_effect} if register_side_effect is not None else {"return_value": listener}
    )
    with patch.object(_interactive_usd_notices.Tf.Notice, "Register", **register_options) as register_mock:
        yield register_mock


class TestInteractiveUsdNoticeService(omni.kit.test.AsyncTestCase):
    async def test_end_interaction_last_token_flushes_merged_notice_once(self):
        # Arrange
        stage = _make_stage()
        callback = Mock()
        listener = Mock()
        path = Sdf.Path("/Root/Cube.xformOp:translate")
        first_notice = _FakeNotice(
            changed_info_only_paths=(path,),
            changed_fields_by_path={path: ("default",)},
        )
        second_notice = _FakeNotice(
            changed_info_only_paths=(path,),
            changed_fields_by_path={path: ("timeSamples",)},
        )
        with _patch_service_dependencies(listener):
            service = InteractiveUsdNoticeService()
            service.register_objects_changed_listener(stage, callback)
            first_token = service.begin_interaction(stage)
            second_token = service.begin_interaction(stage)
            service._on_objects_changed(first_notice, stage)
            service._on_objects_changed(second_notice, stage)
            service.end_interaction(first_token)

            # Act
            service.end_interaction(second_token)

        # Assert
        callback.assert_called_once()
        flushed_notice, flushed_stage = callback.call_args.args
        self.assertIs(flushed_stage, stage)
        self.assertEqual((path,), flushed_notice.GetChangedInfoOnlyPaths())
        self.assertEqual(("default", "timeSamples"), flushed_notice.GetChangedFields(path))

    async def test_active_interaction_only_defers_matching_stage(self):
        # Arrange
        active_stage = _FakeStage("anon:active-root", "anon:active-session")
        other_stage = _FakeStage("anon:other-root", "anon:other-session")
        active_callback = Mock()
        other_callback = Mock()
        active_path = Sdf.Path("/Active/Cube.xformOp:translate")
        other_path = Sdf.Path("/Other/Cube.xformOp:translate")
        active_notice = _FakeNotice(changed_info_only_paths=(active_path,))
        other_notice = _FakeNotice(changed_info_only_paths=(other_path,))
        with _patch_service_dependencies(register_side_effect=(Mock(), Mock())):
            service = InteractiveUsdNoticeService()
            service.register_objects_changed_listener(active_stage, active_callback)
            service.register_objects_changed_listener(other_stage, other_callback)
            token = service.begin_interaction(active_stage)

            # Act
            service._on_objects_changed(other_notice, other_stage)
            service._on_objects_changed(active_notice, active_stage)

            # Assert
            other_callback.assert_called_once_with(other_notice, other_stage)
            active_callback.assert_not_called()

            # Act
            service.end_interaction(token)

        # Assert
        active_callback.assert_called_once()
        flushed_notice, flushed_stage = active_callback.call_args.args
        self.assertEqual((active_path,), flushed_notice.GetChangedInfoOnlyPaths())
        self.assertIs(flushed_stage, active_stage)

    async def test_end_interaction_notifies_interaction_end_listeners(self):
        # Arrange
        stage = _make_stage()
        callback = Mock()
        listener = Mock()
        with _patch_service_dependencies(listener):
            service = InteractiveUsdNoticeService()
            service.register_interaction_end_listener(callback)
            token = service.begin_interaction(stage)

            # Act
            service.end_interaction(token)

        # Assert
        callback.assert_called_once_with(stage)

    async def test_register_objects_changed_listener_without_stage_returns_noop_subscription(self):
        # Arrange
        callback = Mock()
        with _patch_service_dependencies() as register_mock:
            service = InteractiveUsdNoticeService()
            subscription = service.register_objects_changed_listener(
                None,
                callback,
            )

            # Act
            subscription.Revoke()

        # Assert
        register_mock.assert_not_called()
        callback.assert_not_called()
        self.assertFalse(service._stage_listeners)

    async def test_interaction_matches_listener_state_by_stage_identity_not_python_wrapper(self):
        # Arrange
        register_stage = _FakeStage("anon:root", "anon:session")
        begin_stage = _FakeStage("anon:root", "anon:session")
        sender_stage = _FakeStage("anon:root", "anon:session")
        callback = Mock()
        listener = Mock()
        path = Sdf.Path("/Root/Cube.xformOp:translate")
        notice = _FakeNotice(changed_info_only_paths=(path,))
        with _patch_service_dependencies(listener):
            service = InteractiveUsdNoticeService()
            service.register_objects_changed_listener(
                register_stage,
                callback,
            )
            token = service.begin_interaction(begin_stage)

            # Act
            service._on_objects_changed(notice, sender_stage)
            service.end_interaction(token)

        # Assert
        callback.assert_called_once()
        flushed_notice, flushed_stage = callback.call_args.args
        self.assertEqual((path,), flushed_notice.GetChangedInfoOnlyPaths())
        self.assertIs(flushed_stage, register_stage)

    async def test_same_stage_key_rebinds_backend_notice_listener_for_new_stage_object(self):
        # Arrange
        old_stage = _FakeStage("anon:root", "anon:session")
        new_stage = _FakeStage("anon:root", "anon:session")
        old_backend_listener = Mock()
        new_backend_listener = Mock()

        with _patch_service_dependencies(
            register_side_effect=(old_backend_listener, new_backend_listener)
        ) as register_mock:
            service = InteractiveUsdNoticeService()
            service.register_objects_changed_listener(
                old_stage,
                Mock(),
            )

            # Act
            service.begin_interaction(new_stage)

        # Assert
        self.assertEqual(2, register_mock.call_count)
        old_backend_listener.Revoke.assert_called_once_with()
        self.assertIs(service._stage_listeners[("anon:root", "anon:session")][0], new_stage)
        self.assertIs(service._stage_listeners[("anon:root", "anon:session")][1], new_backend_listener)

    async def test_register_prunes_stale_stage_listener_records(self):
        # Arrange
        stale_stage = _FakeStage("anon:stale-root", "anon:stale-session")
        fresh_stage = _FakeStage("anon:fresh-root", "anon:fresh-session")
        stale_backend_listener = Mock()
        fresh_backend_listener = Mock()
        path = Sdf.Path("/Root/Cube.xformOp:translate")
        notice = _FakeNotice(changed_info_only_paths=(path,))

        with _patch_service_dependencies(
            register_side_effect=(stale_backend_listener, fresh_backend_listener)
        ) as register_mock:
            service = InteractiveUsdNoticeService()
            service.register_objects_changed_listener(stale_stage, Mock())
            token = service.begin_interaction(stale_stage)
            service._on_objects_changed(notice, stale_stage)
            stale_stage.close()

            # Act
            service.register_objects_changed_listener(fresh_stage, Mock())

        # Assert
        self.assertEqual(2, register_mock.call_count)
        stale_backend_listener.Revoke.assert_called_once_with()
        self.assertEqual(1, len(service._listeners))
        self.assertNotIn(token.stage_key, service._stage_listeners)
        self.assertNotIn(token.stage_key, service._active_tokens)
        self.assertFalse(service._pending_notices)
        self.assertIs(service._stage_listeners[("anon:fresh-root", "anon:fresh-session")][0], fresh_stage)
        self.assertIs(service._stage_listeners[("anon:fresh-root", "anon:fresh-session")][1], fresh_backend_listener)
