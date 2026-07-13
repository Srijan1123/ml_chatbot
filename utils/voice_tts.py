import io
import logging
import os
import threading
import tempfile
import wave
from pathlib import Path
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


class TextToSpeechService:
    def __init__(
        self,
        voice: str = "af_heart",
        lang_code: str = "a",
        speed: float = 1.08,
        sample_rate: int = 24000,
    ) -> None:
        self.voice = voice
        self.lang_code = lang_code
        self.speed = speed
        self.sample_rate = sample_rate
        self._pipeline = None
        self._voice_ref = voice
        self._device = "cpu"
        self._mode = "kokoro"
        self._last_error: Optional[str] = None
        self._load_lock = threading.Lock()

    def status(self) -> Dict[str, str]:
        if self._pipeline is None:
            return {
                "status": "lazy",
                "mode": self._mode,
                "voice": self.voice,
                "device": self._device,
                "detail": self._last_error or "Kokoro CPU TTS will load on first speech request.",
            }
        return {
            "status": "ready",
            "mode": self._mode,
            "voice": self.voice,
            "device": self._device,
        }

    def preload(self) -> None:
        self._load_model()

    def _load_model(self) -> None:
        if self._pipeline is not None:
            return
        with self._load_lock:
            if self._pipeline is not None:
                return
            self._load_model_unlocked()

    def _load_model_unlocked(self) -> None:
        try:
            import torch
            from kokoro.model import KModel
            from kokoro import KPipeline

            self._device = "cpu"
            torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
            logger.info("Loading Kokoro TTS voice=%s lang=%s on CPU", self.voice, self.lang_code)
            local_model = self._load_local_kokoro_model(KModel)
            self._pipeline = KPipeline(lang_code=self.lang_code, model=local_model, device="cpu")
            self._last_error = None
            logger.info("Kokoro TTS ready on CPU with voice=%s", self.voice)
        except Exception as exc:
            self._pipeline = None
            self._last_error = str(exc)
            logger.exception("Kokoro TTS initialization failed.")
            raise

    def synthesize_wav(self, text: str) -> bytes:
        text = (text or "").strip()
        if not text:
            raise ValueError("Text cannot be empty.")

        if os.getenv("ANA_TTS_MODE", "").strip().lower() == "pyttsx3":
            return self._synthesize_with_pyttsx3(text)

        try:
            self._load_model()
        except Exception:
            logger.warning("Kokoro unavailable; falling back to Windows SAPI TTS.")
            return self._synthesize_with_pyttsx3(text)

        chunks = []
        generator = self._pipeline(
            text[:1200],
            voice=self._voice_ref,
            speed=self.speed,
            split_pattern=r"(?<=[.!?])\s+|\n+",
        )
        for _, _, audio in generator:
            chunks.append(np.asarray(audio, dtype=np.float32))

        if not chunks:
            raise RuntimeError("Kokoro did not generate audio.")
        waveform = np.concatenate(chunks)
        return self._float_audio_to_wav_bytes(waveform, self.sample_rate)

    def _load_local_kokoro_model(self, model_cls):
        cache_root = Path.home() / ".cache" / "huggingface" / "hub" / "models--hexgrad--Kokoro-82M" / "snapshots"
        snapshots = sorted((path for path in cache_root.glob("*") if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True)
        for snapshot in snapshots:
            config_path = snapshot / "config.json"
            model_path = snapshot / "kokoro-v1_0.pth"
            voice_path = snapshot / "voices" / f"{self.voice}.pt"
            if config_path.exists() and model_path.exists() and voice_path.exists():
                self._voice_ref = str(voice_path)
                return model_cls(repo_id="hexgrad/Kokoro-82M", config=str(config_path), model=str(model_path))
        return model_cls(repo_id="hexgrad/Kokoro-82M")

    def _synthesize_with_pyttsx3(self, text: str) -> bytes:
        try:
            import pyttsx3

            handle = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp_path = handle.name
            handle.close()
            try:
                engine = pyttsx3.init()
                engine.setProperty("rate", 168)
                engine.setProperty("volume", 1.0)
                voices = engine.getProperty("voices") or []
                female_voice = next(
                    (
                        voice
                        for voice in voices
                        if any(token in f"{voice.name} {voice.id}".lower() for token in ("female", "zira", "aria", "jenny", "susan"))
                    ),
                    None,
                )
                if female_voice:
                    engine.setProperty("voice", female_voice.id)
                engine.save_to_file(text[:1200], temp_path)
                engine.runAndWait()
                with open(temp_path, "rb") as audio_file:
                    audio = audio_file.read()
                if not audio:
                    raise RuntimeError("Windows SAPI did not generate audio.")
                self._mode = "pyttsx3"
                self._last_error = "Kokoro unavailable; using Windows SAPI fallback."
                return audio
            finally:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        except Exception as exc:
            raise RuntimeError(f"Fallback text to speech failed: {exc}") from exc

    @staticmethod
    def _float_audio_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
        waveform = np.asarray(audio, dtype=np.float32)
        waveform = np.nan_to_num(waveform)
        if waveform.ndim > 1:
            waveform = waveform.mean(axis=-1)
        waveform = np.clip(waveform, -1.0, 1.0)
        pcm = (waveform * 32767).astype(np.int16)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm.tobytes())
        return buffer.getvalue()
