"""
Request and Response Schemas for the NyayaSetu HTTP API.
"""

import sys
from pathlib import Path
from pydantic import BaseModel

# Ensure src directory is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from models import OrchestratorStageResult


class StartSessionRequest(BaseModel):
    message: str


class AnswerRequest(BaseModel):
    field_key: str
    answer: str


class SessionStartResponse(OrchestratorStageResult):
    session_id: str
