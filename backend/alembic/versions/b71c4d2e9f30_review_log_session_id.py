"""review log gets a session id

Занятие-повторение перестало быть очередью из одного упражнения на слово:
теперь это четыре раунда, а расписание пересчитывается один раз в конце.
Чтобы сервер мог сам, по журналу, определить итог занятия и не хранить
состояние между запросами, каждая попытка помечается ключом занятия.

Колонка nullable: строки, накопленные до появления раундов, и ответы
режима «Изучение» остаются с NULL и продолжают считаться в статистике.

Таблица не пересоздаётся — add_column/drop_column идут напрямую, без
batch_alter_table: пересоздание `review_log` в SQLite увело бы внешний
ключ `review_log.word_id -> words.id` на временную таблицу.

Revision ID: b71c4d2e9f30
Revises: 8f2b1d4c9a70
Create Date: 2026-08-29 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b71c4d2e9f30'
down_revision: Union[str, Sequence[str], None] = '8f2b1d4c9a70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('review_log', sa.Column('session_id', sa.String(length=36), nullable=True))
    op.create_index(
        op.f('ix_review_log_session_id'), 'review_log', ['session_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema.

    Ключи занятий теряются безвозвратно — восстановить их из прогресса нельзя.
    На расписание это не влияет: оно уже применено.
    """
    op.drop_index(op.f('ix_review_log_session_id'), table_name='review_log')
    op.drop_column('review_log', 'session_id')
