# Overview

This is the widget that let you create a footer with different columns that show any data

![alt text](../data/images/preview.png)

## Usage

```python
from omni.flux.footer.widget import FooterWidget

home_footer = FooterWidget(model=None, height=None, column_width=None, between_columns_width=None)  # hold the widget in a variable or it will crash
```

## Implementation

The footer will need a model that containt the data we want to show.
For this, you will have to subclass the base model and implement the function the `content()` function:

```python
from functools import partial
from typing import Callable, Dict, Tuple
from omni.flux.footer.widget.model import FooterModel as _FooterModel

import omni.ui as ui


class Model(_FooterModel):
    def content(self) -> Dict[int, Tuple[Callable]]:
        """
        Get the data.

        Returns:
            A dictionary with all the data.
            First int is the column number, Tuple of Callable that will create the UI
        """
        return {
            0: (),
            1: (
                partial(ui.Spacer, height=ui.Pixel(24)),
                partial(ui.Label, "line1-2", height=ui.Pixel(24)),
                partial(ui.Label, "line1-3", height=ui.Pixel(24)),
            ),
            2: (
                partial(ui.Spacer, height=ui.Pixel(24)),
                self.__example,
                partial(ui.Label, "line2-2", height=ui.Pixel(24)),
                partial(ui.Label, "line2-3", height=ui.Pixel(24)),
                partial(ui.Label, "line2-4", height=ui.Pixel(24)),
            ),
        }

    def __example(self):
        with ui.HStack(height=ui.Pixel(24)):
            ui.Label("line2-1-0")
            ui.Spacer()
            ui.Label("line2-1-1", width=0)
```

`content()` has to return a dictionary with the column number as a key, and a tuple of callable function as values.

Each key represents a column (they are called into an `ui.HStack()`).

Each `ui.HStack()` will call the callable functions into a `ui.VStack()`.

Full example:
```python
from omni.flux.footer.widget import FooterWidget
from omni.flux.footer.widget.model import FooterModel as _FooterModel
from functools import partial
from typing import Callable, Dict, Tuple
import omni.ui as ui


class Model(_FooterModel):
    def content(self) -> Dict[int, Tuple[Callable]]:
        """
        Get the data.

        Returns:
            A dictionary with all the data.
            First int is the column number, Tuple of Callable that will create the UI
        """
        return {
            0: (),
            1: (
                partial(ui.Spacer, height=ui.Pixel(24)),
                partial(ui.Label, "line1-2", height=ui.Pixel(24)),
                partial(ui.Label, "line1-3", height=ui.Pixel(24)),
            ),
            2: (
                partial(ui.Spacer, height=ui.Pixel(24)),
                self.__example,
                partial(ui.Label, "line2-2", height=ui.Pixel(24)),
                partial(ui.Label, "line2-3", height=ui.Pixel(24)),
                partial(ui.Label, "line2-4", height=ui.Pixel(24)),
            ),
        }

    def __example(self):
        with ui.HStack(height=ui.Pixel(24)):
            ui.Label("line2-1-0")
            ui.Spacer()
            ui.Label("line2-1-1", width=0)

home_footer = FooterWidget(model=Model, height=ui.Pixel(144))  # hold the widget in a variable or it will crash
```

Result of this model:
![alt text](../data/images/preview.png)

We can see that on the left, column 0, there is nothing.

In the middle, column 1, there are 3 labels.

On the right, column 2, there are multiple labels. The first line as 2 labels in an `ui.HStack()`.
