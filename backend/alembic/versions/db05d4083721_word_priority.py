"""word gets a priority mark

Пользователь может поднять новое слово в очереди «Изучения» — отметить его
«Учить первым». Отбор новых слов сортирует сначала по этой отметке, затем
по выбранному порядку добавления.

Отметка живёт на `words`, а не в `progress`: она бывает только у нового
слова, а у нового слова строки прогресса нет. Сервис снимает её, как только
слово получает прогресс. Существующие слова получают `false` через
server_default, так что поведение у всех не менялось до первой отметки.

Таблица не пересоздаётся — add_column/drop_column идут напрямую, без
batch_alter_table: пересоздание `words` в SQLite увело бы внешние ключи
`progress.word_id` и `review_log.word_id` на временную таблицу.

Revision ID: db05d4083721
Revises: b71c4d2e9f30
Create Date: 2026-09-21 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'db05d4083721'
down_revision: Union[str, Sequence[str], None] = 'b71c4d2e9f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'words',
        sa.Column('priority', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema.

    Теряются только отметки «Учить первым»: слова снова идут в порядке
    добавления. Прогресс и расписание не затрагиваются.
    """
    op.drop_column('words', 'priority')
