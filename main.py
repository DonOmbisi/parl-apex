import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from app.main import app

if __name__ == "__main__":
    app_env = os.getenv("APP_ENV", "development").lower()
    reload_mode = app_env != "production"

    try:
        workers = max(1, int(os.getenv("UVICORN_WORKERS", "1")))
    except ValueError:
        workers = 1

    if reload_mode:
        workers = 1

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=4141,
        reload=reload_mode,
        workers=workers,
    )
