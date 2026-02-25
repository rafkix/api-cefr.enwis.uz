import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.database import init_db
from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as user_router
from app.modules.services.exams.mock.router import router as mock_router
from app.modules.services.exams.reading.router import router as reading_router
from app.modules.services.exams.listening.router import router as listening_router
from app.modules.services.exams.writing.router import router as writing_router

app = FastAPI(
    title="Cefr Enwis Backend API",
    version="2.5.0",
    description=(
        "Enwis is an educational platform created for learning foreign languages using AI. \n"
        "This API manages users, courses, exercises, AI translation, and gamification systems."
    ),
)


origins = [
    "http://localhost:2006",
    "http://127.0.0.1:2006",
    "https://enwis.uz",
    "https://app.enwis.uz",
    "https://api.enwis.uz",
    "https://cefr.enwis.uz",
]

if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # MUHIM: Mana shu qatorni qo'shing
    expose_headers=["Content-Disposition"], 
)

app.add_middleware(
    SessionMiddleware,
    secret_key="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"  # o‘zgartir!
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
app.include_router(mock_router, prefix="/api/v1")
app.include_router(reading_router, prefix="/api/v1")
app.include_router(listening_router, prefix="/api/v1")
app.include_router(writing_router, prefix="/api/v1")

@app.on_event("startup")
async def on_startup():
    await init_db()
    print("✅ Database initialized successfully.")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "status_code": exc.status_code,
                "detail": exc.detail,
                "path": str(request.url),
            }
        },
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"❌ Unexpected error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "status_code": 500,
                "detail": "Internal Server Error",
                "path": str(request.url),
            }
        },
    )


@app.get("/", tags=["System"])
async def root():
    return {
        "message": "🚀 Enwis Backend API is running!",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "database": "connected"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
