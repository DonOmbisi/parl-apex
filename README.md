# Pydantic AI Agent Template

A minimal FastAPI + Pydantic AI project template for building LLM-powered agents. Uses uv for dependency management, async SQLAlchemy for persistence, and Alembic for migrations.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
# Install dependencies
uv sync

# Copy env file and fill in your keys
cp .env.example .env

# Run migrations
uv run alembic upgrade head

# Start the server
uv run python main.py
```

The API will be available at `http://localhost:4141`. Interactive docs at `/docs`.

## Project Structure

```
app/
├── main.py          # FastAPI app, lifespan, middleware
├── config.py        # Shared constants (version, etc.)
├── database.py      # Async SQLAlchemy engine, session, Base
├── models.py        # SQLAlchemy models
├── schemas.py       # Pydantic request/response models
├── auth.py          # API key authentication
├── health.py        # Health check endpoint
├── agent/
│   ├── core.py      # Pydantic AI Agent definition
│   ├── context.py   # Agent dependencies (AgentDeps)
│   └── prompts.py   # System prompts
└── routers/
    └── chat.py      # POST /chat endpoint
```

## Environment Variables


| Variable         | Description                          | Default                             |
| ---------------- | ------------------------------------ | ----------------------------------- |
| `OPENAI_API_KEY` | OpenAI API key                       | -                                   |
| `DATABASE_URL`   | Database connection string           | `sqlite+aiosqlite:///./data/app.db` |
| `APP_API_KEY`    | API key for endpoint auth (optional) | disabled                            |
| `APP_ENV`        | `development` or `production`        | `development`                       |


## Database Migrations

```bash
# Generate a new migration after model changes
uv run alembic revision --autogenerate -m "describe change"

# Apply migrations
uv run alembic upgrade head
```

## Docker

```bash
docker compose up --build
```

