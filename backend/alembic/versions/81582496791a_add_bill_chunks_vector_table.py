"""add bill_chunks vector table

Revision ID: 81582496791a
Revises: 71a44ab8b8ba
Create Date: 2026-08-10 19:18:01.511098

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
#autogenerate emits pgvector.sqlalchemy.vector.VECTOR in the column type but
#does not import it, so the module has to be brought in by hand
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = '81582496791a'
down_revision: Union[str, None] = '71a44ab8b8ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#name kept in one place so upgrade and downgrade cannot drift apart
INDEX_NAME = "ix_bill_chunks_embedding_hnsw"


def upgrade() -> None:
    #the vector type has to exist before a column can be declared with it.
    #IF NOT EXISTS so re-running against a database that already has the
    #extension is a no-op rather than an error
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table('bill_chunks',
    sa.Column('chunk_id', sa.UUID(), nullable=False),
    sa.Column('bill_id', sa.Text(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('chunk_text', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['bill_id'], ['bills.bill_id'], ),
    sa.PrimaryKeyConstraint('chunk_id'),
    sa.UniqueConstraint('bill_id', 'chunk_index', name='uq_bill_chunks_bill_id_index')
    )

    #alembic cannot autogenerate a vector index, so it is written out here.
    #cosine distance because embeddings are compared by direction, not
    #magnitude. creating it now is deliberate: an hnsw index is valid on a
    #table whose embeddings are all still null — rows simply enter the graph
    #as they get filled in, so no rebuild is needed after the embedding step
    op.execute(
        f"CREATE INDEX {INDEX_NAME} ON bill_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    #dropping the table takes its indexes with it
    op.drop_table('bill_chunks')
    #the extension is deliberately left in place: other tables may come to
    #depend on it, and dropping it would cascade into them
