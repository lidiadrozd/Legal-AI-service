from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

# Импорт роутеров (пока закомментированы, создадим позже)
# from app.chat.endpoints import router as chat_router
# from app.documents.generator import router as docs_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Стартап и shutdown события"""
    # При запуске
    print(" Starting Legal AI Service...")
    yield
    # При остановке
    print(" Shutting down Legal AI Service...")

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

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "ok",
        "service": "Legal AI Service",
        "version": "0.1.0"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}
# app.include_router(chat_router, prefix="/chat", tags=["Chat"])
# app.include_router(docs_router, prefix="/documents", tags=["Documents"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
