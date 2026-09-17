// Алгоритм общий с серверной `order_round` (backend/app/exercises.py),
// тесты — на сервере. Кандидаты и порядок их перебора должны совпадать
// буквально: доказательство «кандидатов всегда хватает» верно только для них.

// Одно слово переставлять некуда
const MIN_WORDS_TO_REORDER = 2
// При двух словах «не начинать с последнего» противоречит «не повторять
// порядок», и важнее второе (FR-003, FR-004)
const MIN_WORDS_TO_AVOID_REPEAT = 3

/** Порядок раунда и три его запасные перестановки — ровно в этом порядке. */
function candidates<T>(q: T[]): T[][] {
  const result = [q, [q[1], q[0], ...q.slice(2)], [...q.slice(1), q[0]]]
  if (q.length >= MIN_WORDS_TO_AVOID_REPEAT) {
    result.push([q[0], q[2], q[1], ...q.slice(3)])
  }
  return result
}

/**
 * Поправить порядок следующего раунда под то, что занятие показало на самом деле.
 *
 * Сервер уже перемешал раунд, но знает только план. Поэтому порядок, отличный
 * от `previous` и не начинающийся с `lastWordId` (при трёх словах и больше),
 * остаётся как есть, а иначе берётся первый подходящий запасной. Если такого
 * не нашлось — возвращаем раунд без изменений: занятие важнее порядка.
 */
export function arrangeRound<T extends { word_id: number }>(
  items: T[],
  previous: number[] | null,
  lastWordId: number | null,
): T[] {
  if (previous === null || items.length < MIN_WORDS_TO_REORDER) return items

  const avoidStart = items.length >= MIN_WORDS_TO_AVOID_REPEAT && lastWordId !== null
  const found = candidates(items).find((candidate) => {
    const same =
      candidate.length === previous.length &&
      candidate.every((item, i) => item.word_id === previous[i])
    if (same) return false
    return !(avoidStart && candidate[0].word_id === lastWordId)
  })
  return found ?? items
}
