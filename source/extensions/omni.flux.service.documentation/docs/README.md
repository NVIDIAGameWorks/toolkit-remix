# Service Documentation Generation

This application will generate the offline HTML documentation for the kit microservices, by using
the main service instance (`from omni.services.core import main`).

To ensure your documentation includes all of your services, you should enable the extensions that register
endpoints in the main service instance and make sure they start before the generation extension does.
