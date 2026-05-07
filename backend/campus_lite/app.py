from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from .api import app


def create_app() -> FastAPI:
    return app


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8766)


if __name__ == "__main__":
    main()
