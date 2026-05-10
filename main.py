import datetime
import re
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
import pygame
import requests
import soundfile as sf
from kokoro import KPipeline

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

try:
    import openwakeword
    from openwakeword.model import Model as WakeWordModel
except ImportError:
    openwakeword = None
    WakeWordModel = None


class OTIS:
    def __init__(self, user="sir"):
        self.name = "O.T.I.S"
        self.user = user

        self.voice = "bm_george"
        self.pipeline = KPipeline(lang_code="b")

        self.temp_audio_path = Path(tempfile.gettempdir()) / "temp_otis.wav"
        self.temp_input_path = Path(tempfile.gettempdir()) / "temp_otis_input.wav"

        self.sample_rate = 16000
        self.stt_model_name = "base"
        self.stt_language = None
        self.whisper_model = None

        self.wakeword_model = None
        self.wakeword_key = None
        self.wakeword_phrase = "Hey Jarvis"
        self.wakeword_threshold = 0.5
        self.wakeword_cooldown = 2.5

        self.ollama_base_url = "http://localhost:11434"
        self.ollama_model = "qwen2.5:3b"
        self.max_history_messages = 8
        self.chat_history = []

        self._speak_lock = threading.Lock()

    def speak(self, text):
        text = (text or "").strip()
        if not text:
            return

        self._display_text(text)

        with self._speak_lock:
            self._delete_temp_file_if_present()

            generator = self.pipeline(text, voice=self.voice, speed=1.0)

            audio_written = False
            for _, _, audio in generator:
                sf.write(str(self.temp_audio_path), audio, 24000)
                audio_written = True
                break

            if not audio_written:
                print(f"{self.name}: No audio was generated.")
                return

            try:
                self._play_wav(self.temp_audio_path)
            finally:
                self._delete_temp_file_with_retries(self.temp_audio_path)

    def wait_for_wake_word(self):
        if sd is None:
            raise RuntimeError(
                "Missing dependency: sounddevice. Install it with 'pip install sounddevice'."
            )

        if openwakeword is None or WakeWordModel is None:
            raise RuntimeError(
                "Missing dependency: openwakeword. Install it with 'pip install openwakeword onnxruntime'."
            )

        model = self._get_wakeword_model()

        print(f"{self.name}: Waiting for wake word... Say '{self.wakeword_phrase}'.")

        detected = False
        consecutive_hits = 0

        def callback(indata, frames_count, time_info, status):
            nonlocal detected, consecutive_hits

            pcm = indata[:, 0].copy()
            prediction = model.predict(pcm)

            if self.wakeword_key is None:
                for key in prediction.keys():
                    if "jarvis" in key.lower():
                        self.wakeword_key = key
                        break

            score = 0.0
            if self.wakeword_key is not None:
                score = float(prediction.get(self.wakeword_key, 0.0))

            if score >= self.wakeword_threshold:
                consecutive_hits += 1
            else:
                consecutive_hits = 0

            if consecutive_hits >= 2:
                detected = True
                raise sd.CallbackStop()

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=1280,
            callback=callback,
        ) as stream:
            while stream.active and not detected:
                time.sleep(0.05)

        self._reset_wakeword_detector()
        print(f"{self.name}: Wake word detected.")

    def listen(self, silence_duration=1.2, max_listen_duration=15, speech_threshold=0.015):
        if sd is None:
            raise RuntimeError(
                "Missing dependency: sounddevice. Install it with 'pip install sounddevice'."
            )

        if WhisperModel is None:
            raise RuntimeError(
                "Missing dependency: faster-whisper. Install it with 'pip install faster-whisper'."
            )

        print(f"{self.name}: Listening...")

        frames = []
        pre_roll = deque(maxlen=5)
        speech_started = False
        last_voice_time = None
        stream_start = time.monotonic()

        def callback(indata, frames_count, time_info, status):
            nonlocal speech_started, last_voice_time

            chunk = indata.copy()
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            now = time.monotonic()

            if not speech_started:
                pre_roll.append(chunk)

            if rms >= speech_threshold:
                if not speech_started:
                    speech_started = True
                    frames.extend(pre_roll)
                    pre_roll.clear()
                    print(f"{self.name}: Speech detected.")

                frames.append(chunk)
                last_voice_time = now

            elif speech_started:
                frames.append(chunk)

            if speech_started and last_voice_time is not None:
                if now - last_voice_time >= silence_duration:
                    raise sd.CallbackStop()

            if now - stream_start >= max_listen_duration:
                raise sd.CallbackStop()

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=1024,
            callback=callback,
        ) as stream:
            while stream.active:
                time.sleep(0.05)

        if not frames:
            print(f"{self.name}: No speech detected.")
            return ""

        audio_data = np.concatenate(frames, axis=0)
        sf.write(str(self.temp_input_path), audio_data, self.sample_rate)

        try:
            heard_text = self._transcribe_audio_file(self.temp_input_path)
        finally:
            self._delete_temp_file_with_retries(self.temp_input_path)

        if heard_text:
            print(f"{self.user}: {heard_text}")
        else:
            print(f"{self.name}: No speech detected.")

        return heard_text

    def generate_response(self, user_text):
        user_text = (user_text or "").strip()
        if not user_text:
            return "I did not catch that, sir."

        system_prompt = (
            "You are O.T.I.S., short for Operational Technician for Incompetent Student. "
            "You are a personal AI assistant inspired by J.A.R.V.I.S. "
            "You are calm, intelligent, concise, slightly dry-witted, and helpful. "
            "Keep most answers short and natural for spoken conversation unless the user asks for detail."
        )

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.chat_history[-self.max_history_messages :])
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": False,
            "keep_alive": "10m",
        }

        try:
            response = requests.post(
                f"{self.ollama_base_url}/api/chat",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()

            assistant_text = data.get("message", {}).get("content", "").strip()
            if not assistant_text:
                assistant_text = "I do not have a response at the moment, sir."

            self.chat_history.append({"role": "user", "content": user_text})
            self.chat_history.append({"role": "assistant", "content": assistant_text})
            self.chat_history = self.chat_history[-self.max_history_messages :]

            return assistant_text

        except requests.exceptions.RequestException:
            return (
                "My local language model is not reachable, sir. "
                "Please make sure Ollama is running and the model is installed."
            )

    def _display_text(self, text):
        lines = re.split(r"(?<=[.!?])\s+", text)

        for line in lines:
            cleaned_line = line.strip()
            if cleaned_line:
                print(f"{self.name}: {cleaned_line}")

    def _get_wakeword_model(self):
        if self.wakeword_model is None:
            print(f"{self.name}: Loading wake word model...")
            openwakeword.utils.download_models()
            self.wakeword_model = WakeWordModel(vad_threshold=0.5)

        return self.wakeword_model

    def _reset_wakeword_detector(self):
        if self.wakeword_model is not None:
            try:
                self.wakeword_model.reset()
            except AttributeError:
                pass

    def _get_stt_model(self):
        if self.whisper_model is None:
            print(f"{self.name}: Loading speech recognition model...")
            self.whisper_model = WhisperModel(
                self.stt_model_name,
                device="cpu",
                compute_type="int8",
            )

        return self.whisper_model

    def _transcribe_audio_file(self, audio_path):
        model = self._get_stt_model()
        segments, _ = model.transcribe(
            str(audio_path),
            language=self.stt_language,
            vad_filter=True,
            beam_size=5,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def _play_wav(self, audio_path):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()

            pygame.mixer.music.load(str(audio_path))
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
        finally:
            try:
                pygame.mixer.music.stop()
            except pygame.error:
                pass

            try:
                pygame.mixer.music.unload()
            except (pygame.error, AttributeError):
                pass

            if pygame.mixer.get_init():
                pygame.mixer.quit()

    def _delete_temp_file_if_present(self):
        if self.temp_audio_path.exists():
            self._delete_temp_file_with_retries(self.temp_audio_path)

    @staticmethod
    def _delete_temp_file_with_retries(path, retries=20, delay=0.1):
        for _ in range(retries):
            try:
                if path.exists():
                    path.unlink()
                return
            except PermissionError:
                time.sleep(delay)

        raise PermissionError(f"Could not delete temporary audio file: {path}")

    def boot_system(self):
        hour = datetime.datetime.now().hour

        if 5 <= hour < 12:
            greeting = "Good morning"
        elif 12 <= hour < 18:
            greeting = "Good afternoon"
        elif 18 <= hour < 22:
            greeting = "Good evening"
        else:
            greeting = "Good night"

        message = (
            f"{greeting}, {self.user}. Systems are initializing. "
            "I am currently running on your laptop while awaiting the HP ProDesk deployment."
        )
        self.speak(message)

    def run(self):
        self.boot_system()

        while True:
            self.wait_for_wake_word()
            time.sleep(self.wakeword_cooldown)

            self.speak("Yes, I'm listening.")

            spoken_text = self.listen()

            if spoken_text:
                response_text = self.generate_response(spoken_text)
                self.speak(response_text)
            else:
                self.speak("I did not catch that, sir.")

            self._reset_wakeword_detector()
            time.sleep(self.wakeword_cooldown)


if __name__ == "__main__":
    otis = OTIS()

    try:
        otis.run()
    except KeyboardInterrupt:
        print("OTIS: Shutdown requested.")
