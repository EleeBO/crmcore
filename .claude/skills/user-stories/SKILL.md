---
name: user-stories
description: Writing effective user stories with acceptance criteria, edge cases, and testable requirements. Use when documenting features or planning sprints.
---

# User Stories Skill

**Core Rule:** User stories describe VALUE, not implementation. Focus on WHO, WHAT, WHY.

## When to Use

- Documenting features before implementation
- Sprint planning
- Requirements gathering
- Backlog grooming

## User Story Format

```markdown
## US-001: [Short Title]

**As a** [role/persona]
**I want to** [action/feature]
**So that** [benefit/value]

### Acceptance Criteria

Given [precondition]
When [action]
Then [expected result]

### Edge Cases
- [ ] What if [edge case 1]?
- [ ] What if [edge case 2]?

### Out of Scope
- [Explicitly excluded feature]

### Technical Notes
- [Implementation hints if needed]
```

## Story Types

### Feature Story
```markdown
## US-042: User Profile Photo Upload

**As a** registered user
**I want to** upload a profile photo
**So that** other users can recognize me visually

### Acceptance Criteria

**AC1: Upload Flow**
- Given I am on my profile settings page
- When I click "Change Photo" and select an image file
- Then the image is uploaded and displayed as my avatar

**AC2: File Validation**
- Given I try to upload a file
- When the file is larger than 5MB or not an image
- Then I see an error message and the upload is rejected

**AC3: Crop/Resize**
- Given I upload a valid image
- When the image is not square
- Then I am shown a crop interface to select the area

### Edge Cases
- [ ] User uploads animated GIF → Accept, show first frame as static
- [ ] User on slow connection → Show upload progress
- [ ] Upload fails midway → Allow retry, show clear error
- [ ] User has no existing photo → Show default avatar

### Out of Scope
- Video upload
- Multiple photos
- AI-generated avatars
```

### CRUD Story
```markdown
## US-101: Manage Users (Admin)

**As an** administrator
**I want to** create, view, edit, and delete user accounts
**So that** I can manage platform access

### Acceptance Criteria

**AC1: List Users**
- Given I am on the Users page
- When the page loads
- Then I see a paginated table with: Name, Email, Role, Status, Created Date
- And I can sort by any column
- And I can filter by status and role
- And I can search by name or email

**AC2: Create User**
- Given I click "Add User"
- When I fill in required fields (name, email, role) and submit
- Then a new user is created
- And they receive a welcome email with password setup link

**AC3: Edit User**
- Given I click "Edit" on a user row
- When I modify fields and save
- Then changes are persisted
- And audit log records the change

**AC4: Delete User**
- Given I click "Delete" on a user row
- When I confirm the deletion
- Then the user is soft-deleted (not permanently removed)
- And they can no longer log in

### Data Fields
| Field | Type | Required | Validation |
|-------|------|----------|------------|
| Name | string | ✓ | 2-100 chars |
| Email | string | ✓ | Valid email, unique |
| Role | enum | ✓ | admin, manager, user |
| Status | enum | - | active (default), inactive, suspended |

### Edge Cases
- [ ] Delete yourself → Blocked with message
- [ ] Duplicate email → Show validation error
- [ ] Last admin → Cannot delete or change role
```

### Integration Story
```markdown
## US-201: Stripe Payment Integration

**As a** customer
**I want to** pay for my subscription with a credit card
**So that** I can access premium features

### Acceptance Criteria

**AC1: Checkout Flow**
- Given I select a subscription plan
- When I click "Subscribe"
- Then I am redirected to Stripe Checkout
- And I can enter payment details securely

**AC2: Success**
- Given I complete payment on Stripe
- When payment succeeds
- Then I am redirected back with success message
- And my subscription is activated immediately
- And I receive confirmation email

**AC3: Failure**
- Given I complete payment on Stripe
- When payment fails
- Then I am redirected back with error message
- And I can retry with different card

**AC4: Webhook**
- Given Stripe sends a webhook event
- When it's a valid subscription event
- Then our backend updates the subscription status

### Out of Scope
- Multiple payment methods (PayPal, etc.)
- Manual invoicing
- Refund processing (handled in Stripe dashboard)
```

## Story Sizing

| Size | Description | Typical Effort |
|------|-------------|----------------|
| **XS** | Trivial change, single file | < 2 hours |
| **S** | Simple feature, few files | 2-4 hours |
| **M** | Standard feature, multiple components | 1-2 days |
| **L** | Complex feature, cross-cutting | 3-5 days |
| **XL** | Epic, needs breakdown | > 1 week |

**Rule:** If story is L or XL, break it down into smaller stories.

## Definition of Done

```markdown
### DoD Checklist
- [ ] Code complete and pushed
- [ ] All acceptance criteria met
- [ ] Unit tests written (coverage > 80%)
- [ ] Integration tests for happy path
- [ ] Code reviewed and approved
- [ ] Documentation updated
- [ ] No critical/major bugs
- [ ] Deployed to staging
- [ ] QA verified
- [ ] Product owner accepted
```

## User Personas

Define personas once, reference in stories:

```markdown
## Persona: Admin (Alice)

**Role:** System Administrator
**Goals:**
- Manage all users and their permissions
- Monitor system health
- Handle escalated issues

**Pain Points:**
- Bulk operations are slow
- No audit trail for changes
- Complex reports require IT help

**Tech Savviness:** High
```

## Story Mapping Template

```
Epic: User Management
├── US-101: List users
├── US-102: Create user
├── US-103: Edit user
├── US-104: Delete user
├── US-105: Bulk import users
├── US-106: Export users to CSV
└── US-107: User activity log
```

## Anti-Patterns

**❌ BAD: Implementation-focused**
```
As a developer, I want to add a users table to the database...
```

**✅ GOOD: Value-focused**
```
As an admin, I want to manage user accounts so I can control platform access...
```

**❌ BAD: Too vague**
```
As a user, I want the app to be fast...
```

**✅ GOOD: Specific and testable**
```
As a user, I want pages to load within 2 seconds so I don't lose patience...
```

**❌ BAD: No acceptance criteria**
```
As a user, I want to upload files.
```

**✅ GOOD: Clear criteria**
```
As a user, I want to upload files (max 10MB, images/PDFs only) to attach to my reports...
```

## Quick Reference

```markdown
# Story Template (Copy-Paste)

## US-XXX: [Title]

**As a** [role]
**I want to** [feature]
**So that** [benefit]

### Acceptance Criteria

**AC1: [Name]**
- Given [context]
- When [action]
- Then [result]

### Edge Cases
- [ ] [Edge case 1]

### Out of Scope
- [Excluded]

### Size: [XS/S/M/L/XL]
```
