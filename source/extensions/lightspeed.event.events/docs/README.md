# Lightspeed Global Events Registration

This extension registers all global custom events used across the application at startup.

## Overview

The extension automatically registers all events defined in `lightspeed.common.constants.GlobalEventNames` enum.

## Usage

Simply add this extension as a dependency in your extension.toml that subscribes to such events:

```toml
[dependencies]
"lightspeed.event.events" = {}
```

or add a new entry in the `GlobalEventNames` enum if you want a custom event.

The events will be automatically registered when this extension starts up.
