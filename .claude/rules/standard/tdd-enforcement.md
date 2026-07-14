# TDD Enforcement Rules

## The TDD Cycle

**RED → GREEN → REFACTOR**

1. **RED**: Write a failing test first
2. **GREEN**: Write minimal code to make the test pass
3. **REFACTOR**: Improve code quality while keeping tests green

## When TDD is Required

| Requires TDD | Skip TDD |
|--------------|----------|
| New functions/methods | Documentation changes |
| API endpoints | Config file updates |
| Business logic | IaC code (CDK, Terraform) |
| Bug fixes | Formatting/style changes |
| Data transformations | Static content |

## Test First Checklist

Before writing implementation code:

- [ ] Test file exists for the module
- [ ] Test describes expected behavior
- [ ] Test fails with clear error message
- [ ] Test covers edge cases

## Test Naming Convention

```python
# Python
def test_<action>_<condition>_<expected_result>():
    """<Human readable description>."""
    pass

# Example
def test_create_user_with_invalid_email_raises_validation_error():
    """Creating a user with an invalid email should raise ValidationError."""
    pass
```

```typescript
// TypeScript
describe('ComponentName', () => {
  it('should <expected behavior> when <condition>', () => {
    // ...
  });
});

// Example
describe('UserForm', () => {
  it('should show error message when email is invalid', () => {
    // ...
  });
});
```

## The TDD Enforcer Hook

The `tdd_enforcer.py` hook runs before every Write/Edit operation:

- Checks if file is implementation code (not test, config, docs)
- Verifies failing tests exist in pytest cache
- Warns if no failing tests found
- Allows override on second attempt (60 second window)

## Exceptions

These file types skip TDD checks:
- `.md`, `.rst`, `.txt` - Documentation
- `.json`, `.yaml`, `.yml`, `.toml` - Configuration
- `.env`, `.sql` - Environment/Database
- Files in `migrations/`, `generated/`, `dist/` directories
