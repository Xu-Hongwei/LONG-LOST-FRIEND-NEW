from __future__ import annotations

import uvicorn
import os
from .api import create_app


def main() -> None:
    port = int(os.getenv("CAMPUS_BACKEND_PORT") or "8766")
    if not 1 <= port <= 65535:
        raise ValueError("CAMPUS_BACKEND_PORT must be between 1 and 65535")
    uvicorn.run("campus_lite.api:create_app", factory=True, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
