const state = {
  sessionId: localStorage.getItem("anaSessionId") || null,
  voiceActive: false,
  mediaStream: null,
  audioContext: null,
  analyser: null,
  recorder: null,
  chunks: [],
  animationId: null,
  isRecording: false,
  isBusy: false,
  isSpeaking: false,
  speechStartedAt: 0,
  silenceStartedAt: 0,
  lastVolume: 0,
  useBrowserTTS: new URLSearchParams(window.location.search).get("browserTts") === "1",
};

const elements = {
  body: document.body,
  stage: document.getElementById("stage"),
  orbLabel: document.getElementById("orbLabel"),
  caption: document.getElementById("caption"),
  statusLine: document.getElementById("statusLine"),
  messages: document.getElementById("messages"),
  chatForm: document.getElementById("chatForm"),
  textInput: document.getElementById("textInput"),
  micButton: document.getElementById("micButton"),
  micText: document.getElementById("micText"),
  meterBar: document.getElementById("meterBar"),
  miniLog: document.getElementById("miniLog"),
  healthBadge: document.getElementById("healthBadge"),
  healthText: document.getElementById("healthText"),
};

const VOLUME_THRESHOLD = 0.024;
const MIN_SPEECH_MS = 300;
const END_SILENCE_MS = 650;

function setMode(mode, caption, status) {
  elements.stage.classList.remove("listening", "thinking", "speaking");
  if (mode) elements.stage.classList.add(mode);
  const labels = {
    listening: "Listening",
    thinking: "Thinking",
    speaking: "Speaking",
  };
  elements.orbLabel.textContent = labels[mode] || "Ready";
  if (caption !== undefined) elements.caption.textContent = caption;
  if (status !== undefined) elements.statusLine.textContent = status;
}

function logMini(text) {
  elements.miniLog.innerHTML = `<p>${escapeHtml(text)}</p>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function addMessage(role, text) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.innerHTML = `<span class="role">${role === "user" ? "You" : "Receptionist"}</span>${escapeHtml(text)}`;
  elements.messages.appendChild(node);
  elements.messages.scrollTop = elements.messages.scrollHeight;
  return node;
}

function updateMessage(node, text) {
  const role = node.classList.contains("user") ? "You" : "Receptionist";
  node.innerHTML = `<span class="role">${role}</span>${escapeHtml(text)}`;
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    const llmReady = data.llm?.status === "ready";
    elements.healthBadge.classList.toggle("ready", llmReady);
    elements.healthBadge.classList.toggle("error", !llmReady);
    elements.healthText.textContent = llmReady ? "Ready" : "LLM offline";
    if (data.tts?.status === "fallback") {
      logMini("Local Qwen voice needs the female reference files. Browser voice fallback is active.");
    }
  } catch (error) {
    elements.healthBadge.classList.add("error");
    elements.healthText.textContent = "Backend offline";
  }
}

async function sendChat(message, speak = false) {
  const clean = message.trim();
  if (!clean || state.isBusy) return;

  state.isBusy = true;
  addMessage("user", clean);
  setMode("thinking", clean, "Receptionist is thinking");
  logMini("Thinking...");

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: clean, session_id: state.sessionId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Chat request failed.");

    state.sessionId = data.session_id;
    localStorage.setItem("anaSessionId", state.sessionId);

    const assistantNode = addMessage("assistant", data.answer);
    elements.caption.textContent = data.answer;
    if (speak) {
      await speakAnswer(data.answer);
    } else {
      setMode(null, data.answer, "Ready");
    }
  } catch (error) {
    setMode(null, "Something went wrong.", "Error");
    logMini(error.message);
    addMessage("assistant", error.message);
  } finally {
    state.isBusy = false;
    if (state.voiceActive) {
      setMode("listening", "I am listening.", "Voice is on");
    }
  }
}

async function revealCaption(text, node) {
  setMode("speaking", "", "Preparing response");
  let shown = "";
  const words = text.split(/\s+/).filter(Boolean);
  for (const word of words) {
    shown = shown ? `${shown} ${word}` : word;
    elements.caption.textContent = shown;
    updateMessage(node, shown);
    await sleep(28);
  }
  return shown;
}

function splitSentences(text) {
  const chunks = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [text];
  return chunks.map((chunk) => chunk.trim()).filter(Boolean);
}

async function speakAnswer(text) {
  setMode("speaking", text, "Receptionist is speaking");
  logMini("Speaking...");
  state.isSpeaking = true;

  try {
    const chunks = splitSentences(text);
    if (state.useBrowserTTS) {
      for (const chunk of chunks) {
        await speakWithBrowser(chunk);
      }
      logMini("Browser voice finished.");
      if (state.voiceActive) {
        setMode("listening", "I am listening.", "Voice is on");
      } else {
        setMode(null, text, "Ready");
      }
      return;
    }

    let usedLocalTTS = false;
    let nextAudioPromise = chunks.length ? fetchLocalSpeech(chunks[0]) : null;
    for (let index = 0; index < chunks.length; index += 1) {
      const chunk = chunks[index];
      const audioBlob = await nextAudioPromise;
      nextAudioPromise = chunks[index + 1] ? fetchLocalSpeech(chunks[index + 1]) : null;
      if (audioBlob) {
        usedLocalTTS = true;
        await playAudioBlob(audioBlob);
      } else {
        await speakWithBrowser(chunk);
      }
    }

    logMini(usedLocalTTS ? "Kokoro voice finished." : "Browser voice fallback finished.");
    if (state.voiceActive) {
      setMode("listening", "I am listening.", "Voice is on");
    } else {
      setMode(null, text, "Ready");
    }
  } finally {
    state.isSpeaking = false;
  }
}

async function fetchLocalSpeech(text) {
  try {
    const response = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) return null;
    return response.blob();
  } catch (error) {
    return null;
  }
}

function playAudioBlob(blob) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => {
      URL.revokeObjectURL(url);
      resolve();
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      resolve();
    };
    audio.play().catch(resolve);
  });
}

function speakWithBrowser(text) {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window)) return resolve();
    const utterance = new SpeechSynthesisUtterance(text);
    const voices = speechSynthesis.getVoices();
    const femaleVoice = voices.find((voice) => /female|zira|susan|aria|jenny|natural/i.test(voice.name));
    if (femaleVoice) utterance.voice = femaleVoice;
    utterance.rate = 1.04;
    utterance.pitch = 1.0;
    utterance.onend = resolve;
    utterance.onerror = resolve;
    speechSynthesis.speak(utterance);
  });
}

async function toggleVoice() {
  if (state.voiceActive) {
    stopVoice();
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
    state.voiceActive = true;
    elements.micButton.classList.add("active");
    elements.micButton.setAttribute("aria-pressed", "true");
    elements.micText.textContent = "Stop voice";
    setMode("listening", "I am listening.", "Voice is on");
    logMini("Voice is active.");
    monitorVoice();
  } catch (error) {
    logMini(`Microphone error: ${error.message}`);
    setMode(null, "Microphone unavailable.", "Error");
  }
}

function stopVoice() {
  state.voiceActive = false;
  state.isRecording = false;
  if (state.recorder && state.recorder.state !== "inactive") {
    state.recorder.stop();
  }
  if (state.animationId) cancelAnimationFrame(state.animationId);
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach((track) => track.stop());
  }
  if (state.audioContext) {
    state.audioContext.close().catch(() => {});
  }
  state.mediaStream = null;
  state.audioContext = null;
  state.analyser = null;
  elements.micButton.classList.remove("active");
  elements.micButton.setAttribute("aria-pressed", "false");
  elements.micText.textContent = "Start voice";
  elements.meterBar.style.width = "0%";
  setMode(null, "Good to see you. How can I help?", "Ready");
  logMini("Voice is idle.");
}

function monitorVoice() {
  if (!state.voiceActive || !state.analyser) return;

  const data = new Uint8Array(state.analyser.fftSize);
  const tick = () => {
    if (!state.voiceActive || !state.analyser) return;
    state.analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (const sample of data) {
      const centered = (sample - 128) / 128;
      sum += centered * centered;
    }
    const volume = Math.sqrt(sum / data.length);
    state.lastVolume = volume;
    elements.meterBar.style.width = `${Math.min(100, Math.round(volume * 520))}%`;

    if (!state.isBusy && !state.isSpeaking) handleVoiceActivity(volume);
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
  state.isBusy = true;
  setMode("thinking", "Let me catch that.", "Processing speech");
  state.recorder.stop();
}

async function transcribeCurrentRecording() {
  try {
    const blob = new Blob(state.chunks, { type: "audio/webm" });
    state.chunks = [];
    if (blob.size < 1200) {
      state.isBusy = false;
      setMode("listening", "I am listening.", "Voice is on");
      return;
    }
    const formData = new FormData();
    formData.append("audio", blob, "voice.webm");
    const response = await fetch("/api/transcribe", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Speech recognition failed.");
    elements.caption.textContent = data.text;
    state.isBusy = false;
    await sendChat(data.text, true);
  } catch (error) {
    state.isBusy = false;
    logMini(error.message);
    setMode("listening", "Please say that again.", "Voice is on");
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

elements.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = elements.textInput.value;
  elements.textInput.value = "";
  await sendChat(message, true);
});

elements.micButton.addEventListener("click", toggleVoice);

window.speechSynthesis?.addEventListener?.("voiceschanged", () => {});
checkHealth();
setInterval(checkHealth, 30000);
