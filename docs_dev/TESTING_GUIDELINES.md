# Automated Testing Guidelines

**Tip**: Several tests will run in CI/CD, but to run them all locally: `./repo.bat test`. To run tests for specific
extensions, use the corresponding batch file in the
format `.\_build\windows-x86_64\release\tests-lightspeed.app.trex.bat`, where `lightspeed.app.trex.bat` is the name of
the extension.

## Writing Tests

Writing tests is an essential practice in software development to ensure the reliability and correctness of code. In the
context of extensions, different types of tests are used to verify their functionality and behavior.

### Unit Tests

- **Purpose**: Unit tests focus on testing individual units or components of code in isolation to ensure they work as
  expected.
- **Scope**: These tests are used when there is no user interface (UI) involved or when testing new utility functions.
- **Approach**: Unit tests often use fake data (Mocks) to simulate different scenarios and test the logic of the code.
- **Naming**: Follow the Arrange/Act/Assert pattern and give tests descriptive names
  like `test_this_function_should_do_this_and_return_this`. Use subtests to cover various edge cases with clear names
  like `subtest_should_delete_True` and `subtest_should_delete_False`.
- **Example**: If you have a utility function that performs some calculations, a unit test would validate that the
  function returns the correct output for various input scenarios.

#### Subtests (`self.subTest`)

Use `self.subTest` when a single logical behaviour needs to be verified across multiple inputs or edge cases. Each
subtest must exercise **one code path in isolation** — give it its own Arrange, Act, and Assert — while the full set
of subtests together covers all relevant paths and edge cases.

Structure the test as a **single loop** that contains all three steps. Do not split them across multiple loops:

```python
def test_filter_should_include_only_valid_extensions(self):
    core = MyCore()

    # Each tuple is one code path: (input, expected_outcome)
    cases = [
        ("texture.png", ".png", True),   # valid texture extension
        ("mesh.fbx",    ".fbx", True),   # valid asset extension
        ("readme.txt",  ".txt", False),  # unsupported extension
    ]

    for name, suffix, should_include in cases:
        with self.subTest(file=name):
            # Arrange
            mock_file = MagicMock()
            mock_file.suffix = suffix
            mock_file.name = name
            mock_folder = MagicMock()
            mock_folder.iterdir.return_value = iter([mock_file])

            # Act
            result = core.get_valid_files(mock_folder, "")

            # Assert
            if should_include:
                self.assertEqual(len(result), 1)
            else:
                self.assertEqual(len(result), 0)
```

Key rules:
- The `with self.subTest(...)` block is the outermost wrapper inside the loop.
- Arrange, Act, and Assert all live **inside** the `subTest` block.
- Never build a shared result before the loop and then assert inside it — that turns
  one Act into an all-or-nothing call that hides which specific case failed.
- The `subTest` label (e.g. `file=name`) must be descriptive enough to identify the
  failing case immediately from the test report.

### End-to-End (E2E) Tests (Integration Tests)

- **Purpose**: E2E tests, as the name suggests, simulate a complete end-to-end scenario by testing the entire system
  from start to finish.
- **Scope**: They are particularly useful when dealing with extensions that have a UI component.
- **Approach**: E2E tests mimic user interactions with the UI, including keyboard inputs and other actions, and they use
  real data inputs (no Mocks) to closely resemble actual usage scenarios.
- **Example**: If you have an extension that provides a graphical user interface, an E2E test would automate
  interactions with that UI to verify that the extension functions correctly under realistic conditions.

## Omni Kit UI Test Framework

When testing extensions in the context of Omniverse Kit,
the [UI test framework](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/testing_exts_python.html#omni-kit-ui-test-writing-ui-tests)
provided in the kit documentation allows developers to write UI tests for their extensions, ensuring that the user
interface behaves as expected.

## Test Directory Structure

To organize your tests effectively, follow these guidelines:

- Add a `tests` subdirectory next to the `__init__.py` file in your extensions.
- Use separate subdirectories for `e2e` and `unit` tests, with the tests themselves contained within.
- When you have completed writing tests, please update the `extension.toml` to reflect that there are tests, and specify
  which arguments (if any) should be applied.

## Test Coverage

It is generally recommended to write tests for most extensions, with the only exception being extensions that do not
have any functional code. Writing tests helps catch bugs early in the development process and facilitates maintenance
and refactoring.

As part of the merge request process, engineers are required to submit a coverage percentage for any new tests, along
with their code. To generate the coverage percentage, the desired test can be run with the `--coverage` argument, and a
report will be produced. Upon opening the report, navigate to the coverage tab, filter for newly added files/tests, and
see the 'total' coverage percentage reported.

For more information on measuring code coverage in Python testing, you can refer to
the [code coverage documentation](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/testing_exts_python.html#tests-code-coverage-python).
Code coverage analysis helps identify areas of code that may not have been tested adequately and can guide efforts to
improve test coverage.

## Conclusion

In summary, when developing extensions, it is advisable to write unit tests for code logic and, if the extension
includes a UI, write end-to-end tests to simulate user interactions and ensure the proper functioning of the user
interface.
