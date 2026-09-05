#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

readonly PUSHOVER_URL="https://api.pushover.net/1/messages.json"
readonly DEFAULT_CONFIG="/etc/nagios4/private/notifications.env"
readonly CURL_BIN="${CURL_BIN:-/usr/bin/curl}"
readonly DATE_BIN="${DATE_BIN:-/usr/bin/date}"

user_key="" app_token="" title="" message="" sound=""
warning_sound="" critical_sound="" ok_sound="" event_epoch=""
priority="0" retry="60" expire="3600"
config_file="${NAGIOS_NOTIFICATION_CONFIG:-$DEFAULT_CONFIG}"

usage() {
    cat <<'EOF'
Usage: notify_by_pushover.sh -t TITLE -m MESSAGE [options]
       notify_by_pushover.sh --nagios-host|--nagios-service

Options:
  -f FILE  Secret configuration file
  -u KEY   Override PUSHOVER_USER_KEY
  -a TOKEN Override PUSHOVER_APP_TOKEN
  -e EPOCH Append the event time
  -p N     Priority, -2 through 2 (default: 0)
  -s NAME  Default sound
  -w NAME  WARNING sound
  -c NAME  CRITICAL sound
  -o NAME  OK sound
  -r N     Emergency retry interval, at least 30 seconds (default: 60)
  -x N     Emergency expiry, at most 10800 seconds (default: 3600)
EOF
}

die() { printf 'UNKNOWN: %s\n' "$*" >&2; exit 3; }

config_value() {
    local wanted="$1" key value
    [ -r "$config_file" ] || return 1
    while IFS='=' read -r key value; do
        key="${key#${key%%[![:space:]]*}}"; key="${key%${key##*[![:space:]]}}"
        [[ -z "$key" || "$key" == \#* ]] && continue
        if [ "$key" = "$wanted" ]; then
            value="${value#${value%%[![:space:]]*}}"; value="${value%${value##*[![:space:]]}}"
            if [[ "$value" == \"*\" || "$value" == \'*\' ]]; then value="${value:1:${#value}-2}"; fi
            printf '%s' "$value"; return 0
        fi
    done < "$config_file"
    return 1
}

spoken_english_time() {
    local epoch="$1"
    [[ "$epoch" =~ ^[0-9]+$ ]] || die "event time must be a Unix epoch"
    "$DATE_BIN" --date="@${epoch}" '+%A %-d %B at %H:%M:%S'
}

if [ "${1:-}" = "--nagios-host" ] || [ "${1:-}" = "--nagios-service" ]; then
    [ "$#" -eq 1 ] || die "Nagios mode does not accept additional arguments"
    critical_sound="siren"; warning_sound="gamelan"; event_epoch="${NAGIOS_TIMET:-}"
    if [ "$1" = "--nagios-host" ]; then
        [ -n "${NAGIOS_HOSTNAME:-}" ] || die "NAGIOS_HOSTNAME is required"
        [ -n "${NAGIOS_HOSTSTATE:-}" ] || die "NAGIOS_HOSTSTATE is required"
        title="Host"
        message="${NAGIOS_HOSTNAME} - ${NAGIOS_HOSTSTATE} - Info: '${NAGIOS_HOSTOUTPUT:-}'"
    else
        [ -n "${NAGIOS_HOSTNAME:-}" ] || die "NAGIOS_HOSTNAME is required"
        [ -n "${NAGIOS_SERVICESTATE:-}" ] || die "NAGIOS_SERVICESTATE is required"
        [ -n "${NAGIOS_SERVICEDESC:-}" ] || die "NAGIOS_SERVICEDESC is required"
        title="Service"
        message="${NAGIOS_HOSTNAME} - ${NAGIOS_SERVICESTATE} - ${NAGIOS_SERVICEDESC} - '${NAGIOS_SERVICEOUTPUT:-}'"
    fi
else
    while getopts ":f:u:a:t:m:p:s:w:c:o:e:r:x:h" option; do
        case "$option" in
            f) config_file="$OPTARG" ;; u) user_key="$OPTARG" ;; a) app_token="$OPTARG" ;;
            t) title="$OPTARG" ;; m) message="$OPTARG" ;; p) priority="$OPTARG" ;;
            s) sound="$OPTARG" ;; w) warning_sound="$OPTARG" ;; c) critical_sound="$OPTARG" ;;
            o) ok_sound="$OPTARG" ;; e) event_epoch="$OPTARG" ;; r) retry="$OPTARG" ;;
            x) expire="$OPTARG" ;; h) usage; exit 0 ;; :) die "option -${OPTARG} requires a value" ;;
            \?) die "unknown option: -${OPTARG}" ;;
        esac
    done
fi

[ -n "$user_key" ] || user_key="$(config_value PUSHOVER_USER_KEY || true)"
[ -n "$app_token" ] || app_token="$(config_value PUSHOVER_APP_TOKEN || true)"
[ -n "$user_key" ] || die "Pushover user key is missing from ${config_file}"
[ -n "$app_token" ] || die "Pushover application token is missing from ${config_file}"
[ -n "$title" ] || die "notification title is required"
[ -n "$message" ] || die "notification message is required"
[ "${#title}" -le 250 ] || die "title exceeds 250 characters"
[[ "$priority" =~ ^-?[0-2]$ ]] || die "priority must be between -2 and 2"

case "${title} ${message}" in
    *CRITICAL*) [ -z "$critical_sound" ] || sound="$critical_sound" ;;
    *WARNING*) [ -z "$warning_sound" ] || sound="$warning_sound" ;;
    *OK*|*RECOVERY*) [ -z "$ok_sound" ] || sound="$ok_sound" ;;
esac
[ -z "$event_epoch" ] || message="${message}. $(spoken_english_time "$event_epoch")"
[ "${#message}" -le 1024 ] || die "message exceeds 1024 characters"

args=(--fail --silent --show-error --output /dev/null --max-time 5
    --form-string "token=${app_token}" --form-string "user=${user_key}"
    --form-string "title=${title}" --form-string "message=${message}"
    --form-string "priority=${priority}")
[ -z "$sound" ] || args+=(--form-string "sound=${sound}")
if [ "$priority" = "2" ]; then
    [[ "$retry" =~ ^[0-9]+$ ]] && [ "$retry" -ge 30 ] || die "retry must be at least 30 seconds"
    [[ "$expire" =~ ^[0-9]+$ ]] && [ "$expire" -ge 1 ] && [ "$expire" -le 10800 ] || die "expire must be between 1 and 10800 seconds"
    args+=(--form-string "retry=${retry}" --form-string "expire=${expire}")
fi
[ -x "$CURL_BIN" ] || die "curl is not executable: ${CURL_BIN}"
"$CURL_BIN" "${args[@]}" "$PUSHOVER_URL"
