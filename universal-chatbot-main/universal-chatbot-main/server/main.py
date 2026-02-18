"""
Server entry point
"""
import uvicorn
from app.core.settings import settings


if __name__ == "__main__":
    print(f"""
    ╔════════════════════════════════════════════════════════════════════╗
    ║             RAG & Course Generation Server                         ║
    ║                                                                    ║
    ║  RAG Endpoints:           /rag/*                                   ║
    ║  Course Endpoints:        /course/*                                ║
    ║                                                                    ║
    ║  Interactive docs: {settings.SERVER_BASE_URL}/docs              ║
    ╚════════════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "app.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        log_level=settings.LOG_LEVEL,
        reload=True  # Enable auto-reload for development
    )
