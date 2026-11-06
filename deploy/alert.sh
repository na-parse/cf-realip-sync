#!/usr/bin/env bash
# Mail root the log of a failed unit run.  Called by OnFailure= as:
#   alert.sh <unit>
set -uo pipefail

unit="${1:?usage: alert.sh <unit>}"
host="$(hostname -f 2>/dev/null || hostname)"
inv="$(systemctl show -p InvocationID --value "$unit")"

{
    echo "${unit} failed on ${host} at $(date -Is)."
    echo
    echo "Last run:"
    if [[ -n "$inv" ]]; then
        journalctl --no-pager -o short-iso _SYSTEMD_INVOCATION_ID="$inv"
    else
        journalctl --no-pager -o short-iso -u "$unit" -n 40
    fi
    echo
    echo "Re-run by hand (dry run):  /opt/cf-realip-sync/cf-realip-sync"
    echo "Docs: https://github.com/na-parse/cf-realip-sync#troubleshooting"
} | mail -s "[cf-realip-sync] FAILED on ${host}" root
