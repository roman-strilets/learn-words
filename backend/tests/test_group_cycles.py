"""Круг группы — чистая логика без базы: какие слова войдут в порцию, какие
строки круга завести и какие круги удалить.

Слова — просто числа, строки круга — `CycleEntry`; «применить план» здесь
значит дописать вставки и выбросить удалённые круги, как это делает сервис.
"""

import random

import pytest

from app.group_cycles import CycleEntry, PortionPlan, plan_portion, plan_restart, summary


def _apply(entries: list[CycleEntry], plan: PortionPlan) -> list[CycleEntry]:
    rows = [*entries, *plan.inserts]
    if plan.delete_below is not None:
        rows = [e for e in rows if e.cycle >= plan.delete_below]
    return rows


def _finish(entries: list[CycleEntry], word_ids: list[int]) -> list[CycleEntry]:
    """Отметить слова пройденными в их самой ранней непройденной строке, как `finish`."""
    rows = list(entries)
    for word_id in word_ids:
        undone = sorted(
            (i for i, e in enumerate(rows) if e.word_id == word_id and not e.done),
            key=lambda i: rows[i].cycle,
        )
        i = undone[0]
        e = rows[i]
        rows[i] = CycleEntry(e.word_id, e.cycle, e.position, True)
    return rows


def _order(entries: list[CycleEntry], cycle: int) -> list[int]:
    return [e.word_id for e in sorted(entries, key=lambda e: e.position) if e.cycle == cycle]


def _play(entries, members, size, rng) -> tuple[list[CycleEntry], PortionPlan]:
    plan = plan_portion(members, entries, size, rng)
    rows = _apply(entries, plan)
    return _finish(rows, plan.word_ids), plan


# --------------------------------------------------------------------- сборка


def test_empty_group_has_no_portion():
    plan = plan_portion([], [], 5, random.Random(1))
    assert plan.word_ids == []
    assert plan.inserts == []
    assert plan.delete_below is None


def test_first_portion_creates_cycle_one():
    members = list(range(1, 13))
    plan = plan_portion(members, [], 5, random.Random(2))

    assert {e.cycle for e in plan.inserts} == {1}
    assert sorted(e.word_id for e in plan.inserts) == members
    assert not any(e.done for e in plan.inserts)
    assert plan.word_ids == _order(plan.inserts, 1)[:5]
    assert plan.cycle == 1


@pytest.mark.parametrize("seed", range(20))
def test_portions_walk_the_cycle_and_top_up_at_the_seam(seed):
    members = list(range(1, 13))
    rng = random.Random(seed)

    rows, first = _play([], members, 5, rng)
    rows, second = _play(rows, members, 5, rng)
    third = plan_portion(members, rows, 5, rng)

    assert len(first.word_ids) == len(second.word_ids) == len(third.word_ids) == 5
    assert not set(first.word_ids) & set(second.word_ids)
    # Остаток первого круга — два слова, и добираются три из второго
    remainder = sorted(set(members) - set(first.word_ids) - set(second.word_ids))
    assert sorted(third.word_ids[:2]) == remainder
    top_up = third.word_ids[2:]
    assert len(top_up) == 3
    assert not set(top_up) & set(remainder)
    assert len(set(third.word_ids)) == 5
    # Добор — первые слова нового круга, кроме слов остатка
    rows = _apply(rows, third)
    assert top_up == [w for w in _order(rows, 2) if w not in remainder][:3]


def test_small_group_gives_whole_group_without_top_up():
    plan = plan_portion([1, 2, 3], [], 5, random.Random(3))
    assert sorted(plan.word_ids) == [1, 2, 3]
    assert {e.cycle for e in plan.inserts} == {1}


@pytest.mark.parametrize("size", [3, 4, 5])
def test_new_cycle_order_differs_and_does_not_start_with_last(size):
    members = list(range(1, size + 1))
    for seed in range(200):
        rng = random.Random(seed)
        rows, _ = _play([], members, size, rng)
        old = _order(rows, 1)
        plan = plan_portion(members, rows, size, rng)
        rows = _apply(rows, plan)

        new = _order(rows, 2)
        assert plan.cycle == 2
        assert sorted(new) == members
        assert new != old
        assert new[0] != old[-1]
        assert plan.word_ids == new


def test_two_words_swap_in_the_next_cycle():
    for seed in range(20):
        rng = random.Random(seed)
        rows, _ = _play([], [1, 2], 5, rng)
        old = _order(rows, 1)
        rows = _apply(rows, plan_portion([1, 2], rows, 5, rng))
        assert _order(rows, 2) == list(reversed(old))


def test_single_word_is_every_cycle():
    rng = random.Random(4)
    rows: list[CycleEntry] = []
    for cycle in (1, 2, 3):
        rows, plan = _play(rows, [7], 5, rng)
        assert plan.word_ids == [7]
        assert plan.cycle == cycle


def test_new_member_is_appended_to_current_and_next_cycle():
    members = list(range(1, 8))
    rng = random.Random(5)
    rows, _ = _play([], members, 5, rng)
    # Стык: остаток из 2 слов и добор из второго круга, но занятие прервано
    rows = _apply(rows, plan_portion(members, rows, 5, rng))
    last_positions = {c: max(e.position for e in rows if e.cycle == c) for c in (1, 2)}

    plan = plan_portion([*members, 99], rows, 5, rng)
    added = [e for e in plan.inserts if e.word_id == 99]
    assert {e.cycle for e in added} == {1, 2}
    assert all(not e.done for e in added)
    for e in added:
        assert e.position > last_positions[e.cycle]
    # Новое слово стоит в конце остатка текущего круга, порция до него доходит
    assert 99 in plan.word_ids


def test_word_that_lost_the_label_is_ignored_and_returns_with_it():
    members = list(range(1, 13))
    rng = random.Random(6)
    rows, _ = _play([], members, 5, rng)
    gone = _order(rows, 1)[5]  # первое слово следующей порции

    without = [m for m in members if m != gone]
    plan = plan_portion(without, rows, 5, rng)
    assert gone not in plan.word_ids
    assert summary(without, rows) == (11, 5, 1)
    # Строки ушедшего слова не удаляются: метку вернули — место вернулось
    assert all(e.word_id != gone for e in plan.inserts)
    assert plan_portion(members, rows, 5, rng).word_ids[0] == gone


def test_next_cycle_is_reused_on_retry():
    members = list(range(1, 8))
    rng = random.Random(7)
    rows, _ = _play([], members, 5, rng)

    plan = plan_portion(members, rows, 5, rng)
    rows = _apply(rows, plan)
    retry = plan_portion(members, rows, 5, random.Random(999))
    assert retry.inserts == []
    assert retry.word_ids == plan.word_ids


def test_cycles_below_current_are_deleted():
    members = list(range(1, 8))
    rng = random.Random(8)
    rows, _ = _play([], members, 5, rng)
    rows, _ = _play(rows, members, 5, rng)  # стык: круг 1 закрыт, во втором 3 пройдено

    plan = plan_portion(members, rows, 5, rng)
    assert plan.cycle == 2
    assert plan.delete_below == 2
    assert all(e.cycle >= 2 for e in _apply(rows, plan))


def test_no_deletion_without_lower_cycles():
    plan = plan_portion([1, 2, 3], [], 5, random.Random(9))
    assert plan.delete_below is None


# ------------------------------------------------------------------- итоги


def test_summary():
    members = list(range(1, 8))
    assert summary(members, []) == (7, 0, 0)

    rng = random.Random(10)
    rows, _ = _play([], members, 5, rng)
    assert summary(members, rows) == (7, 5, 1)

    rows, _ = _play(rows, members, 5, rng)
    # Круг 1 закрыт, во втором пройдено три добранных слова
    assert summary(members, rows) == (7, 3, 2)

    small = [1, 2, 3]
    rows, _ = _play([], small, 5, rng)
    assert summary(small, rows) == (3, 3, 1)


# ------------------------------------------------------------- круг заново


def test_restart_starts_new_cycle_in_new_order():
    members = list(range(1, 13))
    for seed in range(50):
        rng = random.Random(seed)
        rows, _ = _play([], members, 5, rng)
        plan = plan_restart(members, rows, rng)
        assert plan.word_ids == []
        assert plan.cycle == 2
        assert plan.delete_below == 2
        rows = _apply(rows, plan)
        assert {e.cycle for e in rows} == {2}
        assert summary(members, rows) == (12, 0, 2)


def test_restart_order_differs_from_latest_cycle():
    members = [1, 2, 3, 4]
    for seed in range(100):
        rng = random.Random(seed)
        rows = _apply([], plan_portion(members, [], 2, rng))
        latest = _order(rows, 1)
        rows = _apply(rows, plan_restart(members, rows, rng))
        assert _order(rows, 2) != latest
        assert _order(rows, 2)[0] != latest[-1]


def test_restart_of_empty_group_does_nothing():
    plan = plan_restart([], [CycleEntry(1, 1, 0, True)], random.Random(11))
    assert plan.inserts == []
    assert plan.delete_below is None
