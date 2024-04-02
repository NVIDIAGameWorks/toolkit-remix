# lightspeed.event.shutdown

An event extension for any shutdown related activities.

## Events

### Unsaved Project Event
If the app is in the middle of making changes, this event will halt shutdown and give over control to `lightspeed.trex.control.stagecraft` to save unsaved progress before closing.
