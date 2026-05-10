import datetime
import tempfile
import threading
import time
from pathlib import Path

import pygame
import soundfile as sf
from kokoro import KPipeline


class OTIS:
    def __init__(self, user="sir"):
        self.name = "O.T.I.S"
        self.user = user

        self.voice = "bm_george"
        self.pipeline = KPipeline(lang_code="b")
        self.temp_audio_path = Path(tempfile.gettempdir()) / "temp_otis.wav"
        self._speak_lock = threading.Lock()

    def speak(self, text):
        text = (text or "").strip()
        if not text:
            return

        print(f"{self.name}: {text}")

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


if __name__ == "__main__":
    otis = OTIS()
    otis.boot_system()