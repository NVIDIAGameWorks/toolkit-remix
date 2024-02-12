"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Callable, Optional

import carb.input
from lightspeed.trex.contexts import get_instance as _get_trex_context_manager
from omni.flux.utils.common import Event, EventSubscription
from omni.kit.hotkeys.core import KeyCombination

from .hotkey import AppHotkey

_global_instance: HotkeyManager | None = None

if TYPE_CHECKING:
    from lightspeed.trex.contexts.setup import Contexts as _TrexContexts


def get_global_hotkey_manager() -> "HotkeyManager":
    if not _global_instance:
        raise RuntimeError("GlobalHotkeys instance has not been initialized!")
    return _global_instance


def create_global_hotkey_manager():
    global _global_instance
    if _global_instance:
        raise RuntimeError("GlobalHotkeys instance already exists!")
    _global_instance = HotkeyManager()


def destroy_global_hotkey_manager():
    global _global_instance
    get_global_hotkey_manager().destroy()
    _global_instance = None


class HotkeyEvent(enum.Enum):
    """Supported hotkey triggers"""


class TrexHotkeyEvent(HotkeyEvent):
    """Trex Specific HotkeyEvents"""

    # undo
    CTRL_Z = KeyCombination(carb.input.KeyboardInput.Z, modifiers=carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
    # redo
    CTRL_Y = KeyCombination(carb.input.KeyboardInput.Y, modifiers=carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
    # save
    CTRL_S = KeyCombination(carb.input.KeyboardInput.S, modifiers=carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL)
    # save as
    CTRL_SHIFT_S = KeyCombination(
        carb.input.KeyboardInput.S,
        modifiers=(carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL | carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT),
    )
    # frame selection as in a viewport
    F = KeyCombination(carb.input.KeyboardInput.F)


class HotkeyManager:
    """
    Manager to define and subscribe to app hotkeys.

    Use this to register common hotkeys that may be supported by more than
    one extension or process and may depend on a specific app context.

    Since these use events/subscriptions multiple actions can be attached to
    one hotkey event.
    """

    def __init__(self):
        # keep references to objects
        self._events = {}  # type: dict[(HotkeyEvent, _TrexContexts | None), Event]
        self._hotkeys = []  # type: list[AppHotkey]
        self._hotkey_events = set()  # type: set[HotkeyEvent]
        self._trex_context_manager = _get_trex_context_manager()

    def define_hotkey_event(self, hotkey_event: HotkeyEvent, hotkey_display_name, hotkey_description=None):
        """
        Declare a supported hotkey.

        Args:
            hotkey_event: hotkey trigger to support
            hotkey_display_name: Display name for hotkey action
            hotkey_description: Description for hotkey action
        """
        if hotkey_event in self._hotkey_events:
            raise ValueError(f"Existing event registered for {hotkey_event}")
        hotkey = AppHotkey(
            f"trex::{hotkey_display_name}",
            hotkey_event.value,
            lambda: self.__trigger(hotkey_event),
            display_name=hotkey_display_name,
            description=hotkey_description,
        )
        self._hotkeys.append(hotkey)
        self._hotkey_events.add(hotkey_event)

    def __trigger(self, hotkey_event):
        # Note: We don't use `omni.kit.hotkeys.context.HotkeyContext` for the filtering
        # because that could interfere with any other extensions using `omni.kit.hotkeys`
        # as there can only be one context. It also requires you to declare the context on
        # hotkey declaration instead of subscription time, leading to repetitive declarations.

        context = self._trex_context_manager.get_current_context()
        for context_ in (context, None):
            event = self._events.get((hotkey_event, context_))
            # note: also check size in case all subscriptions have been deleted
            if event and len(event) != 0:
                event()
                break

    def subscribe_hotkey_event(
        self,
        hotkey_event,
        fn,
        context: Optional["_TrexContexts"] = None,
        enable_fn: Optional[Callable[[], bool]] = None,
    ) -> EventSubscription:
        """
        Return the subscription object that will automatically unsubscribe when destroyed.

        Args:
            hotkey_event: User action triggered
            fn: Callable to be called on hotkey event
            context: Optionally provide the app context where this hotkey will be active.
            enable_fn: Optionally provide an additional callback to filter events. If
                the callback returns True then the fn will be called.
        """
        event_key = (hotkey_event, context)
        event = self._events.get(event_key)
        if not event:
            event = Event()
            self._events[event_key] = event

        def filter_context_fn():
            if enable_fn is not None and not enable_fn():
                return
            fn()

        return EventSubscription(event, filter_context_fn)

    def destroy(self):
        """Cleanup and de-register all hotkey hooks owned by this manager"""
        for hotkey in self._hotkeys:
            hotkey.destroy()
        self._events = {}
        self._hotkey_events = set()
        self._trex_context_manager = None


def register_global_hotkeys():
    """
    Define hotkeys that are common for the remix app.

    Any extension that wants to make hotkey actions/effects shareable with another
    extension can follow this same pattern.
    """
    global_hotkeys = get_global_hotkey_manager()
    for event in TrexHotkeyEvent:
        global_hotkeys.define_hotkey_event(event, f"Global {event.name}")
