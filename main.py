import ast
import ctypes
import datetime
import operator
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from collections import deque
from pathlib import Path

import config as cfg
from spotify_control import SpotifyController
from system_actions import SystemActions
from intents import IntentRouter
from audio_engine import AudioEngine

import numpy as np
import pygame
import requests
import soundfile as sf
import spotipy
from kokoro import KPipeline
from spotipy.oauth2 import SpotifyOAuth

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
    def __init__(self, user=cfg.DEFAULT_USER):
        self.name = cfg.APP_NAME
        self.user = user

        self.voice = cfg.VOICE
        self.pipeline = KPipeline(lang_code="b")

        self.temp_audio_path = Path(tempfile.gettempdir()) / cfg.TEMP_AUDIO_FILENAME
        self.temp_input_path = Path(tempfile.gettempdir()) / cfg.TEMP_INPUT_FILENAME

        self.sample_rate = cfg.SAMPLE_RATE
        self.stt_model_name = cfg.STT_MODEL_NAME
        self.stt_language = cfg.STT_LANGUAGE
        self.whisper_model = None

        self.wakeword_model = None
        self.wakeword_key = None
        self.wakeword_phrase = cfg.WAKEWORD_PHRASE
        self.wakeword_threshold = cfg.WAKEWORD_THRESHOLD
        self.wakeword_cooldown = cfg.WAKEWORD_COOLDOWN

        self.ollama_base_url = cfg.OLLAMA_BASE_URL
        self.ollama_model = cfg.OLLAMA_MODEL
        self.max_history_messages = cfg.MAX_HISTORY_MESSAGES
        self.chat_history = []

        self.spotify_client = None
        self.spotify_scope = cfg.SPOTIFY_SCOPE
        self.spotify_cache_path = str(
            Path(tempfile.gettempdir()) / cfg.SPOTIFY_CACHE_FILENAME
        )

        self._speak_lock = threading.Lock()
        self.conversation_mode_timeout = cfg.CONVERSATION_MODE_TIMEOUT
        self.max_consecutive_silences = cfg.MAX_CONSECUTIVE_SILENCES

        self.exit_phrases = cfg.EXIT_PHRASES.copy()
        self.website_map = cfg.WEBSITE_MAP.copy()
        self.app_map = cfg.APP_MAP.copy()
        self.spotify = SpotifyController(self.app_map)
        self.system_actions = SystemActions(self.website_map, self.app_map)
        self.intent_router = IntentRouter(self.system_actions, self.spotify)


        self.vk_media_play_pause = cfg.VK_MEDIA_PLAY_PAUSE
        self.vk_media_next = cfg.VK_MEDIA_NEXT
        self.vk_media_prev = cfg.VK_MEDIA_PREV
        self.vk_media_stop = cfg.VK_MEDIA_STOP

        self.audio = AudioEngine(self.name, self.voice)

    def speak(self, text):
        self.audio.speak(text)

    def wait_for_wake_word(self):
        self.audio.wait_for_wake_word()

    def listen(self, silence_duration=1.2, max_listen_duration=15, speech_threshold=0.015):
        return self.audio.listen(
            silence_duration=silence_duration,
            max_listen_duration=max_listen_duration,
            speech_threshold=speech_threshold,
        )

    def process_user_input(self, user_text):
        return self.intent_router.process(user_text, self.generate_response)

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

    def should_end_conversation(self, text):
        normalized = (text or "").strip().lower()
        normalized = normalized.replace("’", "'")
        normalized = re.sub(r"[,.!?;:]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        if not normalized:
            return False

        for phrase in self.exit_phrases:
            if phrase in normalized:
                return True

        return False

    def handle_conversation(self):
        consecutive_silences = 0

        self.speak("Yes, I'm listening.")

        while True:
            spoken_text = self.listen(
                silence_duration=1.0,
                max_listen_duration=self.conversation_mode_timeout,
                speech_threshold=0.015,
            )

            if not spoken_text:
                consecutive_silences += 1

                if consecutive_silences >= self.max_consecutive_silences:
                    self.speak("Returning to standby mode, sir.")
                    break

                self.speak("I did not catch that, sir. Please repeat.")
                continue

            consecutive_silences = 0

            if self.should_end_conversation(spoken_text):
                self.speak("Understood. Returning to standby mode, sir.")
                break

            response_text = self.process_user_input(spoken_text)
            self.speak(response_text)

    def standby_loop(self):
        while True:
            self.wait_for_wake_word()
            time.sleep(self.wakeword_cooldown)
            self.handle_conversation()
            self._reset_wakeword_detector()
            time.sleep(self.wakeword_cooldown)

    def _reset_wakeword_detector(self):
        self.audio.reset_wakeword_detector()

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
        self.standby_loop()


if __name__ == "__main__":
    otis = OTIS()

    try:
        otis.run()
    except KeyboardInterrupt:
        print("OTIS: Shutdown requested.")
