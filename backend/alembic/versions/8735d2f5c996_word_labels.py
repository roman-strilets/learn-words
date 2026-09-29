"""word labels

Слова получают тематические метки («кухня», «глаголы движения»): у слова
их может быть сколько угодно, у метки — сколько угодно слов. Для этого две
новые таблицы: `labels` и связка `word_labels`.

У метки есть `name_key` — название в нижнем регистре, посчитанное в Python:
`lower()` в SQLite не знает кириллицы, а уникальность названия нужна без учёта
регистра. Связка удаляется каскадом с обеих сторон: удаление метки снимает её
со всех слов, удаление слова — его метки. Индекс по `label_id` нужен фильтру
словаря по метке и счётчику слов у метки.

Таблица `words` не пересоздаётся — миграция только создаёт новые таблицы:
пересоздание `words` в SQLite увело бы внешние ключи `progress.word_id` и
`review_log.word_id` на временную таблицу.

Revision ID: 8735d2f5c996
Revises: db05d4083721
Create Date: 2026-09-29 15:05:08.567577

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8735d2f5c996'
down_revision: Union[str, Sequence[str], None] = 'db05d4083721'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'labels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('name_key', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ux_labels_name_key', 'labels', ['name_key'], unique=True)
    op.create_table(
        'word_labels',
        sa.Column('word_id', sa.Integer(), nullable=False),
        sa.Column('label_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['word_id'], ['words.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['label_id'], ['labels.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('word_id', 'label_id'),
    )
    op.create_index('ix_word_labels_label_id', 'word_labels', ['label_id'])


def downgrade() -> None:
    """Downgrade schema.

    Теряется только разметка: метки и их связки со словами. Слова, прогресс
    и журнал ответов не затрагиваются.
    """
    op.drop_index('ix_word_labels_label_id', table_name='word_labels')
    op.drop_table('word_labels')
    op.drop_index('ux_labels_name_key', table_name='labels')
    op.drop_table('labels')
