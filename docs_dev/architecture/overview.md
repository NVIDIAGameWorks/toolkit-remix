# Code Architecture

Complete architecture reference for the NVIDIA RTX Remix Toolkit.

For extension naming conventions and dependency direction,
see [Extension Guide](extension-guide.md#extension-naming-conventions).

---

## USD Contexts

The app runs three distinct USD contexts simultaneously, each isolating its own stage:

| Context enum             | String value     | Layout name      | Code name    |
|--------------------------|------------------|------------------|--------------|
| `Contexts.STAGE_CRAFT`   | `""` (default)   | Modding Layout   | StageCraft   |
| `Contexts.INGEST_CRAFT`  | `"ingestcraft"`  | Ingestion Layout | IngestCraft  |
| `Contexts.TEXTURE_CRAFT` | `"texturecraft"` | AI Tools Layout  | TextureCraft |

Always pass `context_name` to USD operations. Never assume the default context — code that only works with `""` is
broken in IngestCraft and TextureCraft.

---

## Extension Lifecycle

### Standard pattern — single instance, simple lifecycle

```python
_INSTANCE = None

def get_instance():
    return _INSTANCE

class MyExtension(omni.ext.IExt):
    def on_startup(self, ext_id: str):
        global _INSTANCE
        _INSTANCE = MyCore()

    def on_shutdown(self):
        global _INSTANCE
        _INSTANCE.destroy()
        _INSTANCE = None
```

### Context-aware pattern — one instance per USD context

Preferred for any extension that operates on a stage. Instances are created lazily on first access:

```python
_instances: dict[str, "MyCore"] = {}

def get_instance(context_name: str = "") -> "MyCore":
    if context_name not in _instances:
        _instances[context_name] = MyCore(context_name=context_name)
    return _instances[context_name]

class MyExtension(omni.ext.IExt):
    def on_startup(self, ext_id: str):
        pass  # instances are created on first access

    def on_shutdown(self):
        _instances.clear()
```

### `default_attr` cleanup pattern — multiple attributes to tear down

`reset_default_attrs` calls `destroy()` on each attribute (if it exists), then resets it to the default value. Use this
instead of manually nulling attributes in `on_shutdown`:

```python
from omni.flux.utils.common import reset_default_attrs

class MyExtension(omni.ext.IExt):
    def __init__(self):
        super().__init__()
        self.default_attr = {"_core": None, "_sub": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    def on_startup(self, ext_id: str):
        self._core = MyCore()
        self._sub = EventSubscription(...)

    def on_shutdown(self):
        reset_default_attrs(self)
```

### Pure library pattern — no lifecycle management

Extensions that are just Python packages omit `extension.py` entirely. Register only via `[[python.module]]` in
`extension.toml`. `omni.flux.utils.common` is an example.

---

## Design Principles

**Separate concerns so that code can be reused across any UI, application, or context.**

- `.core` does the work. It takes inputs and produces outputs. No UI, no menus.
- `.widget` shows the UI. It fires subscriptions when the user interacts. It does no processing.
- `.controller` connects them. It is the only extension a user needs to enable.

This means you can swap the UI without changing the logic, and reuse the logic from a completely different UI. A
`.widget` built on `omni.ui.Frame` can be embedded in a window, a sidebar, or a panel in any application — not just the
one it was designed for.

**Widget rule:** Always build widgets on `omni.ui.Frame` or `omni.ui.Stack`, never on `omni.ui.Window`. A widget must be
embeddable anywhere without creating a standalone window.

**Style rule:** Never define a stylesheet inside a widget or window extension. Styles belong in the app-level `.style`
extension. Use identifier names on UI elements so the stylesheet can target them.

---

## Event System

Use `omni.flux.utils.common.Event` and `EventSubscription` for intra-extension events (not carb events):

```python
from omni.flux.utils.common import Event, EventSubscription

self._on_change = Event()
self._sub = EventSubscription(self._on_change, self._handle_change)
```

**Critical lifetime rule:** An `EventSubscription` is only active while it is referenced. If you do not assign the
return value to `self`, it is garbage-collected immediately and the callback never fires. Always store subscriptions as
instance attributes.

---

## Events Manager

`lightspeed.events_manager` provides a global event bus for Remix-wide lifecycle events (game capture loaded, stage
replaced, etc.). Event extensions register themselves on startup and unregister on shutdown:

```python
from lightspeed.events_manager import get_instance as _get_event_manager_instance

class MyEventExtension(omni.ext.IExt):
    def on_startup(self, ext_id: str):
        self._core = MyEventCore()
        _get_event_manager_instance().register_event(self._core)

    def on_shutdown(self):
        _get_event_manager_instance().unregister_event(self._core)
```

Use `lightspeed.events_manager` for cross-extension Remix lifecycle events. Use `omni.flux.utils.common.Event` for
events scoped to a single extension's public API.

---

## Commands (Undo Support)

All user-facing actions that modify data must be `omni.kit.commands.Command` subclasses with `do()` and `undo()`. Direct
mutations without commands will be rejected in review.

See [Implementing Commands](../patterns/commands.md) for the full implementation reference.

---

## Factory / Plugin Pattern

Many systems (validators, stage manager, AI tools) use `omni.flux.factory.base`. Plugins register themselves and are
discovered at runtime. See `omni.flux.validator.factory` for the canonical example.

Service extensions register with `omni.flux.service.factory`:

```python
from omni.flux.service.factory import get_instance as _get_service_factory_instance

def on_startup(self, _ext_id):
    _get_service_factory_instance().register_plugins([MyService])

def on_shutdown(self):
    _get_service_factory_instance().unregister_plugins([MyService])
```

See [Implementing REST Service Endpoints](../patterns/services.md) for the full implementation reference.

---

## Settings

Declared in `extension.toml` under `[settings]` (transient) or `[settings.persistent]` (persisted across sessions).
Access at runtime via `carb.settings.get_settings()`.

For drag-lifetime USD churn, prefer a shared helper over ad-hoc transient settings. Use
`omni.flux.utils.common.interactive_usd_notices` so interactive writers bracket the edit and listeners can receive one
aggregated `Usd.Notice.ObjectsChanged` flush when the interaction ends.

```toml
[settings]
exts."my.ext.name".some_key = "default_value"

[settings.persistent]
exts."my.ext.name".user_pref = "default_value"
```

---

## Pip Archive

Extensions that need third-party Python packages must declare `"omni.flux.pip_archive" = {}` as a dependency — do not
add pip packages directly to `requirements.txt` or import them without this. `omni.flux.pip_archive` bundles packages (
including Pillow, numpy, PyGit2, etc.) and makes them importable. If a package you need is not in the archive, raise it
with the team rather than trying to install it another way.

See [Adding Pip Package Dependencies](../patterns/pip-packages.md) for the full reference.

---

## Job Queue

`omni.flux.job_queue.core` provides a generic priority-based job queue with dependency tracking. Use `JobGraph` for
multi-step jobs with dependencies. AI tool integrations (ComfyUI, etc.) use this for background processing.

---

## App Files vs. Extension Dependencies

Most extensions are loaded transitively through `[dependencies]` in another extension's `extension.toml`. Only add an
extension directly to a `.kit` app file if it is a standalone top-level UI entry point with no parent extension that
would load it.

App files live in `source/apps/`:

| App file                               | When to add                                   |
|----------------------------------------|-----------------------------------------------|
| `lightspeed.app.trex.base.kit`         | Core feature needed across all Remix contexts |
| `lightspeed.app.trex.stagecraft.kit`   | StageCraft (main modding view) only           |
| `lightspeed.app.trex.texturecraft.kit` | TextureCraft (texture remastering) only       |
| `lightspeed.app.trex.ingestcraft.kit`  | IngestCraft (asset ingestion) only            |
| `lightspeed.app.trex_dev.kit`          | Developer-only / debug features               |
