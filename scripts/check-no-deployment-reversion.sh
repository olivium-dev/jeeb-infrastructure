#!/usr/bin/env bash

set -euo pipefail

blocked_word='roll''back'
blocked_phrase='roll[[:space:]-]+back|rolling[[:space:]-]+back'
blocked_pattern="${blocked_word}|${blocked_phrase}"
found=0

while IFS= read -r -d '' file; do
  [ -f "$file" ] || continue
  if rg --binary -n -i -e "$blocked_pattern" "$file"; then
    echo "Forbidden deployment reversion reference: $file" >&2
    found=1
  fi
done < <(git ls-files --cached --others --exclude-standard -z)

if [ "$found" -ne 0 ]; then
  echo "Deployment reversion audit failed. Recovery must pause and fix forward." >&2
  exit 1
fi

echo "Deployment reversion audit passed."
