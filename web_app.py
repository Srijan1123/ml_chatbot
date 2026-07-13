import logging
import os
import threading
from pathlib import Path
from typing import Dict, List
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend" / "public"

app = FastAPI(title="ANA AI Receptionist Voice Mode", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: Dict[str, List[Dict[str, str]]] = {}
_stt_service = None
_tts_service = None


def _get_stt_service():
    global _stt_service
    if _stt_service is None:
        from utils.voice_stt import SpeechToTextService

        _stt_service = SpeechToTextService()
    return _stt_service


def _get_tts_service():
    global _tts_service
    if _tts_service is None:
        from utils.voice_tts import TextToSpeechService

        _tts_service = TextToSpeechService()
    return _tts_service


def preload_tts_model() -> None:
    try:
        _get_tts_service().preload()
        logger.info("TTS preload completed.")
    except Exception:
        logger.exception("TTS preload failed; speech requests will retry on demand.")


def preload_stt_model() -> None:
    try:
        _get_stt_service().preload()
        logger.info("STT preload completed.")
    except Exception:
        logger.exception("STT preload failed; speech requests will retry on demand.")


@app.on_event("startup")
def startup() -> None:
    if os.getenv("ANA_PRELOAD_TTS", "1").strip().lower() not in {"0", "false", "no"}:
        threading.Thread(target=preload_tts_model, name="tts-preload", daemon=True).start()
    if os.getenv("ANA_PRELOAD_STT", "1").strip().lower() not in {"0", "false", "no"}:
        threading.Thread(target=preload_stt_model, name="stt-preload", daemon=True).start()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    meta: Dict[str, str]


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1200)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/api/health")
def health() -> Dict[str, object]:
    from utils.chat_service import check_llm_health

    return {
        "status": "ok",
        "llm": check_llm_health(),
        "stt": _get_stt_service().status(),
        "tts": _get_tts_service().status(),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    from utils.chat_service import ChatServiceError, answer_receptionist

    session_id = payload.session_id or uuid4().hex
    history = sessions.setdefault(session_id, [])
    try:
        answer, meta = answer_receptionist(payload.message, history)
        logger.info("Chat answered for session=%s source=%s", session_id, meta.get("source"))
        return ChatResponse(session_id=session_id, answer=answer, meta=meta)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ChatServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected chat failure.")
        raise HTTPException(status_code=500, detail="The receptionist could not answer right now.") from exc


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> Dict[str, object]:
    try:
        audio_bytes = await audio.read()
        suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
        result = _get_stt_service().transcribe_bytes(audio_bytes, suffix=suffix)
        if not result["text"]:
            raise HTTPException(status_code=422, detail="I could not hear a clear question. Please try again.")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Transcription failed.")
        raise HTTPException(status_code=500, detail=f"Speech recognition failed: {exc}") from exc


@app.post("/api/tts")
def tts(payload: TTSRequest) -> Response:
    try:
        audio = _get_tts_service().synthesize_wav(payload.text)
        return Response(content=audio, media_type="audio/wav")
    except FileNotFoundError as exc:
        logger.warning("TTS unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("TTS synthesis failed.")
        raise HTTPException(status_code=500, detail=f"Text to speech failed: {exc}") from exc
