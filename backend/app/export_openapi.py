"""Print the FastAPI app's OpenAPI schema as JSON on stdout.

Used by `scripts/generate-api-client.sh` to feed `openapi-typescript`, which
regenerates `frontend/lib/api-types.ts`. Kept out of `main.py` so importing it
never spins up logging or touches the database (`app.openapi()` only reads
route metadata already registered at import time).
"""

import json

from .main import app


def main() -> None:
    print(json.dumps(app.openapi()))


if __name__ == "__main__":
    main()
