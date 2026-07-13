const state = {
  sessionId: localStorage.getItem("anaLiveSessionId") || null,
  booted: false,
  busy: false,
  speakerEnabled: true,
  micActive: false,
  mediaStream: null,
  audioContext: null,
  analyser: null,
  recorder: null,
  chunks: [],
  animationId: null,
  isRecording: false,
  speechStartedAt: 0,
  silenceStartedAt: 0,
};

const elements = {
  bootScreen: document.getElementById("bootScreen"),
  startButton: document.getElementById("startButton"),
  bootText: document.getElementById("bootText"),
  desk: document.getElementById("desk"),
  statusText: document.getElementById("statusText"),
  caption: document.getElementById("caption"),
  avatarImage: document.getElementById("avatarImage"),
  avatarVideo: document.getElementById("avatarVideo"),
  micButton: document.getElementById("micButton"),
  speakerButton: document.getElementById("speakerButton"),
  promptForm: document.getElementById("promptForm"),
  promptInput: document.getElementById("promptInput"),
  meterBar: document.getElementById("meterBar"),
};

const VOLUME_THRESHOLD = 0.024;
const MIN_SPEECH_MS = 300;
const END_SILENCE_MS = 650;

function setMode(mode, caption, status) {
  elements.desk.classList.remove("idle", "listening", "thinking", "speaking");
  elements.bootScreen.classList.remove("loading");
  if (mode) elements.desk.classList.add(mode);
  if (caption !== undefined) elements.caption.textContent = caption;
  if (status !== undefined) elements.statusText.textContent = status;
}

function setBoot(text, loading = false) {
  elements.bootText.textContent = text;
  elements.bootScreen.classList.toggle("loading", loading);
}

async function startReceptionist() {
  elements.startButton.disabled = true;
  setBoot("Checking local services...", true);
  try {
    const response = await fetch("/api/bootstrap", { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Bootstrap failed.");

    const wav2lip = data.steps?.find((step) => step.name === "wav2lip")?.result;
    if (data.status !== "ready") {
      const path = wav2lip?.checkpoint_path || "Wav2Lip/checkpoints/wav2lip_gan.pth";
      throw new Error(`Wav2Lip checkpoint missing. Expected: ${path}`);
    }

    state.booted = true;
    elements.bootScreen.classList.add("hidden");
    elements.desk.classList.remove("hidden");
    setMode("idle", "Namaste. How can I help you?", "Ready");
    elements.promptInput.focus();
  } catch (error) {
    setBoot(error.message, false);
    elements.startButton.disabled = false;
  }
}

async function askReceptionist(message) {
  const clean = message.trim();
  if (!clean || state.busy) return;

  state.busy = true;
  elements.promptInput.value = "";
  setMode("thinking", clean, "Preparing response");

  try {
    const response = await fetch("/api/receptionist/respond", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: clean,
        session_id: state.sessionId,
        speaker_enabled: state.speakerEnabled,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Receptionist request failed.");

    state.sessionId = data.session_id;
    localStorage.setItem("anaLiveSessionId", state.sessionId);
    elements.caption.textContent = data.answer;

    if (data.video_url) {
      await playSyncedVideo(data.video_url, data.answer);
    } else if (data.audio_url && state.speakerEnabled) {
      await playAudioResponse(data.audio_url, data.answer);
    } else {
      setMode("idle", data.answer, "Ready");
    }
  } catch (error) {
    setMode(state.micActive ? "listening" : "idle", error.message, state.micActive ? "Listening" : "Ready");
  } finally {
    state.busy = false;
    if (state.micActive) setMode("listening", "I am listening.", "Voice is on");
  }
}

function playSyncedVideo(url, caption) {
  return new Promise((resolve) => {
    const video = elements.avatarVideo;
    elements.avatarImage.classList.add("hidden");
    video.classList.remove("hidden");
    video.src = `${url}?t=${Date.now()}`;
    video.muted = !state.speakerEnabled;
    video.onended = () => {
      video.pause();
      video.removeAttribute("src");
      video.load();
      video.classList.add("hidden");
      elements.avatarImage.classList.remove("hidden");
      setMode("idle", caption, "Ready");
      resolve();
    };
    video.onerror = () => {
      video.classList.add("hidden");
      elements.avatarImage.classList.remove("hidden");
      setMode("idle", caption, "Video unavailable");
      resolve();
    };
    setMode("speaking", caption, "Speaking");
    video.play().catch(() => {
      video.muted = true;
      video.play().catch(resolve);
    });
  });
}

function playAudioResponse(url, caption) {
  return new Promise((resolve) => {
    const video = elements.avatarVideo;
    video.pause();
    video.classList.add("hidden");
    elements.avatarImage.classList.remove("hidden");

    const audio = new Audio(`${url}?t=${Date.now()}`);
    audio.onended = () => {
      setMode("idle", caption, "Ready");
      resolve();
    };
    audio.onerror = () => {
      setMode("idle", caption, "Audio unavailable");
      resolve();
    };
    setMode("speaking", caption, "Speaking");
    audio.play().catch(() => {
      setMode("idle", caption, "Ready");
      resolve();
    });
  });
}

async function toggleMic() {
  if (state.micActive) {
    stopMic();
    return;
  }
  try {
    state.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
    state.audioContext = new AudioContext();
    const source = state.audioContext.createMediaStreamSource(state.mediaStream);
    state.analyser = state.audioContext.createAnalyser();
    state.analyser.fftSize = 1024;
    source.connect(state.analyser);
    state.micActive = true;
    elements.micButton.classList.add("active");
    elements.micButton.setAttribute("aria-pressed", "true");
    setMode("listening", "I am listening.", "Voice is on");
    monitorMic();
  } catch (error) {
    setMode("idle", `Microphone error: ${error.message}`, "Mic unavailable");
  }
}

function stopMic() {
  state.micActive = false;
  state.isRecording = false;
  if (state.recorder && state.recorder.state !== "inactive") state.recorder.stop();
  if (state.animationId) cancelAnimationFrame(state.animationId);
  if (state.mediaStream) state.mediaStream.getTracks().forEach((track) => track.stop());
  if (state.audioContext) state.audioContext.close().catch(() => {});
  state.mediaStream = null;
  state.audioContext = null;
  state.analyser = null;
  elements.micButton.classList.remove("active");
  elements.micButton.setAttribute("aria-pressed", "false");
  elements.meterBar.style.width = "0%";
  setMode("idle", "Namaste. How can I help you?", "Ready");
}

function monitorMic() {
  if (!state.micActive || !state.analyser) return;
  const data = new Uint8Array(state.analyser.fftSize);
  const tick = () => {
    if (!state.micActive || !state.analyser) return;
    state.analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (const sample of data) {
      const centered = (sample - 128) / 128;
      sum += centered * centered;
    }
    const volume = Math.sqrt(sum / data.length);
    elements.meterBar.style.width = `${Math.min(100, Math.round(volume * 520))}%`;
    if (!state.busy) handleVoiceActivity(volume);
    state.animationId = requestAnimationFrame(tick);
  };
  tick();
}

function handleVoiceActivity(volume) {
  const now = performance.now();
  if (volume > VOLUME_THRESHOLD) {
    state.silenceStartedAt = 0;
    if (!state.isRecording) startRecording();
    if (!state.speechStartedAt) state.speechStartedAt = now;
  } else if (state.isRecording) {
    if (!state.silenceStartedAt) state.silenceStartedAt = now;
    const spokeLongEnough = now - state.speechStartedAt > MIN_SPEECH_MS;
    const pausedLongEnough = now - state.silenceStartedAt > END_SILENCE_MS;
    if (spokeLongEnough && pausedLongEnough) stopRecordingAndSend();
  }
}

function startRecording() {
  if (!state.mediaStream) return;
  state.chunks = [];
  state.speechStartedAt = 0;
  state.silenceStartedAt = 0;
  const options = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? { mimeType: "audio/webm;codecs=opus" }
    : {};
  state.recorder = new MediaRecorder(state.mediaStream, options);
  state.recorder.ondataavailable = (event) => {
    if (event.data.size > 0) state.chunks.push(event.data);
  };
  state.recorder.onstop = transcribeCurrentRecording;
  state.recorder.start();
  state.isRecording = true;
  setMode("listening", "I can hear you.", "Listening");
}

function stopRecordingAndSend() {
  if (!state.recorder || state.recorder.state === "inactive") return;
  state.isRecording = false;
  state.busy = true;
  setMode("thinking", "Let me catch that.", "Processing speech");
  state.recorder.stop();
}

async function transcribeCurrentRecording() {
  try {
    const blob = new Blob(state.chunks, { type: "audio/webm" });
    state.chunks = [];
    if (blob.size < 1200) {
      state.busy = false;
      setMode("listening", "I am listening.", "Voice is on");
      return;
    }
    const formData = new FormData();
    formData.append("audio", blob, "voice.webm");
    const response = await fetch("/api/transcribe", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Speech recognition failed.");
    state.busy = false;
    await askReceptionist(data.text);
  } catch (error) {
    state.busy = false;
    setMode("listening", error.message, "Voice is on");
  }
}

function toggleSpeaker() {
  state.speakerEnabled = !state.speakerEnabled;
  elements.speakerButton.classList.toggle("active", state.speakerEnabled);
  elements.speakerButton.setAttribute("aria-pressed", String(state.speakerEnabled));
}

elements.startButton.addEventListener("click", startReceptionist);
elements.micButton.addEventListener("click", toggleMic);
elements.speakerButton.addEventListener("click", toggleSpeaker);
elements.promptForm.addEventListener("submit", (event) => {
  event.preventDefault();
  askReceptionist(elements.promptInput.value);
});
