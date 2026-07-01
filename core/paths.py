import os
from pathlib import Path


def get_data_dir() -> Path:
    configured = os.getenv("DATA_DIR")
    if configured:
        return Path(configured)

    app_env = os.getenv("APP_ENV", "development").lower()
    if app_env in {"production", "prod"} or os.getenv("RENDER"):
        return Path("/data")

    return Path("./data")


def resolve_data_path(path_value: str | os.PathLike[str]) -> str:
    path = Path(path_value)
    if path.is_absolute():
        return str(path)

    parts = path.parts
    if parts and parts[0] == "data":
        path = Path(*parts[1:]) if len(parts) > 1 else Path()

    return str(get_data_dir() / path)


def default_sqlite_url(filename: str = "app.db") -> str:
    db_path = get_data_dir() / filename
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"
