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
    def __init__(self, user="sir"):
        self.name = "O.T.I.S"
        self.user = user

        self.voice = "bm_george"
        self.pipeline = KPipeline(lang_code="b")

        self.temp_audio_path = Path(tempfile.gettempdir()) / "temp_otis.wav"
        self.temp_input_path = Path(tempfile.gettempdir()) / "temp_otis_input.wav"

        self.sample_rate = 16000
        self.stt_model_name = "small"
        self.stt_language = "en"
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

        self.spotify_client = None
        self.spotify_scope = (
            "user-read-playback-state "
            "user-modify-playback-state "
            "user-read-currently-playing"
        )
        self.spotify_cache_path = str(Path(tempfile.gettempdir()) / "otis_spotify_token_cache")

        self._speak_lock = threading.Lock()
        self.conversation_mode_timeout = 12
        self.max_consecutive_silences = 2

        self.exit_phrases = {
            "goodbye",
            "bye",
            "stop listening",
            "cancel",
            "never mind",
            "thank you",
            "thanks",
            "that's all",
            "that is all",
            "we're done",
            "we are done",
            "all right thank you",
            "alright thank you",
            "ok thank you",
            "okay thank you",
        }

        self.website_map = {
            "youtube": "https://www.youtube.com",
            "github": "https://www.github.com",
            "gmail": "https://mail.google.com",
            "google": "https://www.google.com",
        }

        self.app_map = {
            "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "google chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "browser": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "pycharm": r"C:\Program Files\JetBrains\PyCharm 2025.2.2\bin\pycharm64.exe",
            "python ide": r"C:\Program Files\JetBrains\PyCharm 2025.2.2\bin\pycharm64.exe",
            "pitch arm": r"C:\Program Files\JetBrains\PyCharm 2025.2.2\bin\pycharm64.exe",
            "teach arm": r"C:\Program Files\JetBrains\PyCharm 2025.2.2\bin\pycharm64.exe",
            "jetbrains": r"C:\Program Files\JetBrains\PyCharm 2025.2.2\bin\pycharm64.exe",
            "spotify": r"C:\Users\%USERNAME%\AppData\Roaming\Spotify\Spotify.exe",
            "notepad": "notepad.exe",
            "notes": "notepad.exe",
        }

        self.vk_media_play_pause = 0xB3
        self.vk_media_next = 0xB0
        self.vk_media_prev = 0xB1
        self.vk_media_stop = 0xB2

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

    def process_user_input(self, user_text):
        direct_response = self.handle_direct_intent(user_text)
        if direct_response is not None:
            return direct_response

        return self.generate_response(user_text)

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
        normalized = self.normalize_text(text)
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

    def normalize_text(self, text):
        cleaned = (text or "").strip().lower()
        cleaned = re.sub(r"[,.!?;:]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def handle_direct_intent(self, user_text):
        normalized = self.normalize_text(user_text)
        if not normalized:
            return "I did not catch that, sir."

        spotify_result = self.handle_spotify_command(normalized)
        if spotify_result is not None:
            return spotify_result

        open_result = self.handle_open_command(normalized)
        if open_result is not None:
            return open_result

        if self.is_date_question(normalized):
            return self.get_date_response()

        if self.is_time_question(normalized):
            return self.get_time_response()

        if self.is_weather_question(normalized):
            return (
                "I do not have a weather module yet, sir. "
                "For now, please check a reliable weather app or website."
            )

        math_expression = self.extract_math_expression(normalized)
        if math_expression is not None:
            result = self.safe_eval_math_expression(math_expression)
            if result is not None:
                if isinstance(result, float) and result.is_integer():
                    result = int(result)
                return str(result)

        return None

    def handle_spotify_command(self, text):
        cleaned = self.normalize_text(text)

        spotify_control_phrases = [
            "pause music",
            "pause the music",
            "pause song",
            "pause the song",
            "pause playback",
            "pause spotify",
            "resume music",
            "resume the music",
            "resume song",
            "resume the song",
            "resume playback",
            "resume spotify",
            "continue music",
            "continue the music",
            "continue song",
            "continue the song",
            "continue playback",
            "keep playing",
            "keep the music playing",
            "play music",
            "play the music",
            "next song",
            "next track",
            "skip song",
            "skip track",
            "skip this song",
            "skip this track",
            "previous song",
            "previous track",
            "go back a song",
            "go back a track",
            "stop music",
            "stop the music",
            "stop song",
            "stop playback",
            "stop spotify",
        ]

        if "spotify" not in cleaned and not any(
                phrase in cleaned for phrase in spotify_control_phrases
        ):
            return None

        if any(
                phrase in cleaned
                for phrase in [
                    "pause music",
                    "pause the music",
                    "pause song",
                    "pause the song",
                    "pause playback",
                    "pause spotify",
                ]
        ):
            return self.pause_spotify()

        if any(
                phrase in cleaned
                for phrase in [
                    "resume music",
                    "resume the music",
                    "resume song",
                    "resume the song",
                    "resume playback",
                    "resume spotify",
                    "continue music",
                    "continue the music",
                    "continue song",
                    "continue the song",
                    "continue playback",
                    "keep playing",
                    "keep the music playing",
                ]
        ):
            return self.resume_spotify()

        if cleaned in {"play music", "play the music"}:
            return self.resume_spotify()

        if any(
                phrase in cleaned
                for phrase in [
                    "next song",
                    "next track",
                    "skip song",
                    "skip track",
                    "skip this song",
                    "skip this track",
                ]
        ):
            return self.next_spotify_track()

        if any(
                phrase in cleaned
                for phrase in [
                    "previous song",
                    "previous track",
                    "go back a song",
                    "go back a track",
                ]
        ):
            return self.previous_spotify_track()

        if any(
                phrase in cleaned
                for phrase in [
                    "stop music",
                    "stop the music",
                    "stop song",
                    "stop playback",
                    "stop spotify",
                ]
        ):
            return self.stop_spotify()

        spotify_query = self.extract_spotify_query(cleaned)
        if spotify_query:
            return self.play_on_spotify(spotify_query)

        if "open spotify" in cleaned or "launch spotify" in cleaned or "start spotify" in cleaned:
            return self.open_application("spotify", self.app_map["spotify"])

        return None

    def extract_spotify_query(self, text):
        cleaned = self.normalize_text(text)
        cleaned = cleaned.replace("please", " ")
        cleaned = cleaned.replace("could you", " ")
        cleaned = cleaned.replace("can you", " ")
        cleaned = cleaned.replace("would you", " ")
        cleaned = cleaned.replace("for me", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        patterns = [
            r"play (.+) on spotify",
            r"play (.+) using spotify",
            r"play (.+) with spotify",
            r"open spotify and play (.+)",
            r"launch spotify and play (.+)",
            r"start spotify and play (.+)",
            r"spotify play (.+)",
            r"put on (.+) on spotify",
            r"put on (.+) using spotify",
            r"search spotify for (.+)",
            r"look up (.+) on spotify",
            r"find (.+) on spotify",
            r"i want to hear (.+) on spotify",
            r"i want to listen to (.+) on spotify",
            r"listen to (.+) on spotify",
        ]

        for pattern in patterns:
            match = re.search(pattern, cleaned)
            if match:
                query = match.group(1).strip()
                if query:
                    return query

        return None

    def _get_spotify_client(self):
        if self.spotify_client is None:
            client_id = os.getenv("SPOTIPY_CLIENT_ID")
            client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
            redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")

            if not client_id or not client_secret or not redirect_uri:
                raise RuntimeError(
                    "Spotify environment variables are missing. "
                    "Please set SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and SPOTIPY_REDIRECT_URI."
                )

            auth_manager = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=self.spotify_scope,
                open_browser=True,
                cache_path=self.spotify_cache_path,
            )
            self.spotify_client = spotipy.Spotify(auth_manager=auth_manager)

        return self.spotify_client

    def get_spotify_device_id(self):
        sp = self._get_spotify_client()
        devices_response = sp.devices()
        devices = devices_response.get("devices", [])

        if not devices:
            return None

        for device in devices:
            if device.get("is_active"):
                return device.get("id")

        return devices[0].get("id")

    def ensure_spotify_device(self):
        device_id = self.get_spotify_device_id()
        if device_id:
            return device_id

        self.open_application("spotify", self.app_map["spotify"])

        for _ in range(12):
            time.sleep(1)
            device_id = self.get_spotify_device_id()
            if device_id:
                return device_id

        return None

    def search_spotify_item(self, query):
        sp = self._get_spotify_client()
        results = sp.search(q=query, type="track,album,playlist", limit=5)

        tracks = results.get("tracks", {}).get("items", [])
        albums = results.get("albums", {}).get("items", [])
        playlists = results.get("playlists", {}).get("items", [])

        if tracks:
            track = tracks[0]
            return {
                "kind": "track",
                "name": track.get("name", query),
                "uri": track.get("uri"),
            }

        if albums:
            album = albums[0]
            return {
                "kind": "album",
                "name": album.get("name", query),
                "uri": album.get("uri"),
            }

        if playlists:
            playlist = playlists[0]
            return {
                "kind": "playlist",
                "name": playlist.get("name", query),
                "uri": playlist.get("uri"),
            }

        return None

    def play_on_spotify(self, query):
        try:
            device_id = self.ensure_spotify_device()
            if not device_id:
                return (
                    "I could not find an active Spotify device, sir. "
                    "Please open Spotify fully and try again."
                )

            item = self.search_spotify_item(query)
            if item is None or not item.get("uri"):
                return f"I could not find {query} on Spotify, sir."

            sp = self._get_spotify_client()

            try:
                sp.transfer_playback(device_id=device_id, force_play=False)
                time.sleep(0.5)
            except Exception:
                pass

            if item["kind"] == "track":
                sp.start_playback(device_id=device_id, uris=[item["uri"]])
            else:
                sp.start_playback(device_id=device_id, context_uri=item["uri"])

            return f"Playing {item['name']} on Spotify, sir."
        except Exception:
            return f"I was unable to start Spotify playback for {query}, sir."

    def pause_spotify(self):
        try:
            sp = self._get_spotify_client()
            device_id = self.ensure_spotify_device()
            if device_id:
                sp.pause_playback(device_id=device_id)
                return "Pausing playback, sir."
        except Exception:
            pass

        self.press_media_key(self.vk_media_play_pause)
        return "Pausing playback, sir."

    def resume_spotify(self):
        try:
            sp = self._get_spotify_client()
            device_id = self.ensure_spotify_device()
            if device_id:
                sp.start_playback(device_id=device_id)
                return "Resuming playback, sir."
        except Exception:
            pass

        self.press_media_key(self.vk_media_play_pause)
        return "Resuming playback, sir."

    def next_spotify_track(self):
        try:
            sp = self._get_spotify_client()
            device_id = self.ensure_spotify_device()
            if device_id:
                sp.next_track(device_id=device_id)
                return "Skipping to the next track, sir."
        except Exception:
            pass

        self.press_media_key(self.vk_media_next)
        return "Skipping to the next track, sir."

    def previous_spotify_track(self):
        try:
            sp = self._get_spotify_client()
            device_id = self.ensure_spotify_device()
            if device_id:
                sp.previous_track(device_id=device_id)
                return "Returning to the previous track, sir."
        except Exception:
            pass

        self.press_media_key(self.vk_media_prev)
        return "Returning to the previous track, sir."

    def stop_spotify(self):
        try:
            sp = self._get_spotify_client()
            device_id = self.ensure_spotify_device()
            if device_id:
                sp.pause_playback(device_id=device_id)
                return "Stopping playback, sir."
        except Exception:
            pass

        self.press_media_key(self.vk_media_stop)
        return "Stopping playback, sir."

    def press_media_key(self, virtual_key_code):
        ctypes.windll.user32.keybd_event(virtual_key_code, 0, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(virtual_key_code, 0, 2, 0)

    def handle_open_command(self, text):
        open_verbs = [
            "open ",
            "launch ",
            "start ",
            "run ",
            "show ",
            "go to ",
            "take me to ",
        ]

        if not any(verb in text for verb in open_verbs):
            return None

        for site_name, url in self.website_map.items():
            if site_name in text:
                return self.open_website(site_name, url)

        for app_name, app_path in self.app_map.items():
            if app_name in text:
                return self.open_application(app_name, app_path)

        return "I do not recognize that application or website yet, sir."

    def open_website(self, site_name, url):
        try:
            webbrowser.open(url)
            return f"Opening {site_name}, sir."
        except Exception:
            return f"I was unable to open {site_name}, sir."

    def open_application(self, app_name, app_path):
        try:
            expanded_path = os.path.expandvars(app_path)

            if app_path.endswith(".exe"):
                subprocess.Popen([expanded_path])
            else:
                subprocess.Popen([app_path])

            return f"Opening {app_name}, sir."
        except FileNotFoundError:
            return f"I could not find {app_name} on this system, sir."
        except Exception:
            return f"I was unable to open {app_name}, sir."

    def is_date_question(self, text):
        patterns = [
            "what day is it",
            "what s the date",
            "what is the date",
            "today s date",
            "what day are we",
            "what day are we today",
            "what day is today",
            "tell me the date",
        ]
        return any(pattern in text for pattern in patterns)

    def is_time_question(self, text):
        patterns = [
            "what time is it",
            "what s the time",
            "what is the time",
            "current time",
            "time now",
            "tell me the time",
        ]
        return any(pattern in text for pattern in patterns)

    def is_weather_question(self, text):
        keywords = [
            "weather",
            "temperature",
            "forecast",
            "is it raining",
            "is it sunny",
            "is it cold",
            "is it hot",
        ]
        return any(keyword in text for keyword in keywords)

    def get_date_response(self):
        now = datetime.datetime.now()
        return now.strftime("Today is %A, %B %d, %Y, sir.")

    def get_time_response(self):
        now = datetime.datetime.now()
        return now.strftime("It is %H:%M, sir.")

    def extract_math_expression(self, text):
        if not any(char.isdigit() for char in text):
            return None

        expression = text

        replacements = {
            "what is": "",
            "what s": "",
            "calculate": "",
            "compute": "",
            "how much is": "",
            "plus": "+",
            "minus": "-",
            "multiplied by": "*",
            "times": "*",
            "x": "*",
            "divided by": "/",
            "over": "/",
        }

        for old, new in replacements.items():
            expression = expression.replace(old, new)

        expression = re.sub(r"[^0-9+\-*/(). ]", " ", expression)
        expression = re.sub(r"\s+", " ", expression).strip()

        if not expression:
            return None

        if not any(op in expression for op in "+-*/"):
            return None

        return expression

    def safe_eval_math_expression(self, expression):
        allowed_operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.USub: operator.neg,
        }

        def evaluate_node(node):
            if isinstance(node, ast.Expression):
                return evaluate_node(node.body)

            if isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float)):
                    return node.value
                raise ValueError("Invalid constant")

            if isinstance(node, ast.Num):
                return node.n

            if isinstance(node, ast.BinOp):
                if type(node.op) not in allowed_operators:
                    raise ValueError("Operator not allowed")
                left = evaluate_node(node.left)
                right = evaluate_node(node.right)
                return allowed_operators[type(node.op)](left, right)

            if isinstance(node, ast.UnaryOp):
                if type(node.op) not in allowed_operators:
                    raise ValueError("Unary operator not allowed")
                operand = evaluate_node(node.operand)
                return allowed_operators[type(node.op)](operand)

            raise ValueError("Unsupported expression")

        try:
            parsed = ast.parse(expression, mode="eval")
            return evaluate_node(parsed)
        except Exception:
            return None

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
                compute_type="float32",
            )

        return self.whisper_model

    def _transcribe_audio_file(self, audio_path):
        model = self._get_stt_model()

        segments, _ = model.transcribe(
            str(audio_path),
            language=self.stt_language,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            beam_size=5,
            temperature=0.0,
            condition_on_previous_text=False,
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
        self.standby_loop()


if __name__ == "__main__":
    otis = OTIS()

    try:
        otis.run()
    except KeyboardInterrupt:
        print("OTIS: Shutdown requested.")
