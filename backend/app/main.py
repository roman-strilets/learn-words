from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import group_study, labels, stats, study, word_import, words
from app.routers import settings as settings_router

app = FastAPI(
    title="Learn Words API",
    description="Изучение английских слов с интервальными повторениями",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раньше `words.router`: `/words/import` не должен даже пробоваться как `/words/{word_id}`
app.include_router(word_import.router, prefix="/api")
app.include_router(words.router, prefix="/api")
app.include_router(study.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(labels.router, prefix="/api")
# Фразы — отдельная колода под своими префиксами, с теми же схемами ответов
app.include_router(words.phrases_router, prefix="/api")
app.include_router(study.phrase_study_router, prefix="/api")
app.include_router(stats.phrase_stats_router, prefix="/api")
app.include_router(labels.phrase_labels_router, prefix="/api")
# Занятие по группе — слова одной метки, отдельно от расписания и статистики
app.include_router(group_study.router, prefix="/api")
# Роутер настроек импортирован под другим именем: `settings` здесь уже занято конфигом
app.include_router(settings_router.router, prefix="/api")


@app.get("/api/health", tags=["service"])
def health() -> dict[str, str]:
    return {"status": "ok"}
