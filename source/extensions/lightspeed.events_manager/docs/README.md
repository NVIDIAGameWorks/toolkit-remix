# omni.drivesim.scenario.events_manager

# Overview
API that let developer to register DS events (behaviors).

For example, if an attribute in the current stage change, we want to fired something.

Or if we open a stage, we want to do something.

# API

To register an DS event

First you need to create an extension that will implement the behavior, like:
`omni.drivesim.scenario.event.my_behavior`

```python
from omni.drivesim.scenario.events_manager.scripts.i_ds_event import IDSEvent


class MyBehavior(IDSEvent):

    def __init__(self):
        super().__init__()
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    @property
    def name(self) -> str:
        """Name of the event"""
        return "MyBehavior"

    def _install(self):
        """Function that will create the behavior"""
        print("Behavior installed")

    def _uninstall(self):
        """Function that will delete the behavior"""
        print("Behavior uninstalled")
```

After you have to register your behavior

```python
from omni.drivesim.scenario.events_manager.scripts.core import EVENTS_MANAGER_INSTANCE

my_behavior = MyBehavior()
EVENTS_MANAGER_INSTANCE.register_event(my_behavior)
```

As a result, the event manager will install your behavior.

## All commands

```python
from omni.drivesim.scenario.events_manager.scripts.core import EVENTS_MANAGER_INSTANCE

EVENTS_MANAGER_INSTANCE.register_event()
EVENTS_MANAGER_INSTANCE.unregister_event()
EVENTS_MANAGER_INSTANCE.get_registered_events()
EVENTS_MANAGER_INSTANCE.subscribe_event_registered()
```
