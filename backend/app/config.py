from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'app.db'}"

    # Состав учебной сессии: занятие — это 5 слов одной категории
    new_words_per_session: int = 5
    review_words_per_session: int = 5
    daily_new_limit: int = 20
    # Фразы — своя колода со своими лимитами: занятие с фразами не съедает
    # дневной лимит новых слов, и наоборот
    new_phrases_per_session: int = 5
    review_phrases_per_session: int = 5
    daily_new_phrases_limit: int = 20

    # Границы SM-2
    max_interval_days: float = 365.0
    min_ease: float = 1.3
    initial_ease: float = 2.5

    # Классификатор меток. Адрес, ключ и модель — только значения по умолчанию:
    # действующие лежат в таблице `settings` и меняются на вкладке «Разметка»
    classifier_base_url: str = "http://localhost:11434"
    classifier_api_key: str = "ollama"  # Ollama ключ не проверяет, но SDK требует непустой
    classifier_model: str = "nimble"
    # Предел ожидания одной пачки: локальная модель думает над 20 словами десятки секунд
    classifier_timeout_seconds: float = 120.0
    # «Проверить подключение» — один крошечный вопрос, висеть две минуты ему незачем
    classifier_check_timeout_seconds: float = 15.0
    # Больше — одна пачка не укладывается в таймаут на локальной модели
    classifier_batch_max: int = 100

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
