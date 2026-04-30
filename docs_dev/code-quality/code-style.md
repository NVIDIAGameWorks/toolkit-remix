# Code Style

Most code style rules are enforced automatically by the linter (`ruff`) and formatter (`black` + `isort`).
See `.ruff.toml` for the full linter configuration. This document covers rules that tools cannot enforce.

Run: `.\format_code.bat` (formatter) | `.\lint_code.bat all` (linter)

---

## Naming

Names must be descriptive and self-explanatory. Avoid vague names like `_push`, `_do`, `_run_it`.
Name them for what they do: `_push_settings_changed`, `_validate_host`, `_start_server`.

## Class Member Ordering

Order members by visibility.

1. Dunder methods (`__init__`, `__call__`, `__del__`, etc.)
2. Public properties
3. Protected properties
4. Public methods
5. Protected methods (`_`-prefixed)
6. Private methods (`__`-prefixed)

**Exceptions:** Related members may be grouped together when it aids readability:

- A public property and its setter can sit next to each other.
- A public method and its corresponding protected/private helper can sit next to each other.

Use the ordering above as the default; only deviate when keeping related pairs together makes the code
easier to follow.

## Module Exports

`__all__` must be defined in every public module.

### isort Grouping

Treat `carb`, `omni`, and `lightspeed` as **third-party**.

## Imports

Avoid import aliases (`import x as y` or `from x import y as z`) unless there is a name collision or a widely
established external convention. Prefer real module and symbol names so patch targets, stack traces, and grep results
stay obvious.

---

## License Headers

Every Python source file must begin with an SPDX Apache-2.0 license header as its first docstring.

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
```

| Scenario                                                  | Action                                                                             |
|-----------------------------------------------------------|------------------------------------------------------------------------------------|
| New files                                                 | Use the current year                                                               |
| Existing files                                            | Do not change the year                                                             |
| Existing files missing the header                         | Add it. Use `git log --follow --diff-filter=A -- <file>` to find the original year |
| Non-Python files (`.toml`, `.lua`, `.md`, `.rst`, `.kit`) | No header required                                                                 |

---

## Inline Comments

Only comment the **why**, never the **what**. If a comment explains what the code does, rewrite the code to
speak for itself.

| Do                               | Don't                                           |
|----------------------------------|-------------------------------------------------|
| Non-obvious design constraints   | Narrating obvious steps (`# Create the widget`) |
| Invariants not enforced by types | Development history (`# Tried X, so we do Z`)   |
|                                  | Debugging breadcrumbs                           |

Prefer code that doesn't need comments: rename variables, add type hints, extract well-named helpers.

---

## Docstrings (Google Style)

All public and protected members require a docstring. Only name-mangled private members (`__foo`) can omit
one unless the logic is non-obvious.

### Functions and Methods

```python
def process_textures(paths: list[str], output_dir: str, overwrite: bool = False) -> list[str]:
    """Convert source textures to the Remix-compatible format.

    Skips files that already exist in output_dir unless overwrite is set.

    Args:
        paths: Absolute paths to source texture files.
        output_dir: Directory where converted textures are written.
        overwrite: If True, re-convert files that already exist. Defaults to False.

    Returns:
        Absolute paths of all successfully converted output files.

    Raises:
        FileNotFoundError: If output_dir does not exist.
        ValueError: If paths is empty.
    """
```

| Rule                        | Detail                                                     |
|-----------------------------|------------------------------------------------------------|
| Summary line                | One sentence, ending with a period                         |
| Args                        | Describe the meaning, not the type (it's in the signature) |
| Returns / Raises            | Only if meaningful beyond the type annotation              |
| Self-explanatory signatures | A one-line summary is sufficient                           |

### Classes

```python
class TextureConverter:
    """Converts game textures to Remix-compatible formats.

    Maintains a session-level cache of already-converted paths to avoid
    redundant work across multiple calls. Not thread-safe — create one
    instance per job.

    Attributes:
        output_dir: Root directory where converted textures are written.
    """
```

| Rule        | Detail                                             |
|-------------|----------------------------------------------------|
| Focus       | Role and contract, not implementation              |
| Constraints | Call out thread safety, lifetime, ownership        |
| Attributes  | List public attributes not obvious from `__init__` |

### Modules

Top-level module docstrings are optional but useful for `.core` and `.service` extensions. Keep to 1-3 sentences.
