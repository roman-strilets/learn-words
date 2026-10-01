"""label gets an optional description

Автоматическая разметка спрашивает модель, к какой метке отнести слово.
Названия вроде «B2» или «кухня» модель понимает не всегда так, как имел в виду
пользователь, поэтому у метки появляется необязательное пояснение темы —
классификатор берёт его критерием вместо названия. Существующие метки
получают NULL и судятся по названию, как раньше.

Таблица не пересоздаётся — add_column/drop_column идут напрямую, без
batch_alter_table: пересоздание `labels` в SQLite увело бы внешний ключ
`word_labels.label_id` на временную таблицу.

Revision ID: f59f358ade34
Revises: 8735d2f5c996
Create Date: 2026-10-01 11:12:14.288088

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f59f358ade34'
down_revision: Union[str, Sequence[str], None] = '8735d2f5c996'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('labels', sa.Column('description', sa.String(200), nullable=True))


def downgrade() -> None:
    """Downgrade schema.

    Теряются только описания меток: сами метки и их связки со словами
    остаются, разметка снова судит по названиям.
    """
    op.drop_column('labels', 'description')
