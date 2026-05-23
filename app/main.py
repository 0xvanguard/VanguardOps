# pyrefly: ignore [missing-import]
from fastapi import FastAPI
from app.api.router import api_router
from app.database import Base, engine

# Inicializar tablas en la base de datos
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="VanguardOps API",
    description="API central de operaciones para VanguardOps - Gestión de Assets, Tickets y Workflows",
    version="1.0.0"
)

import os
# pyrefly: ignore [missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore [missing-import]
from fastapi.responses import FileResponse

app.include_router(api_router, prefix="/api/v1")

# Interfaz estática (Frontend Dashboard)
os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", tags=["frontend"])
def read_dashboard():
    return FileResponse("app/static/index.html")

@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "service": "VanguardOps API"}
