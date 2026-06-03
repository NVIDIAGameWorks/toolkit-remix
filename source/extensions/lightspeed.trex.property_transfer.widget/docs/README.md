# lightspeed.trex.property_transfer.widget

## Overview

Shared modal used to transfer authored USD properties, prim definitions, and references between replacement layers.

The widget is intentionally shared. Property-pane actions open this modal today,
and other callers can use the same window without duplicating layer-tree or
transfer-command behavior.

## Architecture

```text
Property pane "..." action
        |
        | property item + authored USD property stack
        v
+----------------------------------------------+
| lightspeed.trex.property_transfer.widget     |
|                                              |
|  PropertyTransferWindow                      |
|   - builds transfer message                  |
|   - owns selected target layer               |
|   - calls the matching transfer command      |
|                                              |
|  layer_tree/model.py                         |
|   - reuses omni.flux.layer_tree.usd.widget   |
|   - exposes layer + transfer-state columns   |
|                                              |
|  layer_tree/delegate.py                      |
|   - reuses the layer-tree row rendering      |
|   - adds transfer-state checkmark styles     |
+----------------------------------------------+
        |
        | selected valid target layer
        v
+----------------------------------------------+
| lightspeed.trex.asset_replacements.core.shared |
|                                              |
|  TransferPropertySpecToLayerCommand          |
|  TransferPrimDefinitionSpecToLayerCommand    |
|  TransferReferenceSpecToLayerCommand         |
|   - move the selected spec kind to target      |
|   - remove editable source specs               |
|   - restore exact specs on undo                |
+----------------------------------------------+
```

## Code Structure

```text
lightspeed/trex/property_transfer/widget/
  __init__.py       Public PropertyTransferWindow import
  window.py         Modal and transfer execution flow
  layer_tree/       Transfer layer-tree model, delegate, and item state
  tests/e2e/        UI workflow coverage for modal behavior
```

## Transfer Flow

```text
1. Caller passes the native property item or prim/reference display data and its authored stack.
2. The window classifies which replacement layers contain authored values.
3. The reused layer tree renders valid target layers.
4. The user selects one target layer and clicks Transfer.
5. The command flattens the composed value onto the target layer.
6. The command removes the other editable source values.
7. Undo restores every touched layer exactly.
```
