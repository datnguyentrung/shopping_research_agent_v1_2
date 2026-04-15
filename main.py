import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as chat_router
from app.tools.query_category_classifier import init_classifier_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting up Shopping Research Agent API...")

    init_classifier_model()
    print("✅ All models initialized successfully! API is ready to serve requests.")

    yield
    print("🛑 Shutting down Shopping Research Agent API...")

# Khởi tạo FastAPI với lifespan
app = FastAPI(title="Shopping Research Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)

@app.get("/")
async def root():
    return {"message": "Shopping Research Agent API is running"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}

