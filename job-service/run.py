import argparse
import os


parser = argparse.ArgumentParser()

parser.add_argument(
    "--port",
    type=int,
    default=None,
)

parser.add_argument(
    "--reload",
    action="store_true",
)

args = parser.parse_args()


# Set PORT before Uvicorn imports app.main.
# This makes INSTANCE_ID and X-Served-By use the real port.
if args.port is not None:
    os.environ["PORT"] = str(args.port)


import uvicorn


uvicorn.run(
    "app.main:app",
    host="127.0.0.1",
    port=args.port or int(
        os.getenv("PORT", "8002")
    ),
    reload=args.reload,
)