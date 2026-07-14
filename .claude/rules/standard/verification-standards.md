## Verification Standards

**Core Rule:** Tests passing does not equal program working. Always execute the real program and show concrete evidence before claiming success.

---

### Section 1: When to Execute

Run the actual program after tests pass. Tests use mocks and fixtures -- they don't prove the real program works.

**Execute after:**
- Tests pass
- Refactoring code
- Modifying imports or dependencies
- Changing configuration
- Working with entry points
- Before marking any task complete

**If there's a runnable program, RUN IT.**

#### How to Execute by Type

**Scripts/CLI Tools:**
```bash
python script.py --args
node cli.js command
# Verify: exit code, stdout/stderr, file changes
```

**API Services:**
```bash
npm start
# Or: python -m uvicorn app:app
curl http://localhost:8000/api/endpoint
# Verify: response status, payload, database changes
```

**ETL/Data Pipelines:**
```bash
python etl/pipeline.py
# Verify: logs, database records, output files
```

**Build Artifacts:**
```bash
npm run build    # or: python -m build
node dist/index.js  # Run the built artifact, not source
```

#### When to Skip Execution

Skip ONLY for:
- Documentation-only changes
- Test-only changes
- Pure internal refactoring (no entry points affected)
- Configuration files (where validation is the execution)

**If uncertain, execute.**

#### Common Issues Caught by Execution

- **Import errors:** Tests mock imports, real code has wrong paths
- **Missing dependencies:** Tests mock libraries, real program needs installed packages
- **Configuration errors:** Tests use fixtures, real program reads missing env vars
- **Build issues:** Tests run source, built package has missing files
- **Path issues:** Tests run from project root, real program runs from different directory

#### When Execution Fails After Tests Pass

1. This is a real bug -- don't ignore it
2. Fix the issue immediately
3. Run tests again (should still pass)
4. Execute again to verify fix
5. Add test to catch this failure type

---

### Section 2: Evidence Requirements

NO completion claims without executing verification commands and showing output in the current message. **If you haven't run the command in this message, you cannot claim it passes.**

#### Verification Workflow

Before ANY claim of success, completion, or correctness:

1. **Identify** - What command proves this claim?
2. **Execute** - Run the FULL command (not partial, not cached)
3. **Read** - Check exit code, count failures, read full output
4. **Confirm** - Does output actually prove the claim?
5. **Report** - State claim WITH evidence from step 3

#### What Requires Verification

| Claim                   | Required Evidence           | Insufficient                |
| ----------------------- | --------------------------- | --------------------------- |
| "Tests pass"            | Fresh test run: 0 failures  | Previous run, "should pass" |
| "Linter clean"          | Linter output: 0 errors     | Partial check, assumption   |
| "Build succeeds"        | Build command: exit 0       | Linter passing              |
| "Bug fixed"             | Test reproducing bug passes | Code changed                |
| "Regression test works" | Red-green cycle verified    | Test passes once            |
| "Requirements met"      | Line-by-line checklist      | Tests passing               |
| "Program works"         | Ran program, showed logs    | "Tests pass so it works"    |

#### Correct vs Incorrect Patterns

**Tests:**
- Yes: Run `pytest` then see "34 passed" then report "All 34 tests pass"
- No: "Should pass now" / "Tests look correct"

**Build:**
- Yes: Run `npm run build` then exit 0 then report "Build succeeds"
- No: "Linter passed, so build should work"

**Execution:**
- Yes: "Ran `python app.py` - output: [paste logs]"
- Yes: "Server started on port 8000, GET /health returned 200"
- No: "I'm confident the imports are correct"
- No: "It will probably work"

#### Stop Signals

Run verification immediately if you're about to:
- Use uncertain language: "should", "probably", "seems to", "looks like"
- Express satisfaction: "Great!", "Perfect!", "Done!", "All set!"
- Commit, push, or create PR
- Mark task complete or move to next task
- Trust agent/tool reports without independent verification

#### Integration with TDD

1. Write failing test (RED)
2. Verify test fails correctly
3. Write minimal code (GREEN)
4. Verify tests pass
5. **RUN ACTUAL PROGRAM** -- don't skip
6. Verify real output matches expectations
7. Refactor if needed
8. Re-verify execution
9. Mark complete

Tests validate logic. Execution validates integration.

---

### Section 3: Quick Reference

#### Execution Triggers

| Situation              | Action          |
| ---------------------- | --------------- |
| Tests just passed      | Execute program |
| About to mark complete | Execute program |
| Changed imports        | Execute program |
| Refactored code        | Execute program |
| Modified config        | Execute program |
| Uncertain if needed    | Execute program |
| Documentation only     | Skip execution  |

**Default action: Execute.**

#### Completion Checklist

Before marking work complete:

- [ ] All tests pass
- [ ] Executed actual program
- [ ] Verified real output (shown evidence in current message)
- [ ] No import/module errors or runtime exceptions
- [ ] Side effects correct (files created, DB updated, API called)
- [ ] Configuration and dependencies resolved

**If you can't check all boxes, the work isn't complete.**

**The rule exists because assumptions fail. Evidence doesn't.**
