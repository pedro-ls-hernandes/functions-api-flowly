from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    # Optional; se vazio, o mock usa "admin"
    user_type: str = os.getenv("FLOWLY_USER_TYPE", "admin").strip().lower()  # admin|user

    # "Usuário logado" no mock. Se informado, o assistente usa esse _id como identidade.
    # Se não existir no mock_data.json, o mock cria um usuário mínimo com esse _id.
    me_user_id: str = os.getenv("FLOWLY_ME_USER_ID", "").strip()
    text_only: bool = _get_bool("FLOWLY_TEXT_ONLY", False)
    tts_enabled: bool = _get_bool("FLOWLY_TTS_ENABLED", True)

    mock_data_path: str = os.getenv("FLOWLY_MOCK_DATA_PATH", "mock_data.json").strip()

    language: str = os.getenv("FLOWLY_LANGUAGE", "pt-BR")
    listen_timeout: int = int(os.getenv("FLOWLY_LISTEN_TIMEOUT", "5"))
    phrase_time_limit: int = int(os.getenv("FLOWLY_PHRASE_TIME_LIMIT", "10"))

    sr_energy_threshold: int = int(os.getenv("FLOWLY_SR_ENERGY_THRESHOLD", "300"))
    sr_dynamic_energy: bool = os.getenv("FLOWLY_SR_DYNAMIC_ENERGY", "True").lower() == "true"
    sr_pause_threshold: float = float(os.getenv("FLOWLY_SR_PAUSE_THRESHOLD", "0.8"))
    sr_non_speaking_duration: float = float(os.getenv("FLOWLY_SR_NON_SPEAKING_DURATION", "0.5"))

    match_threshold: int = int(os.getenv("FLOWLY_MATCH_THRESHOLD", "78"))

    tts_rate: int = int(os.getenv("FLOWLY_TTS_RATE", "175"))
    tts_volume: float = float(os.getenv("FLOWLY_TTS_VOLUME", "1.0"))

    def validate(self) -> None:
        # Mock: não exige token nem backend
        return


def get_settings() -> Settings:
    settings = Settings()
    settings.validate()
    return settings
