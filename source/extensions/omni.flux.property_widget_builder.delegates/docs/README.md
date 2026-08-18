# Overview

`omni.flux.property_widget_builder.delegates` contains reusable property fields for items from
`omni.flux.property_widget_builder.widget`. Its public fields include the shared typed-value editors, file picker, and
ComboBox used by USD, Material, Object, and native property models.

# Implementation

Subclass `AbstractField` and implement `build_ui()`. Prefer an existing shared field before adding a product-specific
editor. `FilePicker` accepts stable field and picker identifiers. Relative-path pickers must also provide the
keyword-only `stage_resolver` callback; constructing `FilePicker(use_relative_paths=True)` without that explicit USD
stage capability raises `ValueError`. `ComboboxField` consumes an `ui.AbstractItemModel` supplied by the property
value model.
