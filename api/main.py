"""
NyayaSetu FastAPI Application.

Exposes the NyayaSetu Multi-Agent orchestrator pipeline over HTTP.
"""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import sys

# Ensure src directory is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import logging_config  # noqa: F401 - configure central logging format
from models import OrchestratorStageResult

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.schemas import AnswerRequest, SessionStartResponse, StartSessionRequest
from api.session_store import SessionStore

logger = logging.getLogger(__name__)

session_store = SessionStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application lifespan: starts the background session eviction
    loop on startup and cleanly cancels it on shutdown.
    """
    logger.info("Starting session store background cleanup task...")
    session_store.start_cleanup_task(interval_seconds=300, max_idle_seconds=1800)
    yield
    logger.info("Stopping session store background cleanup task...")
    await session_store.stop_cleanup_task()


app = FastAPI(
    title="NyayaSetu Multi-Agent Legal Assistance API",
    description="HTTP API exposing the NyayaSetu legal assistance pipeline.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
allowed_origins = [
    origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler ensuring no internal stack trace or raw exception
    text leaks to the client on unhandled failures.
    """
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        return await http_exception_handler(request, exc)
    logger.exception("Unhandled server exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Something went wrong, please start a new session."},
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    """
    Platform health check endpoint. Confirms the API process and its core
    dependencies are loaded and alive without invoking the orchestrator.
    """
    return {"status": "ok"}


@app.post(
    "/api/sessions",
    response_model=SessionStartResponse,
    status_code=status.HTTP_200_OK,
)
def create_session(request: StartSessionRequest) -> SessionStartResponse:
    """
    Creates a new legal assistance session, runs the initial message through
    the query understanding / intake pipeline, and returns the session ID and stage result.
    """
    try:
        session_id, session = session_store.create()
        result = session.start(request.message)
        session_store.touch(session_id)
        return SessionStartResponse(session_id=session_id, **result.model_dump())
    except Exception as exc:
        logger.exception("Unhandled exception during session creation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong, please start a new session.",
        )


@app.post(
    "/api/sessions/{session_id}/answer",
    response_model=OrchestratorStageResult,
    status_code=status.HTTP_200_OK,
)
def answer_question(
    session_id: str, request: AnswerRequest
) -> OrchestratorStageResult:
    """
    Records an answer to an intake checklist question for an active session.
    """
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )

    try:
        session_store.touch(session_id)
        result = session.answer_question(request.field_key, request.answer)
        return result
    except ValueError as exc:
        logger.warning(
            "Validation error in session %s answer_question: %s", session_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception(
            "Unhandled exception in session %s answer_question: %s", session_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong, please start a new session.",
        )


@app.post(
    "/api/sessions/{session_id}/proceed",
    response_model=OrchestratorStageResult,
    status_code=status.HTTP_200_OK,
)
def proceed_session(session_id: str) -> OrchestratorStageResult:
    """
    Proceeds with the legal pipeline (e.g. after a final check gap has been surfaced).
    """
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )

    try:
        session_store.touch(session_id)
        result = session.proceed()
        return result
    except ValueError as exc:
        logger.warning(
            "Validation error in session %s proceed: %s", session_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception(
            "Unhandled exception in session %s proceed: %s", session_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong, please start a new session.",
        )
