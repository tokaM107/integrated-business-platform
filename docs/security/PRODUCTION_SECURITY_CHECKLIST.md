# Production security checklist

For whoever deploys and operates the ERP. It lists what must be true on the production server, in the order to
do it. It comes from the security audit of 10 Nov 2026 ([FULL_SECURITY_AUDIT.md](FULL_SECURITY_AUDIT.md));
finding numbers are in brackets.

It does not repeat the deployment procedure. That is in
[production-deployment-coolify.md](../deployment/production-deployment-coolify.md) and
[production-hardening.md](../deployment/production-hardening.md).

Nothing here was applied to production by the audit. Every step needs the owner's approval and someone with
access to the server.

## 1. Before deploying the security branch

- [ ] The branch `security/full-audit-2026-11-10` is reviewed and merged by a person, not auto-deployed from an
      unreviewed push [I5].
- [ ] A backup is taken, copied off the server and restore-tested (`deploy/verify_backup.sh`).
- [ ] Staff are told: after this release a browser left idle is signed out (section 4).
- [ ] After the deploy, the full suite passes on the deployed image:
      `scripts/run_tests.sh --app imed_erp` on a throwaway copy, never on the production site.
- [ ] No database migration is needed by this branch (no DocType or field changed). `bench migrate` is still run
      as for any release.

## 2. Credentials: rotate and reset

An old initial password for the September user accounts is in the public git history [I1]. Removing it from the
code does not help: treat it as known to everyone.

- [ ] Force a new password for every user that existed before the cut-over (owner, accountant, branch managers,
      every `@imed.local` login): in each User, set a new random password or tick "Send password update
      notification" and untick nothing else. Then check nobody can still sign in with the old one.
- [ ] Administrator has a long random password that is only in the owner's password manager.
- [ ] The 12 test users are disabled on production.
- [ ] Two-factor authentication is on for the owner and the accountant (System Settings > Two Factor
      Authentication, role based).
- [ ] The XStudio seed admin password that appears in `scripts/xstudio_staging.sh` is not in use on production
      XStudio [I15].
- [ ] The Supabase staging password and the three model-provider keys in the developer's local `.env` are
      rotated if that machine or file was ever shared. They were never committed.
- [ ] Library connector: each PC gets its own API user and key (today both share one) [X2]. The key file on the
      PC is readable by the task's Windows user only.

If any credential is found to have been used by someone else, follow section 9.

## 3. Server and network

- [ ] Coolify's dashboard (port 8000) and its realtime ports (6001, 6002) are not reachable from the internet.
      Reach Coolify through an SSH tunnel, or put it behind HTTPS with two-factor [I2]. This reverses the owner's
      decision of 29 Oct 2026, so the owner decides.
      `PORTS=8000,8080,6001,6002 bash deploy/vps_harden.sh apply`, then confirm from a new SSH session.
      The multi-port form of this script was fixed in this audit but not run on Linux: test it with the
      automatic revert left on [I3].
- [ ] SSH accepts keys only (`PasswordAuthentication no`), fail2ban and unattended upgrades are installed.
- [ ] MariaDB and Redis publish no port and are not on Coolify's shared "predefined" network [I12].
- [ ] The database root password and the backup credentials are not in the web containers' environment [I4].
- [ ] Images are pinned by digest, and the base image is updated to a release that fixes the known package
      advisories after a compatibility test [I6, I7].

## 4. Sessions

The server ends a browser session by itself (`imederp/session_policy.py`):

| | Inactivity | Total age |
|---|---|---|
| Everyone | 30 minutes | 12 hours |
| System Manager, Super Admin, Accounts Manager, Administrator | 15 minutes | 8 hours |

- [ ] The values suit the work. A cashier idle for 30 minutes signs in again. To change one without a release,
      set it in the site's configuration and restart the web workers:
      `bench --site <site> set-config imed_session_idle_minutes 60`
      (also `imed_session_privileged_idle_minutes`, `imed_session_absolute_hours`,
      `imed_session_privileged_absolute_hours`; 0 switches one off).
- [ ] System Settings > Session Expiry is lowered from 170 hours to `12:00`, so the cookie's own lifetime matches.
- [ ] Sessions open at the moment of the deploy and older than the limits end at their next request. This is
      expected.
- [ ] The site is served over HTTPS only, so the session cookie carries the Secure flag. Check in the browser:
      the `sid` cookie shows HttpOnly, Secure and SameSite=Lax.

## 5. Site configuration

Read with `bench --site <site> show-config` (it prints secrets: do not paste the output anywhere).

- [ ] `developer_mode` is 0, `allow_tests` is 0, `server_script_enabled` is absent or 0.
- [ ] `ignore_csrf` is absent.
- [ ] `host_name` is the https address.
- [ ] `encryption_key` is present and is the one from the backup (passwords of the XStudio settings depend on it).
- [ ] System Settings: login attempts limited (10, then 60 seconds, as on the development site or stricter),
      password policy on with score 3 or more, "Logout all sessions on password reset" on.

## 6. Permissions and business decisions waiting for the owner

- [ ] Withdrawing an approved recovery and writing off a shortage that waits for the owner: who may do each
      [K1, K2].
- [ ] May a branch manager who is not BA Plus's record an app subscription [D6]?
- [ ] The standard ERPNext rights that Accounts User, Sales User and Stock User still hold outside the permission
      matrix (payment reconciliation, bank accounts, POS settings) are checked on the site and narrowed [D12].

## 7. Backups

- [ ] One backup job is the real one, and it ran last night. The Coolify scheduled task did not exist in the
      image before this audit (the script was not copied in); it does after this branch is deployed [I-backup].
- [ ] Backups are encrypted before they leave the server (restic). The old script that copied plain files to
      Google Drive (`scripts/backup_offsite.sh`) is not used [I8].
- [ ] No plain backup set is left in `/root/imed-restore`, `/var/backups/imed`, `/tmp` or `sites/*/private/backups`.
- [ ] The backup repository cannot be deleted with the credentials the server holds (append-only or object lock).
- [ ] A restore is rehearsed every month and its date written down.

## 8. Monitoring

- [ ] Someone receives an alert when the nightly backup fails, when the site is down, and when the disk is over
      80%.
- [ ] Activity Log is reviewed weekly for failed logins and for "Session Expired" spikes.
- [ ] Error Log is reviewed weekly. Entries titled "Assistant provider … failed" and failed sync runs
      (Integration Status report) are followed up.
- [ ] Docker logs are rotated on the host (`max-size`), and nobody but the operator reads them.

## 9. If a credential or an account is compromised

1. Disable the account (never delete it) and end its sessions: User > Settings > "Logout from all devices", or
   `bench --site <site> execute frappe.sessions.clear_sessions --kwargs '{"user": "<user>", "force": true}'`.
2. Rotate the credential at its source (the provider's console for a model key, XStudio for its login, the User
   record for an API key) and update it on the server.
3. Read what the account did: Activity Log, Version (document changes), Access Log, and for money the GL Entry
   rows it created or cancelled since the suspected date.
4. Check cash documents first: Cash Handover, Treasury Close, Cash Discrepancy, App Payment, Journal Entry.
5. Write down what happened, when, and what was changed, and tell the owner the same day.
