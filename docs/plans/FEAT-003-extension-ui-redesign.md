# FEAT-003: Extension UI Redesign & Polish — Implementation Plan

Status: COMPLETE
Spec: specs/FEAT-003-extension-ui-redesign.md

## Context

FEAT-002 (Audio Pipeline Fix) is complete and committed. The extension UI is functional but rough: 3 tabs with a separate "Файлы" tab, two buttons (Start/Stop), briefing displayed as raw JSON dump, and the widget has only a basic pulse animation. This redesign merges tabs, adds a studio-style REC button, formats briefing beautifully, auto-shows briefing after upload, and adds equalizer animation to the widget.

## Files to Modify

| File | Tasks |
|------|-------|
| `extension/src/popup/popup.html` | 1, 2, 3, 4 |
| `extension/src/popup/popup.ts` | 1, 2, 3, 4 |
| `extension/src/popup/popup.css` | 1, 2, 3 |
| `extension/src/content/widget.ts` | 5, 6 |

## Progress Tracking

- [x] Task 1: Merge tabs — remove "Файлы", combine upload + briefing into one tab
- [x] Task 2: REC button — replace Start/Stop pair with single toggle
- [x] Task 3: Briefing formatting — structured HTML for portrait/strategy/objections
- [x] Task 4: Auto-show briefing after upload
- [x] Task 5: Widget equalizer bars animation
- [x] Task 6: Widget transcript highlight flash

**Total Tasks:** 6 | **Completed:** 6 | **Remaining:** 0
