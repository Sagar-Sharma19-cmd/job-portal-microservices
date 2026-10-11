import argparse

import uvicorn

from app.config import PORT


def main():
    parser = argparse.ArgumentParser(description="Run Notification Service")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Restart the server when source files change",
    )
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()