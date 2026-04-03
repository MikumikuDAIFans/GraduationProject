# MA-IPAAS Mobile Build Guide

## Prerequisites

- Node.js 18+
- `pnpm`
- Android Studio for Android builds
- Xcode on macOS for iOS builds

## Setup

```bash
cd frontend
pnpm install
pnpm build
pnpm cap:sync
```

## Android

```bash
cd frontend
pnpm cap:android
```

## iOS

```bash
cd frontend
pnpm cap:ios
```
