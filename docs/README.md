# API Documentation

This directory contains the OpenAPI/Swagger documentation for the DragonLens API.

## Files

- `swagger.yaml` - OpenAPI 3.1 specification in YAML format
- `openapi.json` - OpenAPI 3.1 specification in JSON format

## Viewing the Documentation

### Option 1: FastAPI Built-in Docs

When the API server is running, you can view the interactive documentation at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Option 2: Swagger Editor

1. Go to https://editor.swagger.io/
2. Upload or paste the contents of `swagger.yaml`

### Option 3: Local Swagger UI

```bash
docker run -p 8080:8080 -e SWAGGER_JSON=/docs/swagger.yaml -v $(pwd)/docs:/docs swaggerapi/swagger-ui
```

Then open http://localhost:8080

## Regenerating Documentation

The documentation is automatically generated from the FastAPI application code.

To regenerate:

```bash
poetry run python scripts/generate_swagger.py
```

This will update both `swagger.yaml` and `openapi.json`.

## API Overview

The DragonLens API provides endpoints for:

- **Verticals**: Manage industry categories (SUVs, smartphones, etc.)
- **Tracking Jobs**: Create and monitor brand tracking runs
- **Metrics**: Retrieve brand visibility metrics and analytics

All endpoints are prefixed with `/api/v1/`.
