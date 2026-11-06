#!/usr/bin/env bash
# Install or update cf-realip-sync from origin/main.
#
#   Run as root:  /opt/cf-realip-sync/deploy/update.sh [--force]
#
# Pulls new commits, links the systemd units from the repo, enables the
# timer, then does a dry run so you can see the current state.  Exits
# without changes if already up to date (--force relinks anyway).
#
# Everything is inside main(), which runs on the last line, so bash has read
# the whole script before `git pull` can replace this file.
set -euo pipefail

INSTALL_DIR="/opt/cf-realip-sync"
UNITS=(cf-realip-sync.service cf-realip-sync.timer cf-realip-sync-alert.service)
TIMER="cf-realip-sync.timer"

die() { echo "ERROR: $*" >&2; exit 1; }

# Link $2 -> $1 unless it already points there.
link() {
    if [[ "$(readlink "$2" 2>/dev/null)" != "$1" ]]; then
        echo "=== Linking $2 -> $1"
        ln -sfn "$1" "$2"
    fi
}

main() {
    local force=false
    case "${1:-}" in
        --force) force=true ;;
        '') ;;
        *) die "usage: $0 [--force]" ;;
    esac

    [[ $EUID -eq 0 ]] || die "run as root"
    [[ -d "$INSTALL_DIR/.git" ]] || die "$INSTALL_DIR is not a git checkout"
    command -v nginx >/dev/null || die "nginx not installed"
    command -v python3 >/dev/null || die "python3 not installed"
    command -v mail >/dev/null \
        || echo "WARNING: no 'mail' command; failure alerts will not send"
    cd "$INSTALL_DIR"

    local local_commit remote_commit
    git fetch origin main --quiet
    local_commit=$(git rev-parse --short HEAD)
    remote_commit=$(git rev-parse --short origin/main)
    if [[ "$local_commit" == "$remote_commit" ]] && ! $force; then
        echo "No updates, already at ${local_commit} (--force to relink)"
        exit 0
    fi
    if [[ "$local_commit" != "$remote_commit" ]]; then
        echo "=== Update: ${local_commit} -> ${remote_commit}"
        git pull --ff-only --quiet origin main
        git log --oneline "${local_commit}..HEAD"
    fi

    local u
    for u in "${UNITS[@]}"; do
        link "${INSTALL_DIR}/systemd/${u}" "/etc/systemd/system/${u}"
    done
    systemctl daemon-reload
    systemctl enable --now --quiet "$TIMER"
    systemctl list-timers --no-pager "$TIMER" | head -2

    echo "=== Dry run"
    "${INSTALL_DIR}/cf-realip-sync" || die "dry run failed"
    echo "=== Done: now at $(git rev-parse --short HEAD)"
}

main "$@"
