import argparse, uvicorn
from app.config import PORT
parser = argparse.ArgumentParser(); parser.add_argument("--port", type=int, default=PORT); parser.add_argument("--reload", action="store_true")
if __name__ == "__main__":
    args = parser.parse_args(); uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, reload=args.reload)
