---
name: E2E Testing with Agent Browser
description: Execute E2E tests using agent-browser CLI for token-efficient browser automation. 40% more efficient than chrome-dev-tools MCP. Use this skill when running user journey tests, validating forms, checking frontend changes, or debugging UI issues. Triggered by requests like "run e2e test", "test user journey", "validate form", "check frontend", "test the form", "verify the page works", "run browser test", "execute user flow".
---

# E2E Testing with Agent Browser

**Core Rule:** Use agent-browser CLI for all browser automation. 40% more token-efficient than chrome-dev-tools MCP.

## When to use this skill

- When executing user journey tests from user-journeys directory
- When validating form submissions and user interactions
- When checking frontend changes work correctly
- When debugging UI issues in the browser
- When capturing screenshots for verification
- When testing multi-step user flows
- When verifying page state after changes

## Prerequisites

```bash
# Install agent-browser (one-time setup)
bun add -g agent-browser playwright
agent-browser install
```

## Core Workflow

### 1. Navigate to Page

```bash
agent-browser open https://example.com
```

### 2. Get Interactive Elements (Snapshot)

```bash
# Get all interactive elements with refs (@e1, @e2, etc.)
agent-browser snapshot -i

# Compact output (less tokens)
agent-browser snapshot -i -c

# Limit depth for complex pages
agent-browser snapshot -i -d 3
```

**Output example:**
```
@e1 button "Submit"
@e2 textbox "Email"
@e3 textbox "Password"
@e4 link "Forgot password?"
```

### 3. Interact Using Refs

```bash
# Click element
agent-browser click @e1

# Fill input field
agent-browser fill @e2 "user@example.com"

# Press keys
agent-browser press Enter
agent-browser press Tab
```

### 4. Re-snapshot After Changes

After any interaction that changes the page, take a new snapshot:

```bash
agent-browser snapshot -i -c
```

## Command Reference

### Navigation

| Command | Description |
|---------|-------------|
| `agent-browser open <url>` | Navigate to URL |
| `agent-browser back` | Go back in history |
| `agent-browser forward` | Go forward |
| `agent-browser reload` | Reload page |
| `agent-browser close` | Close browser |

### Analysis

| Command | Description |
|---------|-------------|
| `agent-browser snapshot` | Full accessibility tree |
| `agent-browser snapshot -i` | Interactive elements only |
| `agent-browser snapshot -i -c` | Compact interactive (recommended) |
| `agent-browser snapshot -d 3` | Limit depth to 3 levels |
| `agent-browser snapshot -s @e5` | Scope to element and children |

### Interactions

| Command | Description |
|---------|-------------|
| `agent-browser click @e1` | Click element |
| `agent-browser fill @e2 "text"` | Fill input with text |
| `agent-browser type "text"` | Type text (keystroke by keystroke) |
| `agent-browser press Enter` | Press keyboard key |
| `agent-browser hover @e3` | Hover over element |
| `agent-browser check @e4` | Check checkbox |
| `agent-browser uncheck @e4` | Uncheck checkbox |
| `agent-browser select @e5 "option"` | Select dropdown option |
| `agent-browser scroll down` | Scroll down |
| `agent-browser scroll @e6` | Scroll element into view |

### Semantic Locators (Alternative to Refs)

When refs aren't available or you need flexibility:

```bash
# Find by role
agent-browser find role button click
agent-browser find role textbox fill "value"

# Find by visible text
agent-browser find text "Submit" click
agent-browser find text "Login" click

# Find by label
agent-browser find label "Email" fill "user@example.com"
agent-browser find label "Password" fill "secret123"

# Find by placeholder
agent-browser find placeholder "Enter email" fill "user@example.com"
```

### Data Extraction

| Command | Description |
|---------|-------------|
| `agent-browser get text @e1` | Get element text content |
| `agent-browser get html @e1` | Get innerHTML |
| `agent-browser get value @e2` | Get input value |
| `agent-browser get title` | Get page title |
| `agent-browser get url` | Get current URL |

### Verification

| Command | Description |
|---------|-------------|
| `agent-browser visible @e1` | Check if visible |
| `agent-browser enabled @e1` | Check if enabled |
| `agent-browser checked @e1` | Check if checked |
| `agent-browser count "selector"` | Count matching elements |

### Screenshots & Recording

| Command | Description |
|---------|-------------|
| `agent-browser screenshot` | Screenshot to stdout |
| `agent-browser screenshot ./path.png` | Save screenshot |
| `agent-browser screenshot --full` | Full page screenshot |
| `agent-browser video start` | Start recording |
| `agent-browser video stop ./video.mp4` | Stop and save |

### Waiting

| Command | Description |
|---------|-------------|
| `agent-browser wait 2000` | Wait milliseconds |
| `agent-browser wait network` | Wait for network idle |
| `agent-browser wait @e1` | Wait for element visible |
| `agent-browser wait text "Success"` | Wait for text to appear |

### Console & Errors

```bash
# View console messages
agent-browser console

# View errors only
agent-browser console --errors
```

## User Journey Testing Pattern

### Standard E2E Test Flow

```bash
# 1. Open the page
agent-browser open https://mysite.com/form

# 2. Get interactive elements
agent-browser snapshot -i -c

# 3. Fill form fields using refs from snapshot
agent-browser fill @e1 "John Doe"
agent-browser fill @e2 "john@example.com"
agent-browser fill @e3 "+1234567890"

# 4. Submit form
agent-browser click @e4  # Submit button

# 5. Wait for response
agent-browser wait network

# 6. Verify success
agent-browser snapshot -i -c
agent-browser get text @e5  # Success message

# 7. Screenshot for evidence
agent-browser screenshot ./test-result.png
```

### Form Filling Example

```bash
# Open form
agent-browser open https://example.com/contact

# Get elements
agent-browser snapshot -i -c

# Fill using semantic locators (more stable)
agent-browser find label "Name" fill "Test User"
agent-browser find label "Email" fill "test@test.com"
agent-browser find label "Message" fill "This is a test message"

# Submit
agent-browser find role button click

# Verify
agent-browser wait text "Thank you"
agent-browser screenshot ./form-success.png
```

### Multi-step Flow Example

```bash
# Step 1: Login
agent-browser open https://app.example.com/login
agent-browser snapshot -i -c
agent-browser find label "Email" fill "user@example.com"
agent-browser find label "Password" fill "password123"
agent-browser find text "Sign in" click
agent-browser wait network

# Step 2: Navigate to dashboard
agent-browser wait text "Dashboard"
agent-browser snapshot -i -c

# Step 3: Perform action
agent-browser find text "Create New" click
agent-browser wait network
agent-browser snapshot -i -c

# Step 4: Fill and submit
agent-browser find label "Title" fill "Test Item"
agent-browser find role button click
agent-browser wait text "Created successfully"
```

## Error Handling

### Check for Errors

```bash
# After each action, check console for errors
agent-browser console --errors

# Check if element exists before interacting
agent-browser visible @e1
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Element not found | Re-run `snapshot -i -c` to get fresh refs |
| Stale refs | Refs change after page updates, always re-snapshot |
| Timeout | Use `wait network` or `wait @element` |
| Wrong element clicked | Use semantic locators for stability |

## Session Management

```bash
# Use named sessions for isolation
agent-browser open https://site.com --session test1

# Persist authentication
agent-browser open https://site.com --profile ./auth-profile
```

## Best Practices

### Token Efficiency

1. **Use `-i -c` flags** for compact interactive-only snapshots
2. **Limit depth** with `-d 3` on complex pages
3. **Scope snapshots** with `-s @e5` when only part of page matters
4. **Use semantic locators** instead of full snapshots when possible

### Stability

1. **Re-snapshot after interactions** that change the page
2. **Use semantic locators** for elements that might change position
3. **Wait for network** after form submissions
4. **Wait for specific text** to confirm page state

### Debugging

1. **Take screenshots** at key points
2. **Check console errors** after failures
3. **Use video recording** for complex flows

## Integration with User Journeys

When reading user journey files:

1. Parse the journey steps
2. Translate each step to agent-browser commands
3. Execute commands sequentially
4. Capture screenshots at checkpoints
5. Collect errors and report

## Quick Reference

```bash
# Most common workflow
agent-browser open <url>
agent-browser snapshot -i -c
agent-browser fill @eN "value"
agent-browser click @eN
agent-browser wait network
agent-browser snapshot -i -c
agent-browser screenshot ./result.png
```

## Cloud Providers

```bash
# Browserbase (cloud browser)
export BROWSERBASE_API_KEY=your-key
agent-browser open https://example.com -p browserbase

# Browser Use
export BROWSER_USE_API_KEY=your-key
agent-browser open https://example.com -p browseruse
```

## Comparison with Chrome Dev Tools MCP

| Aspect | Chrome Dev Tools MCP | Agent Browser |
|--------|---------------------|---------------|
| Tokens per form test | ~15k | ~9k |
| Interface | MCP tools | CLI commands |
| Element refs | Complex selectors | Simple @e1, @e2 |
| Learning curve | Higher | Lower |
| Speed | Good | Fast (Rust CLI) |
