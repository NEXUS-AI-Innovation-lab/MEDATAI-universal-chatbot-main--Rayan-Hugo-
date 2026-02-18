"""
Main FastAPI application factory
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.settings import settings
from app.api.routes import rag, course, qcm


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application

    Returns:
        FastAPI: Configured application instance
    """
    app = FastAPI(
        title="RAG Server for LibreChat",
        description="RAG and Course Generation API",
        version="1.0.0"
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS if settings.CORS_ALLOW_ORIGINS != ['*'] else ["*"],
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS if settings.CORS_ALLOW_METHODS != ['*'] else ["*"],
        allow_headers=settings.CORS_ALLOW_HEADERS if settings.CORS_ALLOW_HEADERS != ['*'] else ["*"],
    )
    
    # Include routers
    app.include_router(rag.router)
    app.include_router(course.router)
    app.include_router(qcm.router, prefix="/qcm", tags=["QCM Generation"])

    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "status": "ok",
            "service": "RAG, Course & QCM Generation Server",
            "version": "1.0.0",
            "endpoints": {
                "rag": "/rag",
                "course": "/course",
                "qcm": "/qcm"
            }
        }

    return app


# Create app instance
app = create_app()

