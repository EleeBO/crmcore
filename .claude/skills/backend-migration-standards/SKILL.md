---
name: backend-migration-standards
description: Database migration standards with reversibility, zero-downtime deployments, and naming conventions. Use when creating or modifying migrations.
---

# Backend Migration Standards

**Core Rule:** Every migration MUST be reversible. One logical change per migration. Never modify deployed migrations.

## When to Use

- Creating database migrations
- Adding/removing columns or tables
- Creating indexes
- Data migrations

## Core Principles

1. **Reversibility is Mandatory** - Every migration has working rollback
2. **One Change Per Migration** - Add table, add column, create index - separately
3. **Never Modify Deployed Migrations** - Create new migration to fix issues

## Naming Convention

```
{timestamp}_{action}_{description}.py

Examples:
20241115120000_add_email_to_users.py
20241115120100_create_orders_table.py
20241115120200_add_index_on_users_email.py
```

## Adding Columns

```python
# BAD - Locks table during backfill
def upgrade():
    op.add_column('users', sa.Column('status', sa.String(), nullable=False))

# GOOD - Uses default, no lock
def upgrade():
    op.add_column('users', sa.Column(
        'status',
        sa.String(),
        nullable=False,
        server_default='active'
    ))

def downgrade():
    op.drop_column('users', 'status')
```

## Removing Columns (Zero-Downtime)

**Multi-step approach:**
1. Deploy code that stops using column
2. Deploy migration that removes column
3. Never combine these steps

```python
def upgrade():
    op.drop_column('users', 'legacy_field')

def downgrade():
    op.add_column('users', sa.Column('legacy_field', sa.String()))
```

## Creating Indexes

**Use concurrent creation on large tables:**

```python
def upgrade():
    # PostgreSQL - concurrent (no lock)
    op.create_index(
        'idx_users_email',
        'users',
        ['email'],
        postgresql_concurrently=True
    )

def downgrade():
    op.drop_index('idx_users_email', 'users')
```

## Data Migrations

**Keep separate from schema migrations. Use batches:**

```python
def upgrade():
    connection = op.get_bind()
    batch_size = 1000

    while True:
        result = connection.execute(text("""
            UPDATE users
            SET status = 'active'
            WHERE status IS NULL
            LIMIT :batch
        """), {'batch': batch_size})

        if result.rowcount == 0:
            break
```

**Make idempotent:**

```python
# BAD - Fails on second run
op.execute("INSERT INTO settings (key, value) VALUES ('flag', 'true')")

# GOOD - Idempotent
op.execute("""
    INSERT INTO settings (key, value)
    VALUES ('flag', 'true')
    ON CONFLICT (key) DO NOTHING
""")
```

## Zero-Downtime Checklist

### Adding NOT NULL column to existing table:
1. Add column as nullable with default
2. Backfill existing rows
3. Add NOT NULL constraint in separate migration

### Renaming column:
1. Add new column
2. Deploy code that writes to both
3. Backfill data
4. Deploy code that reads from new
5. Remove old column

### Changing column type:
1. Add new column with new type
2. Deploy dual-write code
3. Backfill/convert data
4. Deploy code using new column
5. Remove old column

## Migration Template (Alembic)

```python
"""Add email to users.

Revision ID: abc123
Revises: def456
Create Date: 2024-01-15 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'abc123'
down_revision = 'def456'

def upgrade():
    op.add_column('users', sa.Column(
        'email',
        sa.String(255),
        nullable=True
    ))
    op.create_index('idx_users_email', 'users', ['email'])

def downgrade():
    op.drop_index('idx_users_email', 'users')
    op.drop_column('users', 'email')
```

## Testing Protocol

**Before committing:**
1. Run migration up: `alembic upgrade head`
2. Verify schema changes
3. Run migration down: `alembic downgrade -1`
4. Verify rollback worked
5. Run migration up again (repeatability check)

```bash
# Commands
alembic upgrade head
alembic downgrade -1
alembic upgrade head

# Just commands
just db-migrate
```

## Red Flags - STOP

If you're about to:
- Modify a deployed migration
- Drop column without multi-step plan
- Create migration without down method
- Mix schema and data changes
- Add NOT NULL without default to large table
- Create index without CONCURRENT

**STOP. Review this document.**

## Checklist

Before committing migration:

- [ ] Descriptive timestamp-based name
- [ ] Down/rollback method implemented
- [ ] Ran migration up successfully
- [ ] Ran migration down successfully
- [ ] Ran migration up again (repeatable)
- [ ] No schema + data changes mixed
- [ ] Large table indexes use concurrent
- [ ] NOT NULL columns have defaults
- [ ] Backwards compatible with current code
