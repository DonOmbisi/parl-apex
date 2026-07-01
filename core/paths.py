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


def resolve_sqlite_url(database_url: str | None) -> str:
    if not database_url:
        return default_sqlite_url()

    sqlite_prefixes = ("sqlite:///", "sqlite+aiosqlite:///")
    prefix = next((value for value in sqlite_prefixes if database_url.startswith(value)), None)
    if not prefix:
        return database_url

    db_location = database_url[len(prefix):]
    if not db_location or db_location == ":memory:":
        return database_url

    if db_location.startswith("/"):
        db_path = Path(db_location)
    else:
        db_path = Path(resolve_data_path(db_location))

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"{prefix}{db_path.as_posix()}"
