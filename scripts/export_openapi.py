"""Write the API's OpenAPI spec to docs/openapi.json.

The committed spec is the contract the team builds against. CI fails if the code and the
committed spec disagree (tests/test_openapi.py), so run this after any API change:

    python -m scripts.export_openapi
"""

import json
from pathlib import Path

from app.main import app

SPEC_PATH = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def render_spec() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    SPEC_PATH.write_text(render_spec(), encoding="utf-8")
    print(f"Wrote {SPEC_PATH}")
