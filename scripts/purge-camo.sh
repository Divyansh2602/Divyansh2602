#!/usr/bin/env bash
# Purge GitHub's image proxy cache for the profile README.
#
# Why this exists: GitHub does not hotlink README images directly. It proxies
# every one through camo.githubusercontent.com and caches the result hard. So
# the daily-regenerated snake and 3D graphs can sit stale on the profile for
# hours even though this repo already has the new SVG committed — the workflow
# looks green while the profile shows yesterday's picture.
#
# Camo honours an HTTP PURGE on an asset URL, so: fetch the rendered profile
# page, scrape the camo URLs out of it, and purge each one.
#
# Usage: ./scripts/purge-camo.sh <github-username>
set -uo pipefail

USER="${1:?usage: purge-camo.sh <github-username>}"
PROFILE_URL="https://github.com/${USER}"

echo "Fetching rendered profile: ${PROFILE_URL}"
html="$(curl -sSL --max-time 30 "$PROFILE_URL" || true)"

if [ -z "$html" ]; then
    echo "::warning::Could not fetch the profile page; skipping purge."
    exit 0
fi

# Camo asset URLs are a fixed-format hex digest path.
mapfile -t urls < <(
    printf '%s' "$html" \
        | grep -oE 'https://camo\.githubusercontent\.com/[a-zA-Z0-9]+' \
        | sort -u
)

if [ "${#urls[@]}" -eq 0 ]; then
    echo "::warning::No camo URLs found — the README may render no proxied images."
    exit 0
fi

echo "Found ${#urls[@]} proxied image(s); purging."

# Purge in parallel — done one at a time this takes minutes of runner time for
# no reason, since the requests are entirely independent.
purged="$(
    printf '%s\n' "${urls[@]}" \
        | xargs -P 8 -I {} sh -c 'curl -sS -X PURGE --max-time 20 "{}" >/dev/null 2>&1 && echo ok' \
        | grep -c ok || true
)"

echo "Purged ${purged}/${#urls[@]} cached image(s)."

# A partial purge is not worth failing the run over: whatever missed simply
# keeps its old TTL and refreshes on the next pass.
if [ "$purged" -lt "${#urls[@]}" ]; then
    echo "::warning::$(( ${#urls[@]} - purged )) image(s) did not purge; they will refresh on the next run."
fi
