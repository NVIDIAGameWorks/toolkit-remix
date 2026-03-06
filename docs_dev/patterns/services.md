# Implementing REST Service Endpoints

Service endpoints use FastAPI via the Omniverse microservices layer. All implementations use `ServiceBase` from
`omni.flux.service.factory`.

---

## Extension Naming

Service endpoints live in a `.service` extension (e.g. `lightspeed.trex.my_feature.service`). If one doesn't exist for
the feature yet, scaffold it with the `create-extension` command first.

The canonical reference implementation is `lightspeed.trex.asset_replacements.service` — read it before implementing a
new service.

---

## Service Class Template

```python
__all__ = ["MyFeatureService"]

from omni.flux.service.factory import ServiceBase


class MyFeatureService(ServiceBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def prefix(cls) -> str:
        return "/my-feature"

    def router(self):
        @self._router.get("/items", summary="Get all items")
        async def get_items():
            from my.core.extension import get_instance
            return get_instance().get_items()

        @self._router.post("/items", summary="Create an item")
        async def create_item(body: MyItemModel):
            omni.kit.commands.execute("CreateItemCommand", data=body)
            return {"ok": True}

        return self._router
```

**Rules:**

- The service layer is thin — all business logic goes in `.core`.
- Mutations must go through `omni.kit.commands.execute()` so they are undoable.
- Use Pydantic models for request/response bodies.
- `prefix()` must be unique across all registered services.

---

## Factory Registration

Register and unregister the service in the `.service` extension's lifecycle:

```python
from omni.flux.service.factory import get_instance as _get_service_factory_instance
from .service import MyFeatureService as _MyFeatureService


class MyServiceExtension(omni.ext.IExt):
    def on_startup(self, _ext_id):
        _get_service_factory_instance().register_plugins([_MyFeatureService])

    def on_shutdown(self):
        _get_service_factory_instance().unregister_plugins([_MyFeatureService])
```

---

## Extension Dependencies

```toml
[dependencies]
"omni.flux.service.factory" = {}
"omni.services.transport.server.base" = {}
```

---

## Testing

Service tests run against the live FastAPI router. Test at minimum:

- **Happy path:** correct input returns the expected response and status code.
- **Validation:** malformed or missing input returns 422.
- **Side effects:** mutations call the expected command and the action is undoable.
