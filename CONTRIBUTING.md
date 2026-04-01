# Contributing Guide

## Development Setup

### Backend

```bash
cd backend
python -m venv .venv
.venv\\Scripts\\python -m pip install -r requirements.txt
.venv\\Scripts\\python -m pytest
```

### Frontend

```bash
cd frontend
pnpm install
pnpm build
pnpm test
```

## Coding Notes

- Keep backend layering as `api/routes -> services -> repositories -> models`.
- Add tests with every behavior change.
- Keep platform-specific code optional so the web build still works.
- Native packaging may require local Rust, Android Studio, or Xcode toolchains.
