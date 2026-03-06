# Implementing Commands

All user-facing mutations must go through `omni.kit.commands.Command`. This is what makes actions undoable. Any action
that modifies data and is visible to the user requires this pattern — direct mutations will be rejected in review.

---

## When to Use This Pattern

Whenever a user action changes data: setting a property, moving a prim, replacing an asset, deleting an element, etc. If
the action would have an "Undo" entry in a standard application, it needs a Command here.

---

## Class Template

Place the command in `commands.py` in the relevant `.core` extension and export it from `__init__.py`.

```python
__all__ = ["MyActionCommand"]

import omni.kit.commands
import omni.kit.undo


class MyActionCommand(omni.kit.commands.Command):
    """One-line description of what this command does."""

    def __init__(self, param: str):
        self._param = param
        self._previous_value: str | None = None  # captured in do(), used in undo()

    def do(self):
        self._previous_value = get_current_value()  # capture state BEFORE modifying
        set_value(self._param)

    def undo(self):
        set_value(self._previous_value)
```

**Critical rules:**

- `do()` must capture all state needed for `undo()` **before** making any changes.
- Never call `omni.kit.commands.execute()` from inside `do()` or `undo()` — this corrupts the undo stack.
- Never instantiate a command and call `do()` directly — that bypasses the undo stack entirely.

---

## Executing a Command

```python
omni.kit.commands.execute("MyActionCommand", param="value")
```

The string name must exactly match the class name. Commands are registered globally by name — using the wrong string
fails silently.

---

## Grouping Multiple Sub-Commands

When a user action logically requires several sub-commands that should undo as one unit:

```python
with omni.kit.undo.group():
    omni.kit.commands.execute("SubCommandA", ...)
    omni.kit.commands.execute("SubCommandB", ...)
```

---

## Extension Dependency

Declare explicitly if this is the first extension in the dependency chain to use `omni.kit.commands`:

```toml
[dependencies]
"omni.kit.commands" = {}
```

---

## Testing

Write two separate tests — one `Act` each. The undo test's `execute()` call belongs in Arrange (it is setup, not the
thing under test).

```python
async def test_my_action_command_applies_new_value(self):
    # Arrange
    set_value("old_value")

    # Act
    omni.kit.commands.execute("MyActionCommand", param="new_value")

    # Assert
    self.assertEqual(get_current_value(), "new_value")


async def test_my_action_command_undo_restores_previous_value(self):
    # Arrange
    set_value("original_value")
    omni.kit.commands.execute("MyActionCommand", param="new_value")

    # Act
    omni.kit.undo.undo()

    # Assert
    self.assertEqual(get_current_value(), "original_value")
```
