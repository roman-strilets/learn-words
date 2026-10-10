from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db import get_session
from app.decks import PHRASES, WORDS, Deck
from app.models import WordStatus
from app.schemas import DailyStat, StatsOverview
from app.study_service import day_bounds, due_counts


def _count_by_status(session: Session, deck: Deck) -> dict[str, int]:
    Prog = deck.progress
    rows = session.execute(
        select(Prog.status, func.count(Prog.word_id)).group_by(Prog.status)
    ).all()
    return {status: count for status, count in rows}


def _streak(session: Session, today, deck: Deck) -> int:
    """Сколько дней подряд, заканчивая сегодня или вчера, были ответы в колоде."""
    Log = deck.log
    rows = session.scalars(
        select(func.date(Log.created_at)).distinct().order_by(func.date(Log.created_at).desc())
    ).all()
    days = {str(r) for r in rows}
    if not days:
        return 0

    cursor = today
    if cursor.isoformat() not in days:
        cursor -= timedelta(days=1)
        if cursor.isoformat() not in days:
            return 0

    streak = 0
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def make_stats_router(deck: Deck, prefix: str) -> APIRouter:
    """Статистика колоды — только по её таблицам: слова и фразы не суммируются."""
    router = APIRouter(prefix=prefix, tags=[f"{deck.name}-stats"])

    @router.get("/overview", response_model=StatsOverview)
    def overview(session: Session = Depends(get_session)) -> StatsOverview:
        Item, Prog, Log = deck.item, deck.progress, deck.log
        now = utcnow()
        day_start, day_end = day_bounds(now)

        total_words = session.scalar(select(func.count(Item.id))) or 0
        by_status = _count_by_status(session, deck)
        tracked = sum(by_status.values())
        due_now, due_today = due_counts(session, now, deck)

        answers_today = (
            session.scalar(
                select(func.count(Log.id)).where(
                    Log.created_at >= day_start, Log.created_at < day_end
                )
            )
            or 0
        )
        new_today = (
            session.scalar(
                select(func.count(Prog.word_id)).where(
                    Prog.started_at >= day_start, Prog.started_at < day_end
                )
            )
            or 0
        )

        return StatsOverview(
            total_words=total_words,
            new=total_words - tracked,
            learning=by_status.get(WordStatus.LEARNING.value, 0),
            review=by_status.get(WordStatus.REVIEW.value, 0),
            known=by_status.get(WordStatus.KNOWN.value, 0),
            due_now=due_now,
            due_today=due_today,
            answers_today=answers_today,
            new_today=new_today,
            streak_days=_streak(session, now.date(), deck),
        )

    @router.get("/daily", response_model=list[DailyStat])
    def daily(
        days: int = Query(default=30, ge=1, le=365),
        session: Session = Depends(get_session),
    ) -> list[DailyStat]:
        Prog, Log = deck.progress, deck.log
        now = utcnow()
        since = (now - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        answers: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        rows = session.execute(
            select(
                func.date(Log.created_at),
                func.count(Log.id),
                func.sum(cast(Log.correct, Integer)),
            )
            .where(Log.created_at >= since)
            .group_by(func.date(Log.created_at))
        ).all()
        for day, total, correct in rows:
            answers[str(day)] = [total or 0, int(correct or 0)]

        started = dict(
            session.execute(
                select(func.date(Prog.started_at), func.count(Prog.word_id))
                .where(Prog.started_at >= since)
                .group_by(func.date(Prog.started_at))
            ).all()
        )

        result: list[DailyStat] = []
        for offset in range(days):
            day = (since + timedelta(days=offset)).date().isoformat()
            total, correct = answers.get(day, [0, 0])
            result.append(
                DailyStat(
                    date=day,
                    answers=total,
                    correct=correct,
                    accuracy=round(correct / total, 3) if total else 0.0,
                    new_words=int(started.get(day, 0) or 0),
                )
            )
        return result

    return router


router = make_stats_router(WORDS, "/stats")
phrase_stats_router = make_stats_router(PHRASES, "/phrase-stats")
