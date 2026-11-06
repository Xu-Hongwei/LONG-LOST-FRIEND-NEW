from __future__ import annotations

import uvicorn
from .api import create_app


def main() -> None:
    uvicorn.run("campus_lite.api:create_app", factory=True, host="127.0.0.1", port=8766)


if __name__ == "__main__":
    main()
