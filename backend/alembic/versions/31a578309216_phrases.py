"""phrases: a separate deck

Фразы («break the ice», «It's up to you») учатся отдельно от слов: свой
словарь, свои метки, свой прогресс и свой журнал ответов. Для этого пять
новых таблиц: `phrases`, `phrase_progress`, `phrase_review_log`,
`phrase_labels` и связка `phrase_label_links`. Все внешние ключи фраз
указывают только на таблицы фраз — связей со словами нет, поэтому запросы,
`finish` и статистика слов не могут задеть фразы.

Колонки повторяют таблицы слов (кроме `text`/`text_key` вместо
`word`/`word_key` и длины 200 вместо 128): алгоритм занятия общий для обеих
колод.

Таблицы слов не трогаются — миграция только создаёт новые таблицы.
`downgrade` удаляет только таблицы фраз.

Revision ID: 31a578309216
Revises: f59f358ade34
Create Date: 2026-10-10 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '31a578309216'
down_revision: Union[str, Sequence[str], None] = 'f59f358ade34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'phrases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(length=200), nullable=False),
        sa.Column('text_key', sa.String(length=200), nullable=False),
        sa.Column('translation', sa.Text(), nullable=False),
        sa.Column('example', sa.Text(), nullable=True),
        sa.Column('example_translation', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('priority', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_phrases_text_key', 'phrases', ['text_key'])
    op.create_index(
        'ux_phrases_text_key_translation', 'phrases', ['text_key', 'translation'], unique=True
    )

    op.create_table(
        'phrase_progress',
        sa.Column('phrase_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('step', sa.Integer(), nullable=False),
        sa.Column('repetitions', sa.Integer(), nullable=False),
        sa.Column('ease', sa.Float(), nullable=False),
        sa.Column('interval_days', sa.Float(), nullable=False),
        sa.Column('due_at', sa.DateTime(), nullable=False),
        sa.Column('lapses', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['phrase_id'], ['phrases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('phrase_id'),
    )
    op.create_index(
        'ix_phrase_progress_status_due_at', 'phrase_progress', ['status', 'due_at']
    )

    op.create_table(
        'phrase_review_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('phrase_id', sa.Integer(), nullable=False),
        sa.Column('exercise', sa.String(length=24), nullable=False),
        sa.Column('correct', sa.Boolean(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('used_hint', sa.Boolean(), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('quality', sa.Integer(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('status_before', sa.String(length=16), nullable=False),
        sa.Column('status_after', sa.String(length=16), nullable=False),
        sa.Column('ease_after', sa.Float(), nullable=False),
        sa.Column('interval_after', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['phrase_id'], ['phrases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_phrase_review_log_phrase_id', 'phrase_review_log', ['phrase_id'])
    op.create_index('ix_phrase_review_log_created_at', 'phrase_review_log', ['created_at'])
    op.create_index('ix_phrase_review_log_session_id', 'phrase_review_log', ['session_id'])

    op.create_table(
        'phrase_labels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('name_key', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ux_phrase_labels_name_key', 'phrase_labels', ['name_key'], unique=True)

    op.create_table(
        'phrase_label_links',
        sa.Column('phrase_id', sa.Integer(), nullable=False),
        sa.Column('label_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['phrase_id'], ['phrases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['label_id'], ['phrase_labels.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('phrase_id', 'label_id'),
    )
    op.create_index('ix_phrase_label_links_label_id', 'phrase_label_links', ['label_id'])


def downgrade() -> None:
    """Downgrade schema.

    Теряются все фразы, их метки, прогресс и журнал ответов. Слова и всё,
    что к ним относится, не затрагиваются.
    """
    op.drop_index('ix_phrase_label_links_label_id', table_name='phrase_label_links')
    op.drop_table('phrase_label_links')
    op.drop_index('ux_phrase_labels_name_key', table_name='phrase_labels')
    op.drop_table('phrase_labels')
    op.drop_index('ix_phrase_review_log_session_id', table_name='phrase_review_log')
    op.drop_index('ix_phrase_review_log_created_at', table_name='phrase_review_log')
    op.drop_index('ix_phrase_review_log_phrase_id', table_name='phrase_review_log')
    op.drop_table('phrase_review_log')
    op.drop_index('ix_phrase_progress_status_due_at', table_name='phrase_progress')
    op.drop_table('phrase_progress')
    op.drop_index('ux_phrases_text_key_translation', table_name='phrases')
    op.drop_index('ix_phrases_text_key', table_name='phrases')
    op.drop_table('phrases')
