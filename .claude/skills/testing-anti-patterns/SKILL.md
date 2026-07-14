---
name: testing-anti-patterns
description: Common testing mistakes to avoid - mock behavior testing, test-only methods, blind mocking, incomplete mocks, tests as afterthought. Review before writing tests.
---

# Testing Anti-Patterns Skill

**Core Rule:** Tests verify BEHAVIOR, not implementation. Avoid these 5 deadly patterns.

## When to Use

- Before writing any test
- When reviewing test code
- When tests are flaky or brittle
- When refactoring breaks tests unexpectedly

## Anti-Pattern 1: Testing Mock Behavior

**The Problem:** Verifying that mocks behave as configured, not actual code.

```python
# BAD - Tests the mock, not the code
@mock.patch('app.client.fetch')
def test_get_user(mock_fetch):
    mock_fetch.return_value = {'name': 'John'}

    result = mock_fetch(1)  # Calling the MOCK directly!

    assert result == {'name': 'John'}  # Always passes!
```

```python
# GOOD - Tests actual code behavior
@mock.patch('app.client.fetch')
def test_get_user(mock_fetch):
    mock_fetch.return_value = {'name': 'John'}

    result = get_user(1)  # Calling REAL function

    assert result.name == 'John'
    mock_fetch.assert_called_once_with(1)
```

**Detection:** If your test passes with ANY mock return value, you're testing the mock.

## Anti-Pattern 2: Test-Only Methods

**The Problem:** Adding methods/parameters to production code ONLY for testing.

```python
# BAD - _for_testing methods
class UserService:
    def __init__(self, db):
        self.db = db

    def _get_db_for_testing(self):  # Why does this exist?
        return self.db

    def create_user(self, data, _skip_validation=False):  # Test flag!
        if not _skip_validation:
            self.validate(data)
        ...
```

```python
# GOOD - Inject dependencies
class UserService:
    def __init__(self, db, validator=None):
        self.db = db
        self.validator = validator or DefaultValidator()

    def create_user(self, data):
        self.validator.validate(data)
        ...

# Test with mock validator
service = UserService(mock_db, mock_validator)
```

**Detection:** Methods/params only used in tests. Ask "would this exist without tests?"

## Anti-Pattern 3: Blind Mocking

**The Problem:** Mocking without understanding what you're mocking.

```python
# BAD - Mock everything blindly
@mock.patch('app.service.db')
@mock.patch('app.service.cache')
@mock.patch('app.service.logger')
@mock.patch('app.service.metrics')
def test_process(mock_metrics, mock_logger, mock_cache, mock_db):
    # What is this test actually verifying?
    result = process_data({})
    assert result is not None  # Meaningless assertion
```

```python
# GOOD - Mock only external boundaries
@mock.patch('app.service.external_api')
def test_process_calls_api_correctly(mock_api):
    mock_api.return_value = {'status': 'ok'}

    result = process_data({'id': 123})

    mock_api.assert_called_with(id=123, format='json')
    assert result.status == 'ok'
```

**Rule:** Mock at boundaries (APIs, databases, file system). Test internal logic directly.

## Anti-Pattern 4: Incomplete Mocks

**The Problem:** Mocks missing behavior that production code depends on.

```python
# BAD - Incomplete mock
@mock.patch('app.client')
def test_fetch_user(mock_client):
    mock_client.get.return_value = Mock()  # Missing status_code!

    result = fetch_user(1)  # Crashes on response.status_code
```

```python
# GOOD - Complete mock with all used attributes
@mock.patch('app.client')
def test_fetch_user(mock_client):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'name': 'John'}
    mock_client.get.return_value = mock_response

    result = fetch_user(1)

    assert result.name == 'John'
```

**Detection:** Tests crash with AttributeError on mocks. Check what attributes code actually uses.

## Anti-Pattern 5: Tests as Afterthought

**The Problem:** Writing tests to cover code, not to specify behavior.

```python
# BAD - Reverse-engineering tests from implementation
def test_calculate_score():
    # I see the code does math, so let me verify that math
    result = calculate_score(10, 20, 0.5)
    assert result == 15.0  # Is this right? Who knows!
```

```python
# GOOD - Tests specify behavior FIRST (TDD)
def test_calculate_score_weights_recent_higher():
    """Recent scores should contribute more to final score."""
    old_score = 10
    new_score = 20
    recency_weight = 0.7  # 70% weight on recent

    result = calculate_score(old_score, new_score, recency_weight)

    # Expected: 10 * 0.3 + 20 * 0.7 = 3 + 14 = 17
    assert result == 17.0
```

**Detection:** Tests don't have clear purpose. Ask "what behavior does this verify?"

## Checklist Before Writing Tests

- [ ] Am I testing REAL code, not mocks?
- [ ] Am I testing BEHAVIOR, not implementation?
- [ ] Do I understand what I'm mocking?
- [ ] Are mocks complete with all needed attributes?
- [ ] Does this test specify a requirement?
- [ ] Would this test exist without the implementation?

## Quick Reference

| Anti-Pattern | Detection | Fix |
|--------------|-----------|-----|
| Testing mocks | Test passes with any mock value | Call real code |
| Test-only methods | Methods only used in tests | Dependency injection |
| Blind mocking | Too many @mock.patch | Mock only boundaries |
| Incomplete mocks | AttributeError in tests | Add all used attributes |
| Afterthought tests | No clear purpose | Write tests FIRST |
