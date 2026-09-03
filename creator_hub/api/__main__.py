from __future__ import annotations

import argparse

import uvicorn

from creator_hub.config import DEFAULT_DB
from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the typed Creator Intelligence FastAPI service")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(create_app(args.db), host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
