#!/bin/bash
# Skill Enforcer Hook
# Reminds Claude to activate relevant skills before implementation

cat <<'EOF'
INSTRUCTION: SKILL ACTIVATION CHECK

Before proceeding with implementation, check if any skills are relevant:

Available Skills:
- backend-python: Python/FastAPI development
- frontend-react: React/Next.js components
- testing-patterns: Writing tests
- architect-standards: Planning and design
- web-design-guidelines: UI/UX and accessibility
- devops-standards: Docker, CI/CD, security

IF working with:
- Python files (*.py) → Activate: backend-python
- React/TSX files (*.tsx) → Activate: frontend-react
- Test files (test_*, *.test.*) → Activate: testing-patterns
- Dockerfiles, CI/CD → Activate: devops-standards
- UI components → Activate: web-design-guidelines
- Planning/Architecture → Activate: architect-standards

HOW TO ACTIVATE:
Use the Skill tool: Skill(skill-name)

Example:
  "Relevant skills: backend-python, testing-patterns"
  [Activates Skill(backend-python), Skill(testing-patterns)]
  [Proceeds with implementation]

CRITICAL: Actually activate skills via Skill() tool.
Mentioning a skill without activating it provides no benefit.
EOF
