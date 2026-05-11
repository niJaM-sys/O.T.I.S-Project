import ctypes
import os
import re
import tempfile
import time
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth

import config as cfg


class SpotifyController:
    def __init__(self, app_map):
        self.app_map = app_map
        self.client = None
        self.scope = cfg.SPOTIFY_SCOPE
        self.cache_path = str(Path(tempfile.gettempdir()) / cfg.SPOTIFY_CACHE_FILENAME)

        self.vk_media_play_pause = cfg.VK_MEDIA_PLAY_PAUSE
        self.vk_media_next = cfg.VK_MEDIA_NEXT
        self.vk_media_prev = cfg.VK_MEDIA_PREV
        self.vk_media_stop = cfg.VK_MEDIA_STOP

    def normalize_text(self, text):
        cleaned = (text or "").strip().lower()
        cleaned = re.sub(r"[,.!?;:]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def handle_command(self, text, open_application_callback):
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
            return self.pause()

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
            return self.resume(open_application_callback)

        if cleaned in {"play music", "play the music"}:
            return self.resume(open_application_callback)

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
            return self.next_track()

        if any(
            phrase in cleaned
            for phrase in [
                "previous song",
                "previous track",
                "go back a song",
                "go back a track",
            ]
        ):
            return self.previous_track()

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
            return self.stop()

        spotify_query = self.extract_query(cleaned)
        if spotify_query:
            return self.play_query(spotify_query, open_application_callback)

        if "open spotify" in cleaned or "launch spotify" in cleaned or "start spotify" in cleaned:
            return open_application_callback("spotify", self.app_map["spotify"])

        return None

    def extract_query(self, text):
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

    def _get_client(self):
        if self.client is None:
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
                scope=self.scope,
                open_browser=True,
                cache_path=self.cache_path,
            )
            self.client = spotipy.Spotify(auth_manager=auth_manager)

        return self.client

    def get_device_id(self):
        sp = self._get_client()
        devices_response = sp.devices()
        devices = devices_response.get("devices", [])

        if not devices:
            return None

        for device in devices:
            if device.get("is_active"):
                return device.get("id")

        return devices[0].get("id")

    def ensure_device(self, open_application_callback):
        device_id = self.get_device_id()
        if device_id:
            return device_id

        open_application_callback("spotify", self.app_map["spotify"])

        for _ in range(12):
            time.sleep(1)
            device_id = self.get_device_id()
            if device_id:
                return device_id

        return None

    def search_item(self, query):
        sp = self._get_client()
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

    def play_query(self, query, open_application_callback):
        try:
            device_id = self.ensure_device(open_application_callback)
            if not device_id:
                return (
                    "I could not find an active Spotify device, sir. "
                    "Please open Spotify fully and try again."
                )

            item = self.search_item(query)
            if item is None or not item.get("uri"):
                return f"I could not find {query} on Spotify, sir."

            sp = self._get_client()

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

    def pause(self):
        try:
            sp = self._get_client()
            device_id = self.get_device_id()
            if device_id:
                sp.pause_playback(device_id=device_id)
                return "Pausing playback, sir."
        except Exception:
            pass

        self._press_media_key(self.vk_media_play_pause)
        return "Pausing playback, sir."

    def resume(self, open_application_callback):
        try:
            sp = self._get_client()
            device_id = self.ensure_device(open_application_callback)
            if device_id:
                sp.start_playback(device_id=device_id)
                return "Resuming playback, sir."
        except Exception:
            pass

        self._press_media_key(self.vk_media_play_pause)
        return "Resuming playback, sir."

    def next_track(self):
        try:
            sp = self._get_client()
            device_id = self.get_device_id()
            if device_id:
                sp.next_track(device_id=device_id)
                return "Skipping to the next track, sir."
        except Exception:
            pass

        self._press_media_key(self.vk_media_next)
        return "Skipping to the next track, sir."

    def previous_track(self):
        try:
            sp = self._get_client()
            device_id = self.get_device_id()
            if device_id:
                sp.previous_track(device_id=device_id)
                return "Returning to the previous track, sir."
        except Exception:
            pass

        self._press_media_key(self.vk_media_prev)
        return "Returning to the previous track, sir."

    def stop(self):
        try:
            sp = self._get_client()
            device_id = self.get_device_id()
            if device_id:
                sp.pause_playback(device_id=device_id)
                return "Stopping playback, sir."
        except Exception:
            pass

        self._press_media_key(self.vk_media_stop)
        return "Stopping playback, sir."

    def _press_media_key(self, virtual_key_code):
        ctypes.windll.user32.keybd_event(virtual_key_code, 0, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(virtual_key_code, 0, 2, 0)
