#!/usr/bin/env bash
set -euo pipefail

env_path="${QUALITY_REPAIR_SDK_ENV:-$HOME/.config/mathpi/quality_repair_sdk.env}"
default_base_url="${QUALITY_REPAIR_DEFAULT_BASE_URL:-https://ai.onegodtoken.top}"

if [[ ! -t 0 ]]; then
  printf 'interactive terminal required for hidden token input\n' >&2
  exit 1
fi

restore_echo() {
  stty echo || true
}
trap restore_echo EXIT

printf 'ANTHROPIC_BASE_URL [%s]: ' "$default_base_url" >&2
read -r base_url
base_url="${base_url:-$default_base_url}"

printf 'SDK key/token (hidden): ' >&2
stty -echo
read -r token
stty echo
trap - EXIT
printf '\n' >&2

if [[ -z "$token" ]]; then
  printf 'empty token, abort\n' >&2
  exit 1
fi

install -d -m 700 "$(dirname "$env_path")"
tmp_path="${env_path}.tmp.$$"
umask 077
{
  printf 'ANTHROPIC_BASE_URL=%s\n' "$base_url"
  printf 'ANTHROPIC_API_KEY=%s\n' "$token"
} > "$tmp_path"
mv "$tmp_path" "$env_path"
chmod 600 "$env_path"

printf 'configured %s\n' "$env_path" >&2
stat -c 'mode=%a path=%n' "$env_path" >&2
