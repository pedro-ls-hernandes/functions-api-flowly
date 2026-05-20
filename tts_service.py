from __future__ import annotations

import threading

try:
    import pyttsx3  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    pyttsx3 = None


class TTSService:
    def __init__(self, rate: int = 175, volume: float = 1.0, *, enabled: bool = True) -> None:
        self._enabled = bool(enabled)
        self._engine = pyttsx3.init() if (self._enabled and pyttsx3 is not None) else None
        self._lock = threading.RLock()
        if self._engine is not None:
            self.set_rate(rate)
            self.set_volume(volume)
            self._try_select_pt_br_voice()

    def _try_select_pt_br_voice(self) -> None:
        if self._engine is None:
            return
        try:
            voices = self._engine.getProperty("voices")
        except Exception:
            return

        preferred = None
        for voice in voices or []:
            name = (getattr(voice, "name", "") or "").lower()
            langs = getattr(voice, "languages", []) or []
            langs_str = " ".join([str(x).lower() for x in langs])
            if "pt" in name or "portugu" in name or "pt" in langs_str or "brazil" in name:
                preferred = voice
                if "br" in name or "brazil" in name or "pt_br" in langs_str or "pt-br" in langs_str:
                    break
        if preferred is not None:
            try:
                self._engine.setProperty("voice", preferred.id)
            except Exception:
                pass

    def set_rate(self, rate: int) -> None:
        with self._lock:
            if self._engine is None:
                return
            self._engine.setProperty("rate", int(rate))

    def set_volume(self, volume: float) -> None:
        with self._lock:
            if self._engine is None:
                return
            self._engine.setProperty("volume", float(volume))

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            if self._engine is None:
                return
            self._engine.say(text)
            self._engine.runAndWait()

    def speak_async(self, text: str) -> None:
        threading.Thread(target=self.speak, args=(text,), daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            try:
                if self._engine is not None:
                    self._engine.stop()
            except Exception:
                pass
