"""group study: cycles and an answer log of their own

Занятие по группе — пять раундов по словам одной метки — не трогает основное
обучение: ни прогресс, ни расписание, ни `review_log`, ни статистику. Поэтому
у него две свои таблицы:

- `group_cycle_words` — круг группы: строка на (метка, круг, слово) с позицией
  в порядке круга и отметкой прохождения. Порядок круга фиксируется один раз и
  переживает перезагрузку и прерванное занятие;
- `group_review_log` — журнал ответов занятий по группе, без колонок
  расписания: переходов расписания здесь не бывает.

Внешние ключи с каскадами: удаление метки удаляет её круги, удаление слова —
его строки круга и журнала; удаление метки оставляет попытки с `label_id`
NULL. Существующие таблицы не трогаются, `downgrade` удаляет только эти две.

Revision ID: c4e8a1f2b6d3
Revises: 31a578309216
Create Date: 2026-10-16 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1f2b6d3'
down_revision: Union[str, Sequence[str], None] = '31a578309216'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'group_cycle_words',
        sa.Column('label_id', sa.Integer(), nullable=False),
        sa.Column('cycle', sa.Integer(), nullable=False),
        sa.Column('word_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        sa.Column('done_session_id', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['label_id'], ['labels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['word_id'], ['words.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('label_id', 'cycle', 'word_id'),
    )
    op.create_index('ix_group_cycle_words_word_id', 'group_cycle_words', ['word_id'])

    op.create_table(
        'group_review_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('word_id', sa.Integer(), nullable=False),
        sa.Column('label_id', sa.Integer(), nullable=True),
        sa.Column('exercise', sa.String(length=24), nullable=False),
        sa.Column('correct', sa.Boolean(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('used_hint', sa.Boolean(), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('quality', sa.Integer(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['word_id'], ['words.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['label_id'], ['labels.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_group_review_log_word_id', 'group_review_log', ['word_id'])
    op.create_index('ix_group_review_log_session_id', 'group_review_log', ['session_id'])
    op.create_index('ix_group_review_log_created_at', 'group_review_log', ['created_at'])


def downgrade() -> None:
    """Downgrade schema: только таблицы занятия по группе, остальные не трогаются."""
    op.drop_index('ix_group_review_log_created_at', table_name='group_review_log')
    op.drop_index('ix_group_review_log_session_id', table_name='group_review_log')
    op.drop_index('ix_group_review_log_word_id', table_name='group_review_log')
    op.drop_table('group_review_log')
    op.drop_index('ix_group_cycle_words_word_id', table_name='group_cycle_words')
    op.drop_table('group_cycle_words')
