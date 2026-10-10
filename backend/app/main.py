from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .dependencies import get_data_service, get_ecos_service
from .routers import chat, conversations, data


@asynccontextmanager
async def lifespan(_: FastAPI):
    data_service = get_data_service()
    data_service.ensure_seed_data()
    settings = get_settings()
    ecos_service = get_ecos_service()
    sync_task = None
    if settings.auto_sync and settings.ecos_api_key:
        async def scheduled_sync() -> None:
            while True:
                if ecos_service.should_sync():
                    await asyncio.to_thread(ecos_service.sync, force=False)
                await asyncio.sleep(6 * 60 * 60)

        sync_task = asyncio.create_task(scheduled_sync())
    try:
        yield
    finally:
        if sync_task:
            sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await sync_task


app = FastAPI(
    title="EconScope API",
    description=(
        "한국은행 ECOS의 환율·기준금리·소비자물가 데이터를 비교하고, "
        "데이터 문맥을 반영한 AI 경제 해설을 제공하는 API입니다."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(chat.router)


@app.get("/", tags=["system"])
def root() -> dict:
    return {
        "service": "EconScope API",
        "status": "ready",
        "docs": "/docs",
    }


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok"}
