# Extension Guide

Complete reference for creating and documenting extensions in the RTX Remix Toolkit. This file covers naming
conventions, directory layout, configuration, and documentation structure.

---

## Extension Naming Conventions

Extension names encode their role:

- `.core` — Business logic only, no UI. Reusable across any UI or application.
- `.widget` — Reusable UI component built on `omni.ui.Frame`/`omni.ui.Stack` (never a window). Exposes `Event`
  subscriptions for interactions; contains no business logic.
- `.window` — Wraps one or more widgets in an `omni.ui.Window`. Often skipped — a simple window can live directly in
  `.controller`.
- `.menu` — Menu items only, exposes subscriptions. Often skipped — a simple menu can live directly in `.controller`.
- `.model` — Data models for tree/list views (`omni.ui.AbstractItemModel`)
- `.controller` — The top-level entry point for a feature. Wires `.core`, `.widget`/`.window`, and `.menu` together.
  This is the extension users enable to activate a feature.
- `.service` — REST API endpoints (FastAPI via Omniverse microservices)
- `.plugin.*` — Plugin implementations loaded by a factory
- `.app.resources` — Shared assets (icons, images, fonts) for an application. No code.
- `.style` — Global application stylesheet. No per-widget inline styles; all styles come from here.
- `.bundle` — Meta-extension that aggregates others for convenience loading

### Dependency Direction

`.controller` → `.widget` + `.core`. `.widget` and `.core` must never depend on each other.

### Flux / Lightspeed Namespaces

Generic UI and utilities go in `omni.flux.*`. RTX Remix-specific behavior goes in `lightspeed.trex.*`. A Lightspeed
extension typically imports a Flux widget and adds USD/game-specific behavior on top. Reusable logic should always be
extracted to Flux first.

---

## Directory Layout

```text
source/extensions/<ext-name>/
├── config/
│   └── extension.toml          # Required: package metadata, dependencies, settings, test config
├── data/
│   ├── icon.png                # 256×256 icon shown in the Extensions window
│   └── preview.png             # Screenshot shown in the Extensions Overview
├── docs/
│   ├── CHANGELOG.md            # Keep a Changelog format (required for versioning)
│   ├── README.md               # Extension documentation
│   └── index.rst               # Sphinx autodoc entry (copy pattern from existing exts)
├── <namespace>/<path>/<name>/  # Python package — mirrors the extension name exactly
│   ├── __init__.py             # Declares __all__ and re-exports public API
│   ├── extension.py            # omni.ext.IExt subclass (+ optional get_instance())
│   ├── *.py                    # Implementation files
│   └── tests/
│       ├── __init__.py         # Must export test classes for runner discovery
│       ├── unit/
│       │   └── test_*.py
│       └── e2e/
│           └── test_*.py
└── premake5.lua                # Build symlink script (boilerplate — copy from any existing ext)
```

The Python package path mirrors the extension name: `omni.flux.job_queue.core` → `omni/flux/job_queue/core/`. For
`lightspeed.*` extensions, replace the root with `lightspeed/`.

**Important:** The `omni.ext.IExt` subclass ALWAYS lives in `extension.py`, never in `__init__.py`. The `__init__.py`
file only declares `__all__` and re-exports the extension class (and `get_instance` if the extension needs a singleton
API). Kit discovers the `IExt` subclass from the module declared in `extension.toml` and runs its `on_startup` /
`on_shutdown` automatically.

---

## `extension.toml` Reference

```toml
[package]
version = "1.0.0"                      # Semantic versioning — bump on every change
authors = ["Name <email@nvidia.com>"]
title = "Human Readable Title"
description = "One-line description"
readme = "docs/README.md"
changelog = "docs/CHANGELOG.md"
category = "internal"                  # or "Service", "Rendering", etc.
keywords = ["keyword1", "keyword2"]
icon = "data/icon.png"
preview_image = "data/preview.png"
repository = "https://gitlab-master.nvidia.com/lightspeedrtx/lightspeed-kit/"

[dependencies]
# Direct dependencies only — never rely on transitive deps
"omni.usd" = {}
"omni.flux.utils.common" = {}
"other.ext" = { order = -100 }        # negative order = load earlier

# Platform-specific dependencies
[dependencies."filter:platform"."windows-x86_64"]
"windows.only.ext" = { version = "1.2.3", exact = true }

# Transient settings (reset on restart)
[settings]
exts."my.ext.name".some_key = "default_value"

# Persistent settings (saved across sessions)
[settings.persistent]
exts."my.ext.name".user_pref = "default_value"

# Python module registration
[[python.module]]
name = "my.ext.name"

# Test config — use lightspeed.trex.tests.dependencies for trex exts,
# omni.flux.tests.dependencies for flux exts
[[test]]
dependencies = [
    "lightspeed.trex.tests.dependencies",
]

# Suppress known-harmless log lines
stdoutFailPatterns.exclude = [
    "*[omni.kit.registry.nucleus.utils.common] Skipping deletion of:*",
]

# Optional named test suite (e.g. a fast "startup" suite)
[[test]]
name = "startup"
dependencies = [
    "lightspeed.trex.tests.dependencies",
]
```

**Notes:**

- Only declare dependencies that are actually imported by this extension.
- Add `"omni.flux.pip_archive" = {}` if the extension uses any third-party pip packages.
- Never rely on transitive dependencies — if you import it, declare it.

---

## `premake5.lua` Boilerplate

```lua
local ext = get_current_extension_info()

project_ext(ext)

repo_build.prebuild_link {
    { "lightspeed/", ext.target_dir.."/lightspeed" },  -- use "omni/" for flux exts
    { "data",        ext.target_dir.."/data" },
    { "docs",        ext.target_dir.."/docs" },
}
```

---

## Python Module Stubs

### `<namespace>/<path>/<name>/__init__.py`

```python
"""
* SPDX-FileCopyrightText: Copyright (c) <YEAR> NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["MyExtension"]

from .extension import MyExtension
```

### `<namespace>/<path>/<name>/extension.py`

```python
"""
* SPDX-FileCopyrightText: Copyright (c) <YEAR> NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["MyExtension"]

import carb
import omni.ext


class MyExtension(omni.ext.IExt):
    def on_startup(self, ext_id: str):
        carb.log_info("[<ext-name>] Startup")

    def on_shutdown(self):
        carb.log_info("[<ext-name>] Shutdown")
```

**Singleton pattern (`get_instance`):** Extensions themselves never need a singleton — Kit manages their lifecycle. The
`get_instance()` pattern is for exposing a **non-extension class** (e.g., a core service) that the extension creates
during startup. The extension owns the lifecycle; `get_instance()` returns the core object, not the extension. Export
`get_instance` from `__init__.py` only when other extensions need runtime access to that core object. Most extensions
do not need this.

### `docs/index.rst`

Copy the pattern from a nearby extension of the same type:

```rst
<ext-name>
==========

.. automodule:: <ext-name>
   :members:
   :undoc-members:
   :show-inheritance:
```

---

## `docs/CHANGELOG.md` Starter

```markdown
# Changelog
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [1.0.0]
### Added
- Created
```

---

## Tests Export Pattern

Only the top-level `tests/__init__.py` should exist. It must export test classes so the test runner can discover them.
Use explicit imports from the concrete test modules. Never use `import *`. Never add `tests/unit/__init__.py` or
`tests/e2e/__init__.py`. Update `tests/__init__.py` as you add tests:

```python
"""
* SPDX-FileCopyrightText: Copyright (c) <YEAR> NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from .unit.test_my_module import TestMyModule
from .e2e.test_my_workflow import TestMyWorkflow

__all__ = ["TestMyModule", "TestMyWorkflow"]
```

An empty `tests/__init__.py` causes the test runner to find nothing, even if test files exist — always export your test
classes.

Do not create `tests/unit/__init__.py` or `tests/e2e/__init__.py`; the only test package initializer should be
`tests/__init__.py`.

---

## `docs/README.md` Structure

Every extension's `docs/README.md` must describe the extension clearly enough that a developer can understand its role,
scope, and architecture without reading the code. The **Non-Responsibilities** section is as important as
Responsibilities — it prevents scope creep and misuse.

### Required sections

**Title and summary** — the extension name and one sentence describing what it is.

**Responsibilities** — a concrete list of what this extension owns. Be specific.

**Non-Responsibilities** — what this extension deliberately does *not* do, and which extension owns that instead.
Examples:

- A `.widget` extension: "Does not validate or process data. Fires subscriptions and lets the caller decide what to do."
- A `.core` extension: "Does not create any UI. Has no dependency on `omni.ui`."

**Architecture** — how the extension is structured:

- Key classes and their individual roles
- Non-obvious design decisions and the reason for them
- How it connects to dependencies (what it calls, what events it listens to)

### Optional sections (include when relevant)

**Usage** — a code snippet showing how another extension imports and uses this one.

**Settings** — any `carb` settings this extension exposes, with key paths, defaults, and purpose.

**Known limitations** — intentional gaps, unhandled edge cases, or things deferred to future work.

### README template

```markdown
# <Extension Name>

One-line description.

## Responsibilities

- Specific thing this extension is responsible for
- Another specific responsibility

## Non-Responsibilities

- What this extension does NOT do (and why, or what extension handles it instead)
- Another explicit non-responsibility

## Architecture

Description of how the extension is structured. Name the key classes and explain
the role of each. Call out any non-obvious design choices.

### Key Classes

- `MyCore` — owns the main processing logic; stateless between calls
- `MyEventHandler` — subscribes to `lightspeed.events_manager` and drives the core

## Usage

​```python
from my.extension import get_instance

core = get_instance(context_name="")
result = core.do_something(input_data)
​```

## Settings

| Setting path | Default | Description |
|---|---|---|
| `exts.my.ext.name.some_key` | `"default"` | What this controls |
```

### What NOT to write in a README

- Don't document every class and method — that belongs in docstrings.
- Don't describe implementation details that are obvious from reading the code.
- Don't leave the auto-generated one-line stub as the final documentation.
- Don't write "This extension provides functionality for X" — say specifically *what* functionality.
