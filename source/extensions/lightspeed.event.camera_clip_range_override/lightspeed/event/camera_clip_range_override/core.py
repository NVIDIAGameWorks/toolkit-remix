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

__all__ = ["EventCameraClipRangeOverride"]

import asyncio

import carb
import carb.settings
import omni.kit.app
import omni.usd
from lightspeed.events_manager import ILSSEvent as _ILSSEvent
from lightspeed.trex.project_settings.core import (
    CAMERA_CLIPPING_OVERRIDE_PATH,
    get_camera_clipping_override,
)
from pxr import Gf, Sdf, Tf, Usd, UsdGeom

_CONTEXT = "/exts/lightspeed.event.camera_clip_range_override/context"

# Pre-constructed once at module load. `_on_settings_changed` fires on every
# Usd.Notice.ObjectsChanged on the stage (not only on our settings prim
# changes), so re-allocating an Sdf.Path here for every notice would be
# wasted work on busy stages.
_OVERRIDE_SDF_PATH = Sdf.Path(CAMERA_CLIPPING_OVERRIDE_PATH)

# When the user pre-edits a camera's clippingRange (e.g., via the property
# panel) and that edit happens to land on the session layer, enabling the
# override would overwrite their value. To preserve their edit, we cache
# the pre-override value per prim on first enable, and restore it on disable.
# The cache is in-memory only; the session layer itself doesn't persist
# across app restarts, so neither needs the cache.


class EventCameraClipRangeOverride(_ILSSEvent):
    """Listens for stage events and applies the project's CameraClippingOverride
    to all `UsdGeomCamera` prims on the session layer.
    """

    def __init__(self):
        super().__init__()
        settings = carb.settings.get_settings()
        self._context_name: str = settings.get(_CONTEXT) or ""
        self._context = omni.usd.get_context(self._context_name)
        self._stage_event_sub = None
        self._settings_notice_listener = None
        self._restoration_cache: dict[Sdf.Path, tuple[float, float] | None] = {}
        # Coalesces bursts of HIERARCHY_CHANGED events into a single
        # _apply_override call on the next frame. Without this, a
        # capture/asset load can fire dozens of events in close succession
        # and each one triggers a full stage traversal.
        self._apply_pending = False

    @property
    def name(self) -> str:
        """Name of the event."""
        return "CameraClipRangeOverride"

    def _install(self):
        """Subscribe to stage events. If a stage is already open, apply immediately."""
        self._uninstall()
        events = self._context.get_stage_event_stream()
        self._stage_event_sub = events.create_subscription_to_pop(
            self._on_stage_event, name="Camera Clip Range Override"
        )
        stage = self._context.get_stage()
        if stage:
            self._on_opened(stage)

    def _uninstall(self):
        """Drop all subscriptions and clear cached state."""
        self._teardown_settings_listener()
        self._stage_event_sub = None
        self._restoration_cache.clear()
        # Any in-flight deferred apply will see _stage_event_sub is None
        # on wake and bail; resetting the flag keeps the next install
        # from short-circuiting the first schedule call.
        self._apply_pending = False

    def _on_stage_event(self, event):
        stage = self._context.get_stage()
        if event.type == int(omni.usd.StageEventType.OPENED):
            if stage:
                self._on_opened(stage)
        elif event.type == int(omni.usd.StageEventType.HIERARCHY_CHANGED):
            if stage:
                self._schedule_apply()
        elif event.type == int(omni.usd.StageEventType.CLOSED):
            self._teardown_settings_listener()
            # Cache entries are keyed by Sdf.Path only, so they would leak
            # across stages if a new project happens to have a camera at the
            # same path. Drop the cache when the current stage closes.
            self._restoration_cache.clear()

    def _schedule_apply(self):
        """Queue a single deferred _apply_override pass on the next frame.

        Bursts of HIERARCHY_CHANGED events (project load, capture swap,
        asset mass-import) collapse into a single traversal rather than
        one traversal per event.
        """
        if self._apply_pending:
            return
        self._apply_pending = True
        asyncio.ensure_future(self._deferred_apply())

    @omni.usd.handle_exception
    async def _deferred_apply(self):
        """Wait until the next frame, then apply the override once.

        Re-checks state at wake time because the stage may have closed,
        the event may have been uninstalled, or a different stage may
        have opened (which triggers its own synchronous apply via
        _on_opened, making this deferred pass redundant) while the
        coroutine was sleeping.
        """
        await omni.kit.app.get_app().next_update_async()
        self._apply_pending = False
        if self._stage_event_sub is None:
            return
        stage = self._context.get_stage()
        if stage is None:
            return
        self._apply_override(stage)

    def _on_opened(self, stage: Usd.Stage):
        self._setup_settings_listener(stage)
        self._apply_override(stage)

    def _setup_settings_listener(self, stage: Usd.Stage):
        self._teardown_settings_listener()
        self._settings_notice_listener = Tf.Notice.Register(
            Usd.Notice.ObjectsChanged,
            self._on_settings_changed,
            stage,
        )

    def _teardown_settings_listener(self):
        if self._settings_notice_listener:
            self._settings_notice_listener.Revoke()
            self._settings_notice_listener = None

    def _on_settings_changed(self, notice, stage):
        if stage != self._context.get_stage():
            return
        # Sdf.Path.HasPrefix respects USD path component boundaries, unlike
        # string startswith which would also match sibling prims that share
        # a name prefix (e.g., /ProjectSettings/Viewport/CameraClippingOverrideLegacy).
        for path_list_getter in (notice.GetChangedInfoOnlyPaths, notice.GetResyncedPaths):
            for path in path_list_getter():
                if path.HasPrefix(_OVERRIDE_SDF_PATH):
                    self._apply_override(stage)
                    return

    def _apply_override(self, stage: Usd.Stage):
        override = get_camera_clipping_override(stage)
        # Fast path: when the override is off and we have nothing cached to
        # restore, traversing every prim is pure waste. HIERARCHY_CHANGED
        # fires frequently during captures and asset loads, so this matters.
        if not override.enabled and not self._restoration_cache:
            return
        session_layer = stage.GetSessionLayer()
        with Sdf.ChangeBlock():
            for prim in stage.TraverseAll():
                if not prim.IsA(UsdGeom.Camera):
                    continue
                prim_path = prim.GetPath()
                session_prim_spec = session_layer.GetPrimAtPath(prim_path)
                if override.enabled:
                    # On first enable for this prim, cache whatever pre-existing
                    # session-layer value exists so we can restore it on disable.
                    # Subsequent re-applies (user changing near/far while the
                    # override is on) must NOT update the cache; we always
                    # want the original.
                    if prim_path not in self._restoration_cache:
                        pre_existing = (
                            session_prim_spec.attributes.get("clippingRange") if session_prim_spec is not None else None
                        )
                        if pre_existing is not None and pre_existing.HasInfo("default"):
                            existing_default = pre_existing.default
                            self._restoration_cache[prim_path] = (
                                float(existing_default[0]),
                                float(existing_default[1]),
                            )
                        else:
                            self._restoration_cache[prim_path] = None
                    if session_prim_spec is None:
                        session_prim_spec = Sdf.CreatePrimInLayer(session_layer, prim_path)
                    attr_spec = session_prim_spec.attributes.get("clippingRange")
                    if attr_spec is None:
                        attr_spec = Sdf.AttributeSpec(session_prim_spec, "clippingRange", Sdf.ValueTypeNames.Float2)
                    attr_spec.default = Gf.Vec2f(float(override.near_clip), float(override.far_clip))
                elif prim_path in self._restoration_cache:
                    # Disable: restore the cached pre-existing value if any,
                    # or remove the spec entirely if no value was cached.
                    previous = self._restoration_cache.pop(prim_path)
                    if previous is None:
                        if session_prim_spec is not None and "clippingRange" in session_prim_spec.properties:
                            del session_prim_spec.properties["clippingRange"]
                    else:
                        if session_prim_spec is None:
                            session_prim_spec = Sdf.CreatePrimInLayer(session_layer, prim_path)
                        attr_spec = session_prim_spec.attributes.get("clippingRange")
                        if attr_spec is None:
                            attr_spec = Sdf.AttributeSpec(
                                session_prim_spec,
                                "clippingRange",
                                Sdf.ValueTypeNames.Float2,
                            )
                        attr_spec.default = Gf.Vec2f(previous[0], previous[1])
        # Drop any cache entries left over for prims that no longer exist
        # on the stage (their cameras were removed while the override was
        # active, so TraverseAll above didn't surface them and the
        # restoration loop never popped their entries). Leaving them would
        # be correctness-harmless but would defeat the fast-path check on
        # subsequent HIERARCHY_CHANGED events.
        if not override.enabled:
            self._restoration_cache.clear()
