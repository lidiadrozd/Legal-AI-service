#!/usr/bin/env bash
# Run on the verified production host. Arguments: archive, SHA256, unique release name.
set -euo pipefail
archive="${1:?archive required}"
expected="${2:?SHA256 required}"
release="${3:?release name required}"
[[ "$release" =~ ^[a-zA-Z0-9-]+$ ]] || exit 1
site=/var/www/legalai-service
stage="/opt/legal-ai-releases/$release"
backup="/var/backups/legal-ai/frontend-before-$release.tar.gz"
test -f "$site/index.html"
test ! -e "$stage"
test ! -e "$backup"
printf '%s  %s\n' "$expected" "$archive" | sha256sum -c -
mkdir -p /var/backups/legal-ai "$stage"
tar -czf "$backup" -C "$site" .
tar -xzf "$archive" -C "$stage"
test -f "$stage/index.html"
test -d "$stage/assets"
mkdir -p "$site/assets"
cp -a "$stage/assets/." "$site/assets/"
find "$site/assets" -type d -exec chmod 755 {} +
find "$site/assets" -type f -exec chmod 644 {} +
cp "$stage/index.html" "$site/index.html.new"
chmod 644 "$site/index.html.new"
mv "$site/index.html.new" "$site/index.html"
if ! curl --max-time 20 -fsS https://135-106-163-146.nip.io/api/health ||
   ! curl --max-time 20 -fsS https://135-106-163-146.nip.io/ -o "$stage/served.html" ||
   ! cmp -s "$site/index.html" "$stage/served.html"; then
  tar -xzf "$backup" -C "$stage" ./index.html
  cp "$stage/index.html" "$site/index.html.rollback"
  chmod 644 "$site/index.html.rollback"
  mv "$site/index.html.rollback" "$site/index.html"
  echo "Verification failed; previous index restored." >&2
  exit 1
fi
printf '\nPublished %s; backup: %s\n' "$release" "$backup"
