# Agent rules: cf-realip-sync

Small public tool: keeps nginx's Cloudflare real-IP conf current.  README.md
is the ops guide; keep it current with behavior changes.

## Environment

- Runs on the operator's nginx hosts behind Cloudflare.  Site knowledge
  lives in the operator's private ops repo; record site changes there.
- **Public repo:** never commit host names, IPs, secrets, or site details.

## Rules

- Standard library only; one script; Python 3.11+.
- Dry run by default; changes only with `--apply`.
- Never leave nginx with a failing config: test, restore on failure.
- Run tests (`python3 -m unittest tests/test_sync.py`) before committing.
