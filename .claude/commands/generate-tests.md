---
description: Generate test scenarios from feature specifications
model: opus
---
# GENERATE TESTS: Spec-to-Test Pipeline

Generate comprehensive test scenarios and executable tests from a living specification using a sequential PM → Tester → Writer → Validation pipeline.

**Input:** `$ARGUMENTS` — `FEAT-NNN [--e2e --url=<url>]`

Examples:
- `FEAT-001` — Generate unit/integration tests only
- `FEAT-001 --e2e --url=http://localhost:3000` — Also generate E2E tests with live selector verification

---

## Step 1: Parse Arguments

1. **Parse `$ARGUMENTS`:**
   - Extract `FEAT-ID` (required, format: `FEAT-\d{3}`)
   - Check for `--e2e` flag (optional, enables E2E test generation)
   - Check for `--url=<url>` (required if `--e2e` is set)
   - If `--e2e` is present without `--url`, report error and stop

2. **Find and read the spec:**
   - Use `Glob(pattern="specs/FEAT-NNN-*.md")` to locate the spec file
   - If not found, report error: "No spec found for FEAT-NNN. Run `/specify FEAT-NNN` first."
   - `Read(file_path="specs/FEAT-NNN-name.md")`

3. **Validate spec has Acceptance Criteria:**
   - The spec must contain an `### Acceptance Criteria` section with at least one criterion
   - If missing, report error: "Spec FEAT-NNN has no acceptance criteria. Run `/specify FEAT-NNN` to add them."

4. **Store parsed values for pipeline:**
   - `FEAT_ID` — e.g., `FEAT-001`
   - `FEAT_NUM` — e.g., `001`
   - `SPEC_PATH` — full path to spec file
   - `SPEC_CONTENT` — full spec text
   - `E2E_ENABLED` — boolean
   - `E2E_URL` — URL string or null

5. **Ensure output directories exist:**
   ```bash
   mkdir -p tests/scenarios tests/unit tests/e2e
   ```

6. **Announce pipeline start:**
   ```
   Starting test generation pipeline for FEAT-NNN
   Source: specs/FEAT-NNN-name.md
   Mode: unit/integration [+ E2E at <url>]

   Pipeline: PM → Tester → Writer → Validation
   ```

---

## Step 2: PM Agent — Scenario Generation

**Use the Task tool** with `subagent_type: "general-purpose"` and model `sonnet`.

**Prompt the PM Agent with:**

```
You are a Product Manager extracting testable scenarios from a feature specification.

## Input Spec

<spec>
{SPEC_CONTENT}
</spec>

## Your Task

1. Read the specification carefully, focusing on:
   - Overview (understand the feature)
   - Acceptance Criteria (primary test scenarios)
   - Edge Cases (boundary and negative scenarios)
   - Behavior section (implementation details)

2. For EACH acceptance criterion, generate one or more Given/When/Then scenarios.

3. Add additional scenarios for:
   - **Happy paths** not explicitly stated but implied
   - **Edge cases** — empty inputs, max values, boundary conditions
   - **Negative cases** — invalid inputs, unauthorized access, missing data
   - **Boundary conditions** — limits, thresholds, transitions

4. For each scenario, provide:
   - A clear descriptive name
   - Type: happy_path / edge_case / negative / boundary
   - Priority: P0 (smoke) / P1 (regression) / P2 (edge case)
   - Given/When/Then in precise language
   - Test data examples where relevant

5. Write the output in EXACTLY this format:

# {FEAT_ID}: Test Scenarios

Generated: {TODAY_DATE}
Source: {SPEC_PATH}

## Scenarios

### S1: [Scenario Name]
- **Type:** [happy_path / edge_case / negative / boundary]
- **Priority:** [P0 / P1 / P2]
- **Given:** [precondition]
- **When:** [action]
- **Then:** [expected result]
- **Test Data:** [example data if relevant]

### S2: ...

(Continue for all scenarios)

## Coverage Notes
- [Any acceptance criteria that were difficult to translate to scenarios]
- [Assumptions made during scenario generation]

IMPORTANT: Output ONLY the markdown document. No preamble, no explanation.
```

**After the PM Agent completes:**
1. Write the output to `tests/scenarios/FEAT-NNN-scenarios.md`
2. Read it back to verify it was written correctly
3. Count the number of scenarios generated
4. Report: "PM Agent: Generated N scenarios → tests/scenarios/FEAT-NNN-scenarios.md"

---

## Step 3: Tester Agent — Test Matrix & Coverage Analysis

**Use the Task tool** with `subagent_type: "general-purpose"` and model `sonnet`.

**Prompt the Tester Agent with:**

```
You are a QA Engineer creating a test matrix from generated scenarios.

## Input Scenarios

<scenarios>
{SCENARIOS_CONTENT from Step 2 output}
</scenarios>

## Original Spec (for coverage verification)

<spec>
{SPEC_CONTENT}
</spec>

## Your Task

1. Read all scenarios from the PM Agent output.

2. Classify each scenario:
   - **smoke** — Critical happy path, must pass for release
   - **regression** — Important functionality, run on every change
   - **edge_case** — Boundary conditions, unusual inputs
   - **negative** — Invalid inputs, error handling

3. Assign priority:
   - **P0** — Smoke tests, blocks release if failing
   - **P1** — Regression tests, should pass but non-blocking
   - **P2** — Edge cases, nice to have

4. Verify coverage against acceptance criteria:
   - Extract EVERY acceptance criterion from the spec
   - Map each criterion to one or more scenarios
   - Flag any criteria with NO scenario coverage as "MISSING"

5. Write the output in EXACTLY this format:

# {FEAT_ID}: Test Matrix

## Summary
- Total scenarios: N
- P0 (smoke): N
- P1 (regression): N
- P2 (edge cases): N

## Coverage vs Acceptance Criteria

| Acceptance Criterion | Scenarios | Coverage |
|---------------------|-----------|----------|
| [criterion from spec] | S1, S3 | Covered |
| [criterion from spec] | — | MISSING |

## Missing Coverage

[If any acceptance criteria are not covered, list them here with suggested scenarios to add.
If all criteria are covered, write "All acceptance criteria are covered."]

## Matrix

| ID | Name | Type | Priority | Automated |
|----|------|------|----------|-----------|
| S1 | [name] | smoke | P0 | Yes |
| S2 | [name] | regression | P1 | Yes |
...

IMPORTANT: Output ONLY the markdown document. No preamble, no explanation.
```

**After the Tester Agent completes:**
1. Write the output to `tests/scenarios/FEAT-NNN-matrix.md`
2. Read it back to verify it was written correctly
3. Check for any "MISSING" coverage items
4. If there are MISSING items, report them to the user but continue the pipeline
5. Report: "Tester Agent: Matrix created with N scenarios (P0: X, P1: Y, P2: Z) → tests/scenarios/FEAT-NNN-matrix.md"

---

## Step 4: Test Writer Agent — Generate Executable Tests

**Use the Task tool** with `subagent_type: "general-purpose"` and model `opus`.

This agent requires higher capability because it generates working test code.

**Prompt the Test Writer Agent with:**

```
You are a Senior Test Engineer writing executable test code from a test matrix.

## Scenarios

<scenarios>
{SCENARIOS_CONTENT from Step 2}
</scenarios>

## Test Matrix

<matrix>
{MATRIX_CONTENT from Step 3}
</matrix>

## Original Spec

<spec>
{SPEC_CONTENT}
</spec>

## Configuration
- E2E Enabled: {E2E_ENABLED}
- E2E URL: {E2E_URL or "N/A"}
- Feature ID: {FEAT_ID}
- Feature Number: {FEAT_NUM}

## Your Task

### Unit/Integration Tests

Determine the tech stack from the spec and project structure:
- **Python project** → Generate pytest files
- **TypeScript/React project** → Generate Jest files
- **Both** → Generate both

For EACH scenario in the matrix:

1. **Name the test** using the convention:
   - Python: `test_<action>_<condition>_<expected_result>`
   - TypeScript: `it('should <behavior> when <condition>')`

2. **Structure the test** using Arrange/Act/Assert (AAA):
   - Arrange: Set up preconditions from "Given"
   - Act: Perform the action from "When"
   - Assert: Verify the result from "Then"

3. **Group tests** by feature area into separate files:
   - `tests/unit/test_feat_{NNN}_<area>.py` (Python)
   - `tests/unit/feat-{NNN}-<area>.test.ts` (TypeScript)

4. **Include proper imports, fixtures, and setup/teardown.**

5. **Add docstrings/comments** referencing the scenario ID (S1, S2, etc.).

### E2E Tests (only if E2E Enabled)

If E2E is enabled:

1. Generate Playwright test files: `tests/e2e/feat_{NNN}_<area>.spec.ts`

2. Structure E2E tests with:
   - `test.describe` blocks for feature areas
   - `test.beforeEach` for navigation to {E2E_URL}
   - Proper page object patterns if the page is complex
   - Screenshot on failure

3. Use reliable selectors:
   - Prefer `data-testid` attributes
   - Fall back to accessible roles and labels
   - Avoid brittle CSS selectors

4. Add reasonable timeouts and wait conditions.

## Output Format

For EACH test file you generate, output it in this format:

---FILE: tests/unit/test_feat_{NNN}_example.py---
```python
[complete test file content]
```

---FILE: tests/e2e/feat_{NNN}_example.spec.ts---
```typescript
[complete test file content]
```

List ALL files at the end:
---FILES_CREATED---
- tests/unit/test_feat_{NNN}_example.py
- [other files...]

IMPORTANT: Output ONLY the file contents in the format above. No preamble, no explanation outside of code comments.
```

**After the Test Writer Agent completes:**

1. **Parse the output** to extract individual files:
   - Split on `---FILE: <path>---` markers
   - Extract the code block content for each file

2. **Write each file** to disk at the specified path

3. **Update the test matrix** — Edit `tests/scenarios/FEAT-NNN-matrix.md`:
   - Fill in the "Automated" column with actual test file paths
   - Use Edit tool to update the Matrix table

4. Report: "Test Writer Agent: Generated N test files"
   - List each file path

---

## Step 5: Validation — Run Tests & Generate Coverage Report

**Run the generated tests directly (no sub-agent needed).**

### 5.1 Run Unit/Integration Tests

```bash
# Python tests
uv run pytest tests/unit/test_feat_NNN_*.py -v --tb=short 2>&1 || true

# TypeScript tests (if generated)
npx jest tests/unit/feat-NNN-*.test.ts --verbose 2>&1 || true
```

Capture the output: test count, pass count, fail count.

### 5.2 Run E2E Tests (if enabled)

```bash
npx playwright test tests/e2e/feat_NNN_*.spec.ts --reporter=list 2>&1 || true
```

### 5.3 Fix Failing Tests (up to 2 attempts)

If any tests fail:

1. **Read the failure output** carefully
2. **Identify the root cause:**
   - Import errors → Fix imports
   - Missing fixtures → Add fixtures
   - Wrong assertions → Correct expected values
   - Missing implementation → Mark as `@pytest.mark.skip(reason="Needs implementation")`
3. **Edit the failing test file** to fix the issue
4. **Re-run the specific failing test** to verify the fix
5. **Repeat once** if still failing (max 2 fix attempts per test)
6. After 2 failed attempts, skip the test with a clear reason

### 5.4 Generate Coverage Report

Write `tests/scenarios/FEAT-NNN-coverage.md`:

```markdown
# FEAT-NNN: Test Coverage Report

Generated: {TODAY_DATE}
Source Spec: {SPEC_PATH}

## Results
- Tests run: N
- Passed: N
- Failed: N
- Skipped: N

## Test Files

| Test File | Tests | Passed | Failed | Skipped |
|-----------|-------|--------|--------|---------|
| tests/unit/test_feat_NNN_xxx.py | N | N | N | N |
| ... | ... | ... | ... | ... |

## Acceptance Criteria Coverage

| Criterion | Scenarios | Tests | Status |
|-----------|-----------|-------|--------|
| [criterion] | S1, S3 | test_xxx, test_yyy | PASS / FAIL / SKIP |
| [criterion] | — | — | NOT COVERED |

## Notes
- [Any issues encountered during test generation]
- [Tests that were skipped and why]
- [Recommendations for additional manual testing]
```

---

## Step 6: Final Report

Present a summary to the user:

```
Test Generation Complete for FEAT-NNN

Pipeline Results:
1. PM Agent:     N scenarios generated
2. Tester Agent: Matrix created (P0: X, P1: Y, P2: Z)
3. Test Writer:  N test files generated
4. Validation:   N passed, N failed, N skipped

Generated Files:
- tests/scenarios/FEAT-NNN-scenarios.md   (scenarios)
- tests/scenarios/FEAT-NNN-matrix.md      (test matrix)
- tests/scenarios/FEAT-NNN-coverage.md    (coverage report)
- tests/unit/test_feat_NNN_*.py           (unit tests)
- tests/e2e/feat_NNN_*.spec.ts            (E2E tests, if --e2e)

Coverage: X/Y acceptance criteria covered

Next steps:
- Review generated tests in tests/unit/ and tests/e2e/
- Implement the feature code to make skipped tests pass
- Run /verify FEAT-NNN after implementation
```

---

## Critical Rules

1. **Sequential pipeline** — Each step depends on the previous step's output. Never run steps in parallel.
2. **PM and Tester use sonnet** — These agents classify and organize; they do not need opus.
3. **Test Writer uses opus** — Code generation requires higher capability.
4. **Always write intermediate files** — Scenarios and matrix files must be written to disk before the next step reads them.
5. **Do not invent requirements** — All scenarios must trace back to the spec's acceptance criteria or explicitly stated edge cases.
6. **Fix failures, then skip** — Attempt to fix failing tests twice. After that, skip with a reason rather than deleting.
7. **Preserve existing tests** — If test files already exist for this FEAT-ID, do not overwrite. Append new tests or report the conflict to the user.
8. **Use today's date** — All generated files use the current date.
9. **Read before writing** — Always read the spec and verify output files after writing.
10. **Report missing coverage** — If any acceptance criterion has no test coverage, explicitly flag it in the coverage report and the final summary.
