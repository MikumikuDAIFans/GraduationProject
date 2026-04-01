#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../frontend"
pnpm install
pnpm build
pnpm cap:sync

echo "Capacitor web assets synced. Use 'pnpm cap:android' or 'pnpm cap:ios' to open native projects."
