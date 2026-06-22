# Microphone Selection in Extension Settings

**Date:** 2026-03-10
**Status:** Approved

## Summary

Add a microphone device selector to the extension settings panel. Users pick their preferred mic from a dropdown; the choice persists in `chrome.storage.local` and is used on every recording session.

## UI Changes (sidepanel.html)

Replace the static mic status block in `#mic-settings` with:
- `<select id="mic-select">` populated by `enumerateDevices()` (filtered to `audioinput`)
- First option: "По умолчанию (системный)" with empty value
- "Настроить микрофон" button remains for first-time permission grant
- After permission granted, select becomes visible and populated

## Data Flow

```
sidepanel: saves selectedMicId to chrome.storage.local on <select> change
service-worker: reads selectedMicId from storage before sending START_SESSION
offscreen: receives deviceId in message, passes to getUserMedia constraints
```

## File Changes

| File | Change |
|------|--------|
| `sidepanel.html` | Add `<select id="mic-select">`, keep grant button |
| `sidepanel.ts` | `populateMicList()`, save selection, listen to `devicechange` |
| `service-worker.ts` | Read `selectedMicId` from storage, include in START_SESSION payload |
| `offscreen.ts` | Accept `deviceId`, use in `getUserMedia({ audio: { deviceId: { exact: id } } })` |

## Edge Cases

- Device disconnected between selection and recording: fallback to default (empty deviceId)
- Device list empty before permission: show "Сначала настройте микрофон"
- `devicechange` event: refresh list, validate selected device still exists
