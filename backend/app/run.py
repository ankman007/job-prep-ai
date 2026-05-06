from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.middleware import LoggingAndPerformanceMiddleware
from app.db.session import Base, engine
from app.routes.auth import router as auth_router
from app.routes.cheatsheet import router as cheatsheet_router
from app.routes.user import router as user_router
from app.routes.health import router as health_router
from app.db.models import UserModel, InterviewCheatSheetModel

def create_app():
    app = FastAPI() 

    app.add_middleware(LoggingAndPerformanceMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "https://job-fit-ai.vercel.app"
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router, prefix="/auth")
    app.include_router(cheatsheet_router, prefix="/cheatsheet")
    app.include_router(user_router, prefix="/user")
    app.include_router(health_router, prefix="/health")

    Base.metadata.create_all(bind=engine)

    return app
