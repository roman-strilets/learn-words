"""Круг группы: какие слова метки войдут в порцию занятия.

Круг — один проход по всем словам метки в зафиксированном порядке. Порции
берут непройденные слова круга по порядку; когда остатка меньше порции,
она добирается первыми словами следующего круга, а следующий круг идёт в
другом порядке (`order_round`, как раунды занятия). Порядок следующего круга
выбирается один раз и хранится: прерванное и повторно начатое занятие получает
ту же порцию, а не новое перемешивание (FR-012a).

Строки слов, с которых сняли метку, не удаляются, а только не учитываются:
вернётся метка — вернётся и место слова в круге (research R5).

Модуль чистый: ни базы, ни часов, `rng` — параметром. На входе — члены группы и
строки круга метки, на выходе — план: слова порции, строки к вставке и круг,
ниже которого строки удаляются. Применяет план `group_study_service.py`.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.exercises import order_round


@dataclass(frozen=True)
class CycleEntry:
    """Строка круга: место слова в круге и пройдено ли оно в нём."""

    word_id: int
    cycle: int
    position: int
    done: bool


@dataclass(frozen=True)
class PortionPlan:
    word_ids: list[int]
    inserts: list[CycleEntry] = field(default_factory=list)
    # Удалить строки кругов меньше этого номера; None — удалять нечего
    delete_below: int | None = None
    # Текущий круг после сборки; 0 — круга нет (в группе нет слов)
    cycle: int = 0


class _Cycles:
    """Строки круга метки по номерам кругов — рабочая копия, в которую план
    дописывает свои вставки, чтобы следующие шаги их видели."""

    def __init__(self, members: Sequence[int], entries: Sequence[CycleEntry]) -> None:
        self.members = list(dict.fromkeys(members))
        self.member_set = set(self.members)
        self.rows: dict[int, dict[int, CycleEntry]] = {}
        for e in entries:
            self.rows.setdefault(e.cycle, {})[e.word_id] = e
        self.inserts: list[CycleEntry] = []

    def member_rows(self, cycle: int) -> list[CycleEntry]:
        rows = self.rows.get(cycle, {})
        return sorted(
            (e for e in rows.values() if e.word_id in self.member_set),
            key=lambda e: (e.position, e.word_id),
        )

    def exists(self, cycle: int) -> bool:
        return bool(self.member_rows(cycle))

    def order(self, cycle: int) -> list[int]:
        return [e.word_id for e in self.member_rows(cycle)]

    def undone(self, cycle: int) -> list[int]:
        return [e.word_id for e in self.member_rows(cycle) if not e.done]

    def current(self) -> int | None:
        """Наименьший круг с непройденным словом группы; если такого нет —
        последний круг, пройденный целиком; None — по группе не занимались."""
        undone = [c for c in self.rows if self.undone(c)]
        if undone:
            return min(undone)
        with_members = [c for c in self.rows if self.exists(c)]
        return max(with_members) if with_members else None

    def complete(self, cycle: int) -> bool:
        """Пройдено ли в круге каждое слово группы. Слово без строки в круге
        (метку поставили позже) считается непройденным."""
        done = {e.word_id for e in self.member_rows(cycle) if e.done}
        return done >= self.member_set

    def _add(self, cycle: int, word_ids: Sequence[int]) -> None:
        rows = self.rows.setdefault(cycle, {})
        start = max((e.position for e in rows.values()), default=-1) + 1
        for offset, word_id in enumerate(word_ids):
            entry = CycleEntry(word_id, cycle, start + offset, False)
            rows[word_id] = entry
            self.inserts.append(entry)

    def create(self, cycle: int, rng: random.Random) -> None:
        """Новый круг по всем словам группы, не похожий на предыдущий круг."""
        previous = self.order(cycle - 1) or None
        last = previous[-1] if previous else None
        self._add(cycle, order_round(self.members, previous, last, rng))

    def append_missing(self, cycle: int, rng: random.Random) -> None:
        """Слова группы без строки в круге — в его конец, в случайном порядке."""
        present = self.rows.get(cycle, {})
        missing = [m for m in self.members if m not in present]
        rng.shuffle(missing)
        self._add(cycle, missing)

    def delete_below(self, cycle: int) -> int | None:
        return cycle if any(c < cycle for c in self.rows) else None


def plan_portion(
    members: Sequence[int],
    entries: Sequence[CycleEntry],
    size: int,
    rng: random.Random,
) -> PortionPlan:
    """Порция занятия по группе: до `size` слов по правилам data-model.md
    («Переходы при сборке порции»)."""
    cycles = _Cycles(members, entries)
    if not cycles.members:
        return PortionPlan(word_ids=[])

    current = cycles.current()
    if current is None:
        current = max(cycles.rows, default=0) + 1
        cycles.create(current, rng)
    elif cycles.complete(current):
        current += 1
        if not cycles.exists(current):
            cycles.create(current, rng)

    cycles.append_missing(current, rng)
    following = current + 1
    if cycles.exists(following):
        cycles.append_missing(following, rng)

    portion = cycles.undone(current)[:size]

    # Стык кругов: остаток короче порции — добор из следующего круга.
    # Слова остатка пропускаются: в одной порции слово бывает только раз
    if len(portion) < size and len(cycles.members) > len(portion):
        if not cycles.exists(following):
            cycles.create(following, rng)
        taken = set(portion)
        top_up = [w for w in cycles.undone(following) if w not in taken]
        portion += top_up[: size - len(portion)]

    return PortionPlan(
        word_ids=portion,
        inserts=cycles.inserts,
        delete_below=cycles.delete_below(current),
        cycle=current,
    )


def plan_restart(
    members: Sequence[int], entries: Sequence[CycleEntry], rng: random.Random
) -> PortionPlan:
    """«Начать круг заново»: новый круг после последнего, в другом порядке,
    а все прежние круги — на удаление. Прогресс слов это не трогает."""
    cycles = _Cycles(members, entries)
    if not cycles.members:
        return PortionPlan(word_ids=[], cycle=cycles.current() or 0)

    cycle = max(cycles.rows, default=0) + 1
    cycles.create(cycle, rng)
    return PortionPlan(
        word_ids=[],
        inserts=cycles.inserts,
        delete_below=cycles.delete_below(cycle),
        cycle=cycle,
    )


def summary(members: Sequence[int], entries: Sequence[CycleEntry]) -> tuple[int, int, int]:
    """Размер группы, сколько пройдено в текущем круге и номер этого круга."""
    cycles = _Cycles(members, entries)
    current = cycles.current()
    if current is None:
        return len(cycles.members), 0, 0
    done = sum(1 for e in cycles.member_rows(current) if e.done)
    return len(cycles.members), done, current
