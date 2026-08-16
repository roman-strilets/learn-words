from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db import get_session
from app.models import Progress, ReviewLog, Word, WordStatus
from app.schemas import DailyStat, StatsOverview
from app.study_service import day_bounds, due_counts

router = APIRouter(prefix="/stats", tags=["stats"])


def _count_by_status(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(Progress.status, func.count(Progress.word_id)).group_by(Progress.status)
    ).all()
    return {status: count for status, count in rows}


def _streak(session: Session, today) -> int:
    """Сколько дней подряд, заканчивая сегодня или вчера, были ответы."""
    rows = session.scalars(
        select(func.date(ReviewLog.created_at))
        .distinct()
        .order_by(func.date(ReviewLog.created_at).desc())
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


@router.get("/overview", response_model=StatsOverview)
def overview(session: Session = Depends(get_session)) -> StatsOverview:
    now = utcnow()
    day_start, day_end = day_bounds(now)

    total_words = session.scalar(select(func.count(Word.id))) or 0
    by_status = _count_by_status(session)
    tracked = sum(by_status.values())
    due_now, due_today = due_counts(session, now)

    answers_today = (
        session.scalar(
            select(func.count(ReviewLog.id)).where(
                ReviewLog.created_at >= day_start, ReviewLog.created_at < day_end
            )
        )
        or 0
    )
    new_today = (
        session.scalar(
            select(func.count(Progress.word_id)).where(
                Progress.started_at >= day_start, Progress.started_at < day_end
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
        streak_days=_streak(session, now.date()),
    )


@router.get("/daily", response_model=list[DailyStat])
def daily(
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
) -> list[DailyStat]:
    now = utcnow()
    since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    answers: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    rows = session.execute(
        select(
            func.date(ReviewLog.created_at),
            func.count(ReviewLog.id),
            func.sum(cast(ReviewLog.correct, Integer)),
        )
        .where(ReviewLog.created_at >= since)
        .group_by(func.date(ReviewLog.created_at))
    ).all()
    for day, total, correct in rows:
        answers[str(day)] = [total or 0, int(correct or 0)]

    started = dict(
        session.execute(
            select(func.date(Progress.started_at), func.count(Progress.word_id))
            .where(Progress.started_at >= since)
            .group_by(func.date(Progress.started_at))
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
