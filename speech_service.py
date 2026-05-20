from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SpeechResult:
    text: str


class SpeechService:
    def __init__(
        self,
        language: str = "pt-BR",
        listen_timeout: int = 5,
        phrase_time_limit: int = 10,
        sr_energy_threshold: int = 300,
        sr_dynamic_energy: bool = True,
        sr_pause_threshold: float = 0.8,
        sr_non_speaking_duration: float = 0.5,
    ) -> None:
        self.language = language
        self.listen_timeout = listen_timeout
        self.phrase_time_limit = phrase_time_limit
        self._sr_recognizer = None

        self.sr_energy_threshold = int(sr_energy_threshold)
        self.sr_dynamic_energy = bool(sr_dynamic_energy)
        self.sr_pause_threshold = float(sr_pause_threshold)
        self.sr_non_speaking_duration = float(sr_non_speaking_duration)

    def listen_once(self) -> SpeechResult:
        return self._listen_google()

    def _listen_google(self) -> SpeechResult:
        try:
            import speech_recognition as sr
        except ModuleNotFoundError as e:
            if (getattr(e, "name", "") or "").lower() in {"aifc", "audioop"}:
                raise RuntimeError(
                    "SpeechRecognition (engine google) falhou no Python 3.13 por mudanças do Python. "
                    "Use Python 3.11/3.12 para a captura de voz, ou use o fallback por texto."
                ) from e
            raise RuntimeError(
                "Engine google requer o pacote SpeechRecognition. Instale as dependências de voz (ver requirements.txt)."
            ) from e
        except Exception as e:
            raise RuntimeError(
                "Engine google requer o pacote SpeechRecognition. Instale as dependências de voz (ver requirements.txt)."
            ) from e

        if self._sr_recognizer is None:
            self._sr_recognizer = sr.Recognizer()
            self._sr_recognizer.energy_threshold = self.sr_energy_threshold
            self._sr_recognizer.dynamic_energy_threshold = self.sr_dynamic_energy
            self._sr_recognizer.pause_threshold = self.sr_pause_threshold
            self._sr_recognizer.non_speaking_duration = self.sr_non_speaking_duration

        try:
            with sr.Microphone() as source:
                self._sr_recognizer.adjust_for_ambient_noise(source, duration=0.6)
                audio = self._sr_recognizer.listen(
                    source,
                    timeout=self.listen_timeout,
                    phrase_time_limit=self.phrase_time_limit,
                )
            return self._recognize_google(sr, audio)
        except AttributeError:
            pass
        except OSError:
            pass
        except sr.WaitTimeoutError as e:
            raise RuntimeError("Tempo esgotado aguardando fala. Tente novamente.") from e

        try:
            import numpy as np  # noqa: F401
            import sounddevice as sd
        except Exception as e:
            raise RuntimeError(
                "Não consegui acessar o microfone via PyAudio. Instale `pyaudio` OU instale `sounddevice`+`numpy` "
                "para usar o fallback."
            ) from e

        samplerate = 16000
        duration = max(2, int(self.phrase_time_limit))
        try:
            audio_np = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype="int16")
            sd.wait()
        except Exception as e:
            raise RuntimeError("Falha ao gravar áudio via sounddevice. Verifique permissões e o microfone.") from e

        raw = audio_np.tobytes()
        audio = sr.AudioData(raw, samplerate, 2)
        return self._recognize_google(sr, audio)

    def _recognize_google(self, sr, audio) -> SpeechResult:
        try:
            text = self._sr_recognizer.recognize_google(audio, language=self.language)
            return SpeechResult(text=text)
        except sr.UnknownValueError as e:
            raise RuntimeError("Não entendi o que foi dito. Pode repetir?") from e
        except sr.RequestError as e:
            raise RuntimeError("Falha ao chamar o serviço de reconhecimento (Google). Verifique sua internet.") from e

    def listen_text_fallback(self, prompt: str = "Digite o comando: ") -> SpeechResult:
        text = input(prompt)
        return SpeechResult(text=text)
