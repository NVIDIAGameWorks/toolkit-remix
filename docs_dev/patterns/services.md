# Implementing REST Service Endpoints

Service endpoints use FastAPI via the Omniverse microservices layer. All implementations use `ServiceBase` from
`omni.flux.service.factory`.

---

## Where Endpoints Live

The Toolkit's REST routes live in `lightspeed.trex.service.core`, one package per area under
`lightspeed/trex/service/core/routes/<surface>/<area>/` — for example `routes/stagecraft/assets/`. Add a Toolkit route
there rather than in a new extension. Generic services that other Flux apps reuse keep their own `.service` extension,
such as `omni.flux.validator.mass.service`.

The canonical reference implementation is `routes/stagecraft/assets/assets.py` (`AssetReplacementsService`) — read it
before implementing a new service.

---

## Service Class Rules

- The service layer is thin — all business logic goes in `.core`.
- `ServiceBase.__init__` calls `register_endpoints()`, so set everything the routes use before calling
  `super().__init__()`.
- Mutations must go through `omni.kit.commands.execute()` so they are undoable.
- Use Pydantic models for request/response bodies. Models the core logic also uses belong in its core extension;
  models only the route needs belong in the area's `data_models/` package.
- `prefix` must be unique among the services mounted on the same router.
- `operation_id` names the MCP tool and `description` is what a model reads; renaming an `operation_id` is a breaking
  API change.

---

## Registration and Mounting

Registering a class makes it findable by name in the service factory; mounting makes it reachable. Toolkit routes do
both in `lightspeed.trex.service.core`:

- **Register** a top-level service by adding it to `ROUTE_SERVICES` in `routes/__init__.py`. `CoreService` mounts the
  top-level services named in the extension's `services` setting.
- **Mount** an area from its top-level service. `StageCraftService` (`routes/stagecraft/stagecraft.py`) imports each
  stagecraft area's service and includes its router under `/stagecraft`. Areas are not registered with the factory.

`StageCraftService` mounts a fixed list of four areas. A new area serves nothing under `/stagecraft` until it joins that
list, even though its own e2e tests, which mount its router directly, still pass.

A Flux `.service` extension registers and unregisters its class in its own lifecycle:

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

A Toolkit route adds its backing core extension to `lightspeed.trex.service.core`'s `[dependencies]`. A Flux `.service`
extension declares the factory and transport:

```toml
[dependencies]
"omni.flux.service.factory" = {}
"omni.services.transport.server.base" = {}
```

---

## Testing

Service tests run against the live FastAPI router. Toolkit route tests live in `lightspeed.trex.service.core` under
`tests/e2e/<surface>/`, for example `tests/e2e/stagecraft/test_assets.py`. They share one Kit process with the routes
`CoreService` serves, so mount a test router under its own prefix and deregister it in `tearDown`. Test at minimum:

- **Happy path:** correct input returns the expected response and status code.
- **Validation:** malformed or missing input returns 422.
- **Side effects:** mutations call the expected command and the action is undoable.
