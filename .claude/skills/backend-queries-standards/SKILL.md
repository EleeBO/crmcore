---
name: backend-queries-standards
description: Secure, performant database queries with parameterization, N+1 prevention, indexing, and transactions. Use when writing database queries.
---

# Backend Queries Standards

**Core Rule:** Parameterized queries ALWAYS, eager loading to prevent N+1, strategic indexing.

## When to Use

- Writing SQL or ORM queries
- Optimizing query performance
- Preventing SQL injection
- Managing transactions

## SQL Injection Prevention (MANDATORY)

**NEVER concatenate user input into SQL strings.**

```python
# BAD - Vulnerable!
query = f"SELECT * FROM users WHERE email = '{email}'"

# GOOD - Parameterized
cursor.execute("SELECT * FROM users WHERE email = %s", (email,))

# SQLAlchemy ORM
User.query.filter_by(email=email).first()

# SQLAlchemy Core
select(User).where(User.email == email)
```

This applies to ALL user input: query params, form data, headers, cookies.

## N+1 Query Prevention

**Problem:** Loading a collection then querying for each item's relations.

```python
# BAD - N+1 queries (1 + N separate queries)
users = User.query.all()
for user in users:
    posts = user.posts  # Query per user!
```

```python
# GOOD - Eager loading (1-2 queries total)
from sqlalchemy.orm import joinedload, selectinload

# joinedload - single query with JOIN
users = User.query.options(joinedload(User.posts)).all()

# selectinload - separate optimized query
users = User.query.options(selectinload(User.posts)).all()
```

### When to Use Each

| Strategy | Use When |
|----------|----------|
| `joinedload` | One-to-one, small one-to-many |
| `selectinload` | Large one-to-many, many-to-many |

## Select Only Required Columns

```python
# BAD - Fetching all columns
users = User.query.all()

# GOOD - Specific columns
from sqlalchemy.orm import load_only

users = User.query.options(
    load_only(User.id, User.email, User.name)
).all()

# Or with query
users = db.session.query(User.id, User.email, User.name).all()
```

**Especially important when:**
- Tables have large TEXT/BLOB columns
- Fetching many rows
- Columns contain sensitive data not needed

## Indexing Strategy

**Index columns used in:**
- WHERE clauses
- JOIN conditions
- ORDER BY clauses
- Foreign keys

```python
# Migration example
def upgrade():
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_posts_user_id', 'posts', ['user_id'])
    op.create_index('idx_posts_created_at', 'posts', ['created_at'])
```

**Composite indexes for multi-column queries:**
```sql
CREATE INDEX idx_posts_user_status ON posts(user_id, status);
```

**Don't over-index:** Each index slows writes.

## Transactions

**Use transactions when:**
- Multiple writes must succeed/fail together
- Read then write (prevent race conditions)
- Updating multiple related tables

```python
from sqlalchemy.orm import Session

with Session(engine) as session:
    try:
        user = session.query(User).filter_by(id=user_id).with_for_update().first()
        user.balance -= amount
        transaction = Transaction(user_id=user_id, amount=amount)
        session.add(transaction)
        session.commit()
    except Exception:
        session.rollback()
        raise
```

**Use `with_for_update()` for row-level locking.**

## Query Timeouts

```python
# SQLAlchemy
engine = create_engine(
    url,
    connect_args={'options': '-c statement_timeout=5000'}
)

# Typical timeouts
# Simple queries: 1-2 seconds
# Complex reports: 10-30 seconds
# Background jobs: 60+ seconds
```

## Caching Expensive Queries

```python
import redis
import json

cache = redis.Redis()

def get_user_stats(user_id):
    cache_key = f"user_stats:{user_id}"
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)

    # Expensive query
    stats = db.session.query(
        func.count(Post.id),
        func.sum(Post.views)
    ).filter(Post.user_id == user_id).first()

    cache.setex(cache_key, 3600, json.dumps(stats))  # 1 hour
    return stats
```

## Common Anti-Patterns

```python
# BAD - Filter in Python
all_users = User.query.all()
active = [u for u in all_users if u.status == 'active']

# GOOD - Filter in database
active = User.query.filter_by(status='active').all()

# BAD - Multiple queries
user = User.query.get(user_id)
posts = Post.query.filter_by(user_id=user_id).all()

# GOOD - Single query with join
user = User.query.options(joinedload(User.posts)).get(user_id)

# BAD - LIKE with leading wildcard (can't use index)
User.query.filter(User.email.like('%@example.com'))

# GOOD - LIKE with trailing wildcard (can use index)
User.query.filter(User.email.like('user@%'))
```

## Testing Query Performance

```python
# Enable query logging
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Use EXPLAIN
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'user@example.com';
```

## Checklist

Before completing query work:

- [ ] All user input uses parameterized queries
- [ ] No N+1 queries (verified with logging)
- [ ] Only required columns selected
- [ ] Indexes on WHERE/JOIN/ORDER BY columns
- [ ] Related writes in transactions
- [ ] Query timeout set
- [ ] Expensive queries cached if appropriate
