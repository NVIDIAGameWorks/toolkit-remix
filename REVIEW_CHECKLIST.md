# Engineer's Code Review Checklist

Before submitting your code for review, please ensure that you have thoroughly reviewed the following aspects:

1. **Action Undoability**:
   - Ensure that all your "actions" are undoable if the code is part of the Kit framework.
   - Utilize `omni.kit.undo` to implement the undo functionality for actions. This allows users to undo changes made by the code.

2. **USD Context Compatibility**:
   - Verify that your code (especially Kit commands) works with different USD contexts, not just the default context.
   - Consider various contexts like IngestCraft and ensure that the command behaves correctly in each of them.

3. **Dependency Management**:
   - Double-check that all necessary dependencies are included in your `extension.toml` file.
   - Avoid relying on nested dependencies that may lead to unexpected behavior or conflicts.

4. **Documentation and Docstrings**:
   - Ensure that all public functions in your code have appropriate docstrings.
   - Thoroughly document the functionality and purpose of each function, as the documentation will be generated from these docstrings.

## Explanation of Terms

- **Action Undoability**: This refers to the ability to reverse an action performed by the code. In the Kit framework, only "commands" are undoable. Therefore, it's essential to implement commands for actions that users should be able to undo, rather than directly applying changes.

- **USD Context Compatibility**: The code should work effectively with different USD contexts, ensuring it doesn't focus solely on the default context. For instance, if the code is a Kit command, it should be applicable in various contexts like IngestCraft.

- **Dependency Management**: The `extension.toml` file should contain all necessary dependencies for the code to function correctly. Nested dependencies should be handled properly to avoid issues.

- **Documentation and Docstrings**: Public functions in the code should have descriptive docstrings that explain their purpose and usage. The documentation for the code will be generated from these docstrings.

## Examples

### Action Undoability

Wrong way:
```python
# This action is not undoable
def rename_prim(prim, new_name):
    prim.Rename(new_name)
```
Correct way:
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

1. **Context-Agnostic Implementation**: Make sure your code doesn't rely solely on the default context of the Kit. If the code is designed to work with specific contexts, verify that it behaves appropriately in each context.

2. **IngestCraft Example**: For instance, if the code is a Kit command and you're working with IngestCraft context, confirm that the command doesn't unintentionally interfere or have no effect in this specific context.

### Dependency Management

Ensure proper dependency management for your code:

1. **extension.toml**: Double-check that all the required dependencies are correctly listed in the `extension.toml` file. This file serves as a reference for the system to identify and fetch the necessary dependencies.

2. **Avoid Nested Dependencies**: Avoid relying on nested dependencies that may cause complications or conflicts. Ensure that the code explicitly lists all direct dependencies without assuming that nested dependencies will automatically be available.

### Documentation and Docstrings

Thoroughly document your code to improve maintainability and understanding:

1. **Docstrings for Public Functions**: All public functions in the code should have clear and informative docstrings. These docstrings will be used to generate the code's documentation, making it easier for others to use and maintain the code.

## Conclusion

Following these guidelines will ensure that your code is compatible with different USD contexts, manages dependencies effectively, and is well-documented for ease of understanding and maintenance. Adhering to these best practices will enhance the review process and contribute to the overall quality of the codebase.

