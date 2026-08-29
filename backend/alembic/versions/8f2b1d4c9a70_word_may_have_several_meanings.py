"""word may have several meanings

Одно слово перестаёт быть уникальным: у «roll out» может быть отдельная
запись под «вылезать» и под «внедрить». Уникальной остаётся пара
слово + перевод, чтобы одно и то же значение не заводилось дважды.

Индексы пересобираются напрямую, без batch_alter_table: пересоздание
таблицы `words` в SQLite увело бы внешние ключи `progress` и `review_log`
на временную таблицу.

Revision ID: 8f2b1d4c9a70
Revises: 3c0a65e7806c
Create Date: 2026-08-23 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8f2b1d4c9a70'
down_revision: Union[str, Sequence[str], None] = '3c0a65e7806c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f('ix_words_word_key'), table_name='words')
    op.create_index(op.f('ix_words_word_key'), 'words', ['word_key'], unique=False)
    op.create_index(
        'ux_words_word_key_translation', 'words', ['word_key', 'translation'], unique=True
    )


def downgrade() -> None:
    """Downgrade schema.

    Упадёт, если у какого-то слова уже заведено больше одного значения:
    вернуть их в одну запись автоматически нельзя, переводы нужно слить руками.
    """
    op.drop_index('ux_words_word_key_translation', table_name='words')
    op.drop_index(op.f('ix_words_word_key'), table_name='words')
    op.create_index(op.f('ix_words_word_key'), 'words', ['word_key'], unique=True)
