from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

import app.models  # noqa: F401
from app.config import VERSION
from app.database import Base, engine
import logging
from app.health import router as health_router
from app.routers.spot import router as spot_router
from app.routers.clients import router as clients_router
from app.routers.query import router as query_router
from app.routers.research import router as research_router
from app.routers.tender_webhook import router as tender_webhook_router
from app.routers.quotations import router as quotations_router
from core.scheduler import start_scheduler, shutdown_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    
    # Start APScheduler with client configurations
    start_scheduler("clients")
    
    yield
    
    # Shutdown APScheduler on application exit
    shutdown_scheduler()
    
    # Close all knowledge graphs to release file locks
    from graph import close_all_graphs
    close_all_graphs()
    
    await app.state.http_client.aclose()
    await engine.dispose()


app = FastAPI(
    title="Pydantic AI Agent",
    description="Generic Pydantic AI agent template with FastAPI",
    version=VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(spot_router)
app.include_router(clients_router)
app.include_router(query_router)
app.include_router(research_router)
app.include_router(tender_webhook_router)
app.include_router(quotations_router)

