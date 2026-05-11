APP_NAME = "O.T.I.S"
DEFAULT_USER = "sir"
VOICE = "bm_george"

TEMP_AUDIO_FILENAME = "temp_otis.wav"
TEMP_INPUT_FILENAME = "temp_otis_input.wav"

SAMPLE_RATE = 16000
STT_MODEL_NAME = "small"
STT_LANGUAGE = "en"

WAKEWORD_PHRASE = "Hey Jarvis"
WAKEWORD_THRESHOLD = 0.5
WAKEWORD_COOLDOWN = 2.5

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:3b"
MAX_HISTORY_MESSAGES = 8

SPOTIFY_SCOPE = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing"
)
SPOTIFY_CACHE_FILENAME = "otis_spotify_token_cache"

CONVERSATION_MODE_TIMEOUT = 12
MAX_CONSECUTIVE_SILENCES = 2

EXIT_PHRASES = {
    "goodbye",
    "bye",
    "see you",
    "see you later",
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

WEBSITE_MAP = {
    "youtube": "https://www.youtube.com",
    "github": "https://www.github.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
}

APP_MAP = {
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

VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1
VK_MEDIA_STOP = 0xB2
