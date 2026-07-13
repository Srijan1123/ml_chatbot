# Voice Quality Notes

This file tracks the speech problems we observed while testing the receptionist assistant, plus safer fixes to try later. The goal is to improve reliability without making the assistant ignore natural short questions.

## Current Stack

- LLM: Qwen3-1.7B-GGUF through Lemonade.
- STT: faster-whisper-small.en on CUDA int8_float16.
- TTS: Kokoro female voice `af_heart` on CPU.
- Future avatar: Wav2Lip on GPU.

## Problems Observed

### 1. False Speech From Noise

The mic sometimes captures room noise or background sound and Whisper turns it into plausible text.

Examples seen during testing:

- `with`
- `and join the men again`
- `It feels like it's a creeper`

Risk:

- The chatbot answers nonsense input as if the user asked a real question.
- The conversation history becomes polluted with random turns.
- The receptionist may sound confused or overly chatty.

### 2. Nepali Names And Local Terms Are Misheard

Names and local phrasing can be misrecognized.

Example:

- User said: `Ravi sir`
- STT heard something like: `rubbish`

Risk:

- The assistant may insult or misunderstand people accidentally.
- Local staff names, teacher names, and Nepali-style honorifics like `sir`, `ma'am`, or names such as `Ravi`, `Sita`, `Ramesh`, etc. may be unreliable without a custom lexicon.

### 3. BCA-IT And Acronyms Are Misheard

Course names and acronyms are hard for STT.

Examples seen:

- `BCA-IT` heard as `PCA`
- `BCA-IT` heard as `BCAID`
- `BCAIT` not normalized to `BCA-IT`

Risk:

- The assistant says it does not know the course even when the user asked about a known program.
- Users may repeat themselves and lose trust.

### 4. Short Utterances Are Ambiguous

Short text can be either valid or noise.

Valid examples:

- `Who are you?`
- `How are you?`
- `Ravi sir`
- `BCAIT`
- `Fees?`

Invalid/noisy examples:

- `with`
- `the`
- `again`

Conclusion:

- Do not use a simple rule like "ignore anything under 3 words." It would block real questions and corrections.

### 5. Assistant Voice May Trigger The Mic

If the assistant speaks while the mic is active, the STT may hear the TTS output or room echo.

Risk:

- Feedback loops.
- Random follow-up questions created from the assistant's own voice.
- Extra latency while the system processes accidental recordings.

### 6. Latency Versus Accuracy Tradeoff

Lower silence thresholds make the assistant feel faster but increase false captures.

Higher thresholds reduce noise but make the assistant feel slow.

Current tuning needs a balance between:

- fast endpoint detection,
- enough speech duration to avoid noise,
- enough silence after speech to avoid cutting off the user.

### 7. Laughter Or Non-Speech Heard As Words

During testing, laughter/background audio was sometimes transcribed as normal speech such as:

- `Thank you`

Risk:

- The assistant may respond to people who were not speaking to it.
- Courtesy phrases like `thank you` are valid when spoken clearly, so they should not be blindly blocked.

Mitigation:

- Use Whisper confidence metadata.
- Reject short/courtesy transcripts only when audio confidence is weak, for example high no-speech probability or poor average log probability.
- Keep valid short questions such as `Who are you?` and clear spoken `Thank you`.

### 8. LLM Hallucinated College Name

The assistant once expanded KCC incorrectly as `Karnataka College of Co-Op`.

Correct fact:

- KCC means Kantipur City College.
- The college is in Kathmandu, Nepal.

Risk:

- Even with correct retrieval, the LLM may invent a familiar-looking acronym expansion.

Mitigation:

- Pin the official identity in the system prompt.
- Ban invented KCC expansions.
- Add output cleanup for known wrong expansions.
- Avoid falling back to general chat for college questions when document retrieval fails.

### 9. Emoji Output Gets Spoken By TTS

The assistant sometimes returned emojis, and TTS tried to speak or vocalize them.

Mitigation:

- Explicitly ban emojis in the system prompt.
- Strip emoji characters from model output before sending it to the UI/TTS.

### 10. BCA-IT Retrieval Can Differ From BCA

`BCA` may retrieve the correct context while `BCA-IT` can fail if punctuation or acronym variants do not match the index well.

Mitigation:

- Normalize `BCAIT`, `BCA IT`, `BCAID`, and `BCA-IT` to canonical `BCA-IT`.
- Add BCA-IT variants to Whisper initial prompt.
- Add BCA-IT variants to college intent keywords.
- Probe retrieval when a course query returns `I don't know from the document`.

## Better Fixes Than A Hard Word Count Filter

### 1. Intent-Aware Short Utterance Filter

Short utterances should be allowed when they look meaningful.

Allow short inputs if they match:

- common questions: `who are you`, `how are you`, `what now`, `why`
- known college terms: `BCA`, `BCAIT`, `BCA-IT`, `BBA`, `BBS`, `BASW`
- staff/name patterns: `Ravi sir`, `Sita ma'am`
- commands: `stop`, `repeat`, `yes`, `no`, `again`

Reject short inputs only when they are low-value filler words and have weak confidence:

- `with`
- `the`
- `and`
- `again`
- `uh`
- `hmm`

### 2. Domain Lexicon And Correction Layer

Create a small correction map before sending STT text to the LLM.

Examples:

- `BCAID` -> `BCA-IT`
- `BCA IT` -> `BCA-IT`
- `BCAIT` -> `BCA-IT`
- `PCA course` -> maybe `BCA-IT course` only when the user is asking about college programs.
- `rubbish sir` -> maybe `Ravi sir` only if `Ravi` exists in a staff/name list.

Important:

- Corrections should be contextual, not blind replacements.
- A staff/name list from the college data would make this much safer.

### 3. Whisper Initial Prompt

Use faster-whisper's `initial_prompt` to bias STT toward expected terms.

Useful prompt terms:

- KCC
- BCA-IT
- BBA
- BBS
- BASW
- Ravi sir
- admission
- eligibility
- semester
- scholarship
- faculty

This may improve acronyms and local names without changing models.

### 4. Confidence And No-Speech Filtering

Use Whisper segment metadata where possible:

- average log probability,
- no-speech probability,
- compression ratio,
- duration,
- number of words,
- known keyword presence.

Better policy:

- Reject likely noise when confidence is weak and the transcript has no domain or conversational value.
- Ask for clarification when the transcript is uncertain but could be important.

Example clarification:

> Did you mean BCA-IT?

### 5. Pause Listening During Assistant Speech

Voice activity detection should pause while the assistant is speaking and resume after playback ends.

This prevents:

- echo capture,
- assistant self-transcription,
- extra accidental turns.

### 6. Push-To-Talk Fallback

Always-on voice is hard in noisy rooms.

Keep always-on mode, but add a push-to-talk mode for reliable testing and demos.

Push-to-talk helps when:

- the room is noisy,
- the user has an accent the model struggles with,
- the assistant is near speakers,
- Wav2Lip audio is playing loudly.

## Future Problems To Expect

### 1. Code-Switching

Users may mix English and Nepali words. English-only `small.en` may struggle with Nepali words and names.

Possible future test:

- Compare `faster-whisper-small.en` with multilingual `faster-whisper-small` for Nepali names and mixed speech.

### 2. Wav2Lip GPU Contention

When Wav2Lip is added, it will compete with STT for GPU.

Mitigation:

- Keep LLM in RAM/CPU.
- Keep TTS on CPU.
- Run Wav2Lip only during response playback.
- Avoid loading Qwen TTS on GPU.

### 3. Long Conversation History Pollution

False transcripts can enter chat history and influence future answers.

Mitigation:

- Do not add rejected/uncertain transcripts to conversation history.
- Add a "clarification" state instead of immediately sending uncertain STT to the LLM.

### 4. Microphone And Room Differences

Settings that work on one mic may fail on another.

Mitigation:

- Add calibration UI or automatic ambient noise measurement.
- Adjust VAD threshold based on room noise.

### 5. Acronym Pronunciation Variants

Users may say:

- `BCAIT`
- `BCA I T`
- `BCA-IT`
- `BCA IT course`

Mitigation:

- Normalize known course/program names after STT.
- Store canonical names in one dictionary.

## Recommended Next Implementation

1. Add a domain lexicon file for programs, staff names, and common college terms.
2. Add STT post-processing:
   - normalize BCA-IT variants,
   - correct known staff names carefully,
   - reject only obvious low-value noise.
3. Add Whisper `initial_prompt`.
4. Pause mic monitoring while assistant audio is playing.
5. Add clarification behavior for uncertain transcripts instead of sending them directly to the LLM.
6. Add push-to-talk mode for noisy demos.
