# Automated Testing Guidelines

**Tip**: Several tests will run in CI/CD, but to run them all locally: `repo.bat test`

## Writing Tests

Writing tests is an essential practice in software development to ensure the reliability and correctness of code. In the context of extensions, different types of tests are used to verify their functionality and behavior.

### Unit Tests

- **Purpose**: Unit tests focus on testing individual units or components of code in isolation to ensure they work as expected.
- **Scope**: These tests are used when there is no user interface (UI) involved or when testing new utility functions.
- **Approach**: Unit tests often use fake data (Mocks) to simulate different scenarios and test the logic of the code.
- **Example**: If you have a utility function that performs some calculations, a unit test would validate that the function returns the correct output for various input scenarios.

### End-to-End (E2E) Tests (Integration Tests)

- **Purpose**: E2E tests, as the name suggests, simulate a complete end-to-end scenario by testing the entire system from start to finish.
- **Scope**: They are particularly useful when dealing with extensions that have a UI component.
- **Approach**: E2E tests mimic user interactions with the UI, including keyboard inputs and other actions, and they use real data inputs (no Mocks) to closely resemble actual usage scenarios.
- **Example**: If you have an extension that provides a graphical user interface, an E2E test would automate interactions with that UI to verify that the extension functions correctly under realistic conditions.

## Omni Kit UI Test Framework

When testing extensions in the context of Omni Kit, the [UI test framework](http://omniverse-docs.s3-website-us-east-1.amazonaws.com/kit-manual/105.0/guide/testing_exts_python.html#omni-kit-ui-test-writing-ui-tests) provided in the kit documentation allows developers to write UI tests for their extensions, ensuring that the user interface behaves as expected.

## Test Directory Structure

To organize your tests effectively, follow these guidelines:

* Add tests in a subdir next to the `__init__.py` file in your extensions.
* Use separate subdirs for E2E and unit tests, with the tests themselves contained within.
* When you have completed writing tests, please update the `extension.toml` to reflect that there are tests, and specify which arguments (if any) should be applied.

## Test Coverage

It is generally recommended to write tests for most extensions, with the only exception being extensions that do not have any functional code. Writing tests helps catch bugs early in the development process and facilitates maintenance and refactoring.

As part of the merge request process, engineers are required to submit a coverage percentage for any new tests, along with their code.  To generate the coverage percentage, the desired test can be run with the `--coverage` arg, and a report will be produced.  Upon open the report, navigate to the coverage tab, filter for newly added files/tests, and see the 'total' coverage percentage reported.

For more information on measuring code coverage in Python testing, you can refer to the [code coverage documentation](http://omniverse-docs.s3-website-us-east-1.amazonaws.com/kit-manual/105.0/guide/testing_exts_python.html#tests-code-coverage-python). Code coverage analysis helps identify areas of code that may not have been tested adequately and can guide efforts to improve test coverage.

## Conclusion

In summary, when developing extensions, it is advisable to write unit tests for code logic and, if the extension includes a UI, write end-to-end tests to simulate user interactions and ensure the proper functioning of the user interface.
