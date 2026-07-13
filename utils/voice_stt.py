import logging
import os
import re
import statistics
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

INITIAL_PROMPT = (
    "This is a college receptionist conversation. Expected terms include KCC, Kantipur City College, "
    "BCA-IT, BCA IT, BCAIT, BBA, BBS, BASW, admission, eligibility, scholarship, semester, "
    "faculty, course, program, fee, routine, schedule, Ravi sir, teacher, lecturer, coordinator."
)

LOW_VALUE_NOISE = {
    "with",
    "the",
    "and",
    "again",
    "uh",
    "um",
    "hmm",
    "mmm",
}

SHORT_CONFIDENCE_SENSITIVE_PHRASES = {
    "thank you",
    "thanks",
    "hello",
    "hi",
}

KNOWN_NOISE_PHRASES = {
    "and join the men again",
    "it feels like it's a creeper",
    "it feels like its a creeper",
}


class SpeechToTextService:
    def __init__(self, model_path: str = "models/stt/faster-whisper-small") -> None:
        self.model_path = Path(model_path)
        self._model = None
        self._device = "unknown"
        self._compute_type = "unknown"
        self._preferred_device = os.getenv("ANA_STT_DEVICE", "cuda").strip().lower()
        self._last_error: Optional[str] = None

    def status(self) -> Dict[str, str]:
        if not self.model_path.exists():
            return {
                "status": "missing",
                "path": str(self.model_path),
                "detail": "Whisper model folder was not found.",
            }
        if self._model is None:
            return {
                "status": "lazy",
                "path": str(self.model_path),
                "preferred_device": self._preferred_device,
                "device": self._device,
                "compute_type": self._compute_type,
                "detail": self._last_error or "Model will load on first transcription.",
            }
        return {
            "status": "ready",
            "path": str(self.model_path),
            "preferred_device": self._preferred_device,
            "device": self._device,
            "compute_type": self._compute_type,
        }

    def _load_model(self) -> None:
        if self._model is not None:
            return
        if self._preferred_device in {"cuda", "gpu"}:
            attempts = [
                ("cuda", "int8_float16"),
                ("cuda", "float16"),
                ("cpu", "int8"),
            ]
        elif self._preferred_device == "auto":
            attempts = [
                ("cuda", "int8_float16"),
                ("cuda", "float16"),
                ("cpu", "int8"),
            ]
        else:
            attempts = [("cpu", "int8")]
        self._load_model_with_attempts(attempts)

    def preload(self) -> None:
        self._load_model()

    def _load_model_with_attempts(self, load_attempts) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(f"Whisper model not found at {self.model_path}")

        from faster_whisper import WhisperModel

        errors = []
        for device, compute_type in load_attempts:
            try:
                logger.info("Loading Whisper model from %s on %s/%s", self.model_path, device, compute_type)
                self._model = WhisperModel(str(self.model_path), device=device, compute_type=compute_type)
                self._device = device
                self._compute_type = compute_type
                self._last_error = None
                logger.info("Whisper ready on %s/%s", device, compute_type)
                return
            except Exception as exc:
                errors.append(f"{device}/{compute_type}: {exc}")
                logger.warning("Whisper load failed on %s/%s: %s", device, compute_type, exc)

        self._last_error = " | ".join(errors)
        raise RuntimeError(f"Unable to load Whisper model. {self._last_error}")

    def _force_cpu_model(self, reason: Exception) -> None:
        logger.warning("Whisper runtime failed on %s/%s; switching to CPU int8. Error: %s", self._device, self._compute_type, reason)
        self._model = None
        self._device = "unknown"
        self._compute_type = "unknown"
        self._last_error = str(reason)
        self._load_model_with_attempts([("cpu", "int8")])

    def transcribe_bytes(self, audio_bytes: bytes, suffix: str = ".webm") -> Dict[str, object]:
        if not audio_bytes:
            raise ValueError("No audio bytes received.")

        self._load_model()

        suffix = suffix if suffix.startswith(".") else f".{suffix}"
        temp_path = None
        started_at = time.perf_counter()
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name

            try:
                segments, info = self._transcribe_file(temp_path)
            except Exception as exc:
                message = str(exc).lower()
                cuda_runtime_missing = "cublas" in message or "cudnn" in message or "cuda" in message
                if self._device == "cuda" and cuda_runtime_missing:
                    self._force_cpu_model(exc)
                    segments, info = self._transcribe_file(temp_path)
                else:
                    raise
            segment_list = list(segments)
            raw_text = " ".join(segment.text.strip() for segment in segment_list).strip()
            confidence = self._confidence_summary(segment_list)
            text = self._postprocess_text(raw_text, confidence)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            logger.info(
                "Transcribed %.2fs of audio into %d characters in %dms on %s/%s.",
                float(info.duration or 0),
                len(text),
                elapsed_ms,
                self._device,
                self._compute_type,
            )
            if raw_text != text:
                logger.info("STT normalized transcript from %r to %r.", raw_text, text)
            return {
                "text": text,
                "raw_text": raw_text,
                "duration": float(info.duration or 0),
                "language": info.language,
                "language_probability": float(info.language_probability or 0),
                "device": self._device,
                "compute_type": self._compute_type,
                "elapsed_ms": elapsed_ms,
                **confidence,
            }
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    logger.warning("Could not delete temporary audio file: %s", temp_path)

    def _transcribe_file(self, path: str):
        return self._model.transcribe(
            path,
            language="en",
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 250},
            condition_on_previous_text=False,
            initial_prompt=INITIAL_PROMPT,
        )

    def _confidence_summary(self, segments) -> Dict[str, float]:
        avg_logprobs = [float(getattr(segment, "avg_logprob", 0.0) or 0.0) for segment in segments]
        no_speech_probs = [float(getattr(segment, "no_speech_prob", 0.0) or 0.0) for segment in segments]
        compression_ratios = [float(getattr(segment, "compression_ratio", 0.0) or 0.0) for segment in segments]
        return {
            "avg_logprob": statistics.mean(avg_logprobs) if avg_logprobs else 0.0,
            "no_speech_prob": max(no_speech_probs) if no_speech_probs else 0.0,
            "compression_ratio": max(compression_ratios) if compression_ratios else 0.0,
        }

    def _postprocess_text(self, text: str, confidence: Optional[Dict[str, float]] = None) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        if not text:
            return ""

        normalized = text.strip(" .,!?:;\"'").lower()
        if normalized in LOW_VALUE_NOISE or normalized in KNOWN_NOISE_PHRASES:
            return ""

        replacements = [
            (r"\bB\s*C\s*A\s*[- ]?\s*I\s*T\b", "BCA-IT"),
            (r"\bBCA\s*ID\b", "BCA-IT"),
            (r"\bBCAID\b", "BCA-IT"),
            (r"\bBCAIT\b", "BCA-IT"),
            (r"\bPCA\s+(course|program)\b", r"BCA-IT \1"),
            (r"\brubbish\s+sir\b", "Ravi sir"),
            (r"\bravish\s+sir\b", "Ravi sir"),
            (r"\bravi\s+sir\b", "Ravi sir"),
        ]
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        text = text.strip()

        normalized_after = text.strip(" .,!?:;\"'").lower()
        protected = any(term in normalized_after for term in ("bca", "bca-it", "ravi sir", "kcc", "bba", "bbs", "basw"))
        confidence = confidence or {}
        avg_logprob = float(confidence.get("avg_logprob", 0.0))
        no_speech_prob = float(confidence.get("no_speech_prob", 0.0))
        word_count = len(normalized_after.split())
        weak_audio = no_speech_prob >= 0.55 or avg_logprob <= -0.85
        if weak_audio and not protected and (normalized_after in SHORT_CONFIDENCE_SENSITIVE_PHRASES or word_count <= 2):
            logger.info(
                "Rejected weak short transcript %r avg_logprob=%.3f no_speech_prob=%.3f.",
                text,
                avg_logprob,
                no_speech_prob,
            )
            return ""
        return text
