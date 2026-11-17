from fastapi import FastAPI
from routers import environment, export
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    app = FastAPI(title="Environment API")

    app.include_router(
        environment.router,
        prefix="/environment",
        tags=["Environment"],
    )

    app.include_router(
        export.router,
        prefix="/environment",
        tags=["Export"],
    )
    uvicorn.run(app, host=args.host, port=args.port, workers=1, timeout_graceful_shutdown=5,)


if __name__ == "__main__":
    main()