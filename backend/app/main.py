from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import stats, study, words

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

app.include_router(words.router, prefix="/api")
app.include_router(study.router, prefix="/api")
app.include_router(stats.router, prefix="/api")


@app.get("/api/health", tags=["service"])
def health() -> dict[str, str]:
    return {"status": "ok"}
