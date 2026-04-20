from fastapi import FastAPI
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from app.api import router
from app.database import engine, Base
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown


app = FastAPI(
    title="Deployment Center",
    description="Railway deployment monitoring and control hub",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
