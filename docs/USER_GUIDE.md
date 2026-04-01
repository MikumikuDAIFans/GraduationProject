# MA-IPAAS User Guide

## Core Workflow

1. Open the workspace and complete your profile with home/work locations and commute preference.
2. Add events or tasks from the UI or ask the assistant in natural language.
3. Review reminders, suggestions, and inbox follow-ups in the side panels.
4. Confirm assistant schedule proposals when the suggested time blocks look right.

## Notifications

- Web: browser notifications and in-page toast notifications
- Desktop shell: Tauri notification plugin
- Mobile shell: Capacitor local notifications

## Voice

- `POST /api/assistant/voice` accepts audio uploads and transcribes them into assistant messages.
- `POST /api/assistant/speak` converts assistant text into playable MP3 audio.

## Offline Support

- The frontend registers `/sw.js` and caches the shell assets plus the web manifest.
- Core UI can reopen when the network is unavailable, but dynamic API data still depends on the backend.
