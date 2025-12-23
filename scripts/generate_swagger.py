import sys
from pathlib import Path
import yaml
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    # When package is installed, api is a top-level module
    from api import app
except ImportError:
    # When running from source, api is under src
    from src.api import app

if __name__ == "__main__":
    openapi_schema = app.openapi()

    docs_dir = Path(__file__).parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)

    yaml_path = docs_dir / "swagger.yaml"
    json_path = docs_dir / "openapi.json"

    with open(yaml_path, "w") as f:
        yaml.dump(openapi_schema, f, sort_keys=False, default_flow_style=False)

    with open(json_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)

    print(f"✅ Generated Swagger documentation:")
    print(f"   - {yaml_path}")
    print(f"   - {json_path}")
