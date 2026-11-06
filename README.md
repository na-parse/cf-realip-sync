# cf-realip-sync

Keeps nginx's Cloudflare real-IP config current.  nginx behind Cloudflare sees
every connection from a Cloudflare address; `real_ip_header CF-Connecting-IP`
plus one `set_real_ip_from` per Cloudflare range makes nginx log (and use) the
visitor's address, and only trusts the header from Cloudflare.  This tool
rebuilds that file from Cloudflare's published lists, safely, on a timer, and
mails root when it fails.

Single Python 3 file, standard library only.  Runs as root on the nginx host.

## What a run does

1. Fetch `ips-v4` and `ips-v6` (3 tries each, backoff).  Must be `text/plain`.
2. Validate: every line a CIDR of the right family, no duplicates, at least
   `min_ipv4` / `min_ipv6` ranges, and no more than `max_removed_fraction` of
   the current ranges removed.  Any failure: exit 1, nothing touched.
3. Render the conf (deterministic, no timestamps) and compare with the
   current file.  Same: exit 0, no reload.
4. Dry run (default): print the diff, exit 0.
5. `--apply`: keep the current file as `<output>.prev`, write the new one
   atomically, run `nginx -t`.  If the test fails, restore the previous
   file and exit 1.  Otherwise reload nginx and, if ranges changed, mail a
   summary.

Exit codes: 0 no change or applied, 1 failed (previous config kept),
2 config error.

## Install

Requires `nginx`, `python3`, and a working `mail` command (local MTA that
can deliver root's mail) for alerts.

```sh
git clone https://github.com/na-parse/cf-realip-sync.git /opt/cf-realip-sync
/opt/cf-realip-sync/deploy/update.sh --force
```

`update.sh` links the three units from `systemd/` into
`/etc/systemd/system/`, enables the timer, and does a dry run.  The first
`--apply` usually rewrites the file once (header comments), with no range
change.

Make sure nothing else manages the output file (e.g. an older update script
or cron job).

## Update

```sh
/opt/cf-realip-sync/deploy/update.sh            # pull origin/main if newer
/opt/cf-realip-sync/deploy/update.sh --force    # relink units anyway
```

## Configure

`config.ini` beside the script (tracked; no secrets).  Every key has a
default; see the file for the full list.  Common changes:

| Key | Default | Use |
|---|---|---|
| `[nginx] output` | `/etc/nginx/conf.d/cloudflare-realip.conf` | Where the conf goes (must be included by nginx) |
| `[sanity] max_removed_fraction` | `0.5` | Raise for one run if Cloudflare really drops many ranges |
| `[notify] on_change` | `yes` | Mail when ranges change |
| `[notify] mail_to` | `root` | Recipient |

Change it in the repo, push, then run `deploy/update.sh` on the host.
`--config PATH` runs with another file (testing).

## Operate

| Task | Command |
|---|---|
| Dry run (what would change) | `/opt/cf-realip-sync/cf-realip-sync` |
| Apply now | `systemctl start cf-realip-sync.service` |
| Next / last run | `systemctl list-timers cf-realip-sync.timer` |
| Last run's log | `journalctl -u cf-realip-sync.service -n 30` |
| Test the failure alert | `systemctl start cf-realip-sync-alert.service` |

Schedule: Mondays 05:00 plus up to 1 h random delay; `Persistent=true` runs
a missed slot at boot.

## Alerts

- **Failure:** the service's `OnFailure=` starts `cf-realip-sync-alert.service`,
  which mails root that run's journal (`deploy/alert.sh`).
- **Change:** the tool mails a list of added and removed ranges.
- Silence (timer never runs, host down, mail broken) is **not** alerted.
  Pair with an external heartbeat if that matters.

## Troubleshooting

| Error | Meaning | Action |
|---|---|---|
| `fetch ... failed` | Cloudflare unreachable or URL changed | Check outbound HTTPS; wait for the next run or start it by hand |
| `not a CIDR` / `unexpected content type` | Cloudflare served something other than the list | Nothing was changed; check the URL in a browser |
| `only N IPv4 ranges` | List suspiciously short | Nothing changed; check the list |
| `... would be removed; refusing` | Large removal | Verify against Cloudflare's IP page; if real, raise `max_removed_fraction`, run, set it back |
| `nginx test failed ... restored` | New file broke nginx (or nginx was already broken) | `nginx -t`; previous file is live, new one discarded |
| `reload failed` | File valid, reload didn't work | `systemctl status nginx` |

## Uninstall

```sh
systemctl disable --now cf-realip-sync.timer
rm /etc/systemd/system/cf-realip-sync{.service,.timer,-alert.service}
systemctl daemon-reload
rm -rf /opt/cf-realip-sync
```
The last generated conf stays in place and keeps working.

## Tests

```sh
python3 -m unittest -v tests/test_sync.py     # Linux (uses true/false)
```
