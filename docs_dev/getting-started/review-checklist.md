# Review Checklist

Before submitting your code for review, please ensure you have thoroughly evaluated the following aspects:

0. **Branch Naming & Commit Format**: See [Git Workflow](git-workflow.md).

1. **Action Undoability**:
    - Ensure all your "actions" are undoable if the code is part of the Kit framework.
    - Use `omni.kit.undo` to implement the undo functionality for actions, allowing users to revert changes made by the
      code.

2. **USD Context Compatibility**:
    - Verify that your code (especially Kit commands) works with different USD contexts, not just the default context.
    - Consider various contexts like IngestCraft and ensure the command behaves correctly in each of them.

3. **Dependency Management**:
    - Double-check that all necessary dependencies are included in your `extension.toml` file.
    - Avoid relying on nested dependencies that may lead to unexpected behavior or conflicts.

4. **Documentation and Docstrings**:
    - Ensure all public functions in your code have appropriate docstrings.
    - Thoroughly document the functionality and purpose of each function, as the documentation will be generated from
      these docstrings.

5. **Version Bumping and Dependency Updates**:
    - Choose each modified extension's version from its complete change and compatibility impact; see
      [Version Bumping and Dependency Updates](#version-bumping-and-dependency-updates).
    - Record the changes in the extension's `docs/CHANGELOG.md` and the root `CHANGELOG.md`.

## Explanation of Terms

- **Action Undoability**: This refers to the ability to reverse an action performed by the code. In the Kit framework,
  only "commands" are undoable. Therefore, it is essential to implement commands for actions that users should be able
  to undo, rather than directly applying changes.

- **USD Context Compatibility**: The code should work effectively with different USD contexts, ensuring it does not
  focus solely on the default context. For instance, if the code is a Kit command, it should be applicable in various
  contexts like IngestCraft.

- **Dependency Management**: The `extension.toml` file should contain all necessary dependencies for the code to
  function correctly. Nested dependencies should be handled properly to avoid issues.

- **Documentation and Docstrings**: Public functions in the code should have descriptive docstrings that explain their
  purpose and usage. The documentation for the code will be generated from these docstrings.

- **Version Bumping and Dependency Updates**: Extension versions communicate compatibility; changelogs explain the
  changes delivered by each version.

## Examples

### Action Undoability

Incorrect implementation:

```python
# This action is not undoable
def rename_prim(prim, new_name):
    prim.Rename(new_name)
```

Correct implementation:

```python
# Implementing a command for undoability
class RenameCommand(omni.kit.commands.Command):
    def __init__(self, prim, name):
        self.prim = prim
        self.name = name
        self.old_name = prim.GetName()

    def do(self):
        self.prim.Rename(self.name)

    def undo(self):
        self.prim.Rename(self.old_name)
```

### USD Context Compatibility

Ensure your code works correctly in different USD contexts, not just the default one. Consider the following:

1. **Context-Agnostic Implementation**: Make sure your code does not rely solely on the default context of the Kit. If
   the code is designed to work with specific contexts, verify that it behaves appropriately in each context.

2. **IngestCraft Example**: For instance, if the code is a Kit command and you are working with the IngestCraft context,
   confirm that the command does not unintentionally interfere or have no effect in this specific context.

### Dependency Management

Ensure proper dependency management for your code:

1. **extension.toml**: Double-check that all the required dependencies are correctly listed in the `extension.toml`
   file. This file serves as a reference for the system to identify and fetch the necessary dependencies.

2. **Avoid Nested Dependencies**: Avoid relying on nested dependencies that may cause complications or conflicts. Ensure
   the code explicitly lists all direct dependencies without assuming that nested dependencies will automatically be
   available.

### Documentation and Docstrings

Thoroughly document your code to improve maintainability and understanding:

1. **Docstrings for Public Functions**: All public functions in the code should have clear and informative docstrings.
   These docstrings will be used to generate the code's documentation, making it easier for others to use and maintain
   the code.

### Version Bumping and Dependency Updates

Compare each modified extension's complete change against the review base (`origin/<base>` when preparing an MR).
Choose the highest required level across that change, based on supported behavior and contracts, not diff size,
commit labels, or changelog headings:

| Required level | Change |
| --- | --- |
| Patch | Compatible fixes, internal maintenance, documentation, or tests. |
| Minor | New supported functionality or deprecations that preserve compatibility. |
| Major | Incompatible changes to supported contracts, including APIs, events, settings, or persisted formats. |

Increment the required component and reset lower components to zero. Keep one resulting version increase per MR:
preserve an existing branch version only if it is newer than the base and sufficient for the aggregate change.
Do not repeatedly increment for follow-up commits or downgrade an intentionally larger, sufficient increase.

For existing `0.x` extensions, this repository uses patch increases for compatible fixes and maintenance, and minor
increases for new functionality, deprecations, or breaking changes. Moving to `1.0.0` is a deliberate stable-contract
milestone, not an automatic consequence of a breaking change. New extensions keep their declared initial release
version (the [extension scaffold](../architecture/extension-guide.md) defaults to `1.0.0`); there is no prior version
to bump. Removed extensions need no version increase; assess changes to surviving callers independently.

A review finding about a missing or insufficient bump must identify the base and submitted versions, the required
level, and the concrete delta that requires it. Claims that a feature or compatibility break requires a higher level
must cite the changed supported behavior or contract. When compatibility cannot be established from the available
evidence, report the uncertainty through the review's existing verification-gap handling.

Add extension changelog entries under the resulting `config/extension.toml` version, appending entries last within
their section. Keep one concise root `CHANGELOG.md` entry for the MR.

## Conclusion

Following these guidelines will ensure that your code is compatible with different USD contexts, manages dependencies
effectively, and is well-documented for ease of understanding and maintenance. Adhering to these best practices will
enhance the review process and contribute to the overall quality of the codebase.


