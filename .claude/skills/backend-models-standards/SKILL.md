---
name: backend-models-standards
description: Database model design with naming conventions, constraints, relationships, and data types. Use when creating or modifying database models.
---

# Backend Models Standards

**Core Rule:** Models define data structure and integrity. Constraints in database, not just code.

## When to Use

- Creating or modifying database models
- Defining relationships between tables
- Setting up constraints and validation
- Choosing data types

## Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Model | Singular PascalCase | `User`, `OrderItem` |
| Table | Plural snake_case | `users`, `order_items` |
| Column | snake_case | `created_at`, `user_id` |
| FK | `{table}_id` | `user_id`, `order_id` |
| Index | `idx_{table}_{column}` | `idx_users_email` |

**Avoid generic names:** `data`, `info`, `record`, `entity`

## Required Fields (Every Model)

```python
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer

class Base:
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
```

## Data Types

| Data | Use | Avoid |
|------|-----|-------|
| Email, URL | VARCHAR(255) | TEXT |
| Short text | VARCHAR(n) | TEXT |
| Long text | TEXT | VARCHAR |
| Money | DECIMAL(10,2) | FLOAT |
| Boolean | BOOLEAN | TINYINT |
| Timestamps | TIMESTAMP/DATETIME | VARCHAR |
| JSON | JSON/JSONB | TEXT |
| UUIDs | UUID | VARCHAR(36) |

## Database Constraints

**Enforce integrity at database level, not just application:**

```python
from sqlalchemy import Column, String, Integer, ForeignKey, CheckConstraint

class User(Base):
    __tablename__ = 'users'

    # NOT NULL for required fields
    email = Column(String(255), nullable=False)

    # UNIQUE constraint
    email = Column(String(255), unique=True, nullable=False)

    # CHECK constraint for business rules
    age = Column(Integer, CheckConstraint('age >= 18'))

    # Foreign key with cascade
    role_id = Column(
        Integer,
        ForeignKey('roles.id', ondelete='SET NULL'),
        nullable=True
    )
```

## Relationships

**Define both sides explicitly:**

```python
from sqlalchemy.orm import relationship

class User(Base):
    __tablename__ = 'users'

    # One-to-many
    orders = relationship(
        'Order',
        back_populates='user',
        cascade='all, delete-orphan'
    )

class Order(Base):
    __tablename__ = 'orders'

    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User', back_populates='orders')
```

### Cascade Behaviors

| Behavior | Use When |
|----------|----------|
| CASCADE | Delete children with parent |
| SET NULL | Keep children, nullify FK |
| RESTRICT | Prevent deletion if children exist |
| NO ACTION | Database default (usually RESTRICT) |

## Indexes

**Index columns used in:**
- WHERE clauses
- JOIN conditions
- ORDER BY clauses
- Foreign keys

```python
class Order(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    status = Column(String(50), index=True)  # Frequently filtered
    created_at = Column(DateTime, index=True)  # Frequently sorted
```

## Enums for Fixed Values

```python
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = 'pending'
    PAID = 'paid'
    SHIPPED = 'shipped'
    DELIVERED = 'delivered'

class Order(Base):
    status = Column(
        Enum(OrderStatus),
        nullable=False,
        default=OrderStatus.PENDING
    )
```

## Soft Deletes

```python
class User(Base):
    deleted_at = Column(DateTime, nullable=True, index=True)

# Query only active records
active_users = session.query(User).filter(User.deleted_at.is_(None))
```

## Model Validation

```python
from sqlalchemy.orm import validates
import re

class User(Base):
    @validates('email')
    def validate_email(self, key, email):
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            raise ValueError('Invalid email format')
        return email.lower()

    @validates('age')
    def validate_age(self, key, age):
        if age < 0:
            raise ValueError('Age cannot be negative')
        return age
```

## What Belongs in Models

**YES:**
- Field definitions and types
- Relationships to other models
- Simple property methods (`@property def full_name`)
- Data validation rules
- Database constraints

**NO:**
- Business logic (→ service layer)
- External API calls
- Complex calculations
- Email sending, file uploads

## Testing Models

```python
import pytest
from sqlalchemy.exc import IntegrityError

def test_user_email_required(session):
    with pytest.raises(IntegrityError):
        user = User(name='Test')  # No email
        session.add(user)
        session.commit()

def test_user_email_unique(session):
    user1 = User(email='test@example.com')
    session.add(user1)
    session.commit()

    with pytest.raises(IntegrityError):
        user2 = User(email='test@example.com')
        session.add(user2)
        session.commit()

def test_cascade_delete(session):
    user = User(email='test@example.com')
    order = Order(user=user)
    session.add(user)
    session.commit()

    session.delete(user)
    session.commit()

    assert session.query(Order).count() == 0
```

## Checklist

Before completing model work:

- [ ] Singular model name, plural table name
- [ ] Primary key defined
- [ ] `created_at` and `updated_at` timestamps
- [ ] NOT NULL on required fields
- [ ] UNIQUE constraints where appropriate
- [ ] Foreign keys with explicit cascade
- [ ] Indexes on FK and queried columns
- [ ] Appropriate data types
- [ ] Validation at model AND database levels
- [ ] Relationships defined on both sides
- [ ] Tests for constraints
