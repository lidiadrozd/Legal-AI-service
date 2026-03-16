# backend/app/main.py - Обновленный main
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from app.api import auth, chat
from app.db.session import engine
from app.db.base import Base
from app.core.config import settings

# Создаем таблицы
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Legal AI Service...")
    yield
    print("🛑 Shutting down Legal AI Service...")

app = FastAPI(
    title="Legal AI Service",
    description="Юридический AI-сервис (Сбербанк)",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])

@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Legal AI Service",
        "version": "0.1.0",
        "endpoints": {
            "auth": ["/auth/register", "/auth/login", "/auth/consent"],
            "chat": ["/chat/new", "/chat/list", "/chat/{id}/send_stream"]
        }
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}
