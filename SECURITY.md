# Security

Onion MC Launcher is a free, community-oriented desktop project. Security fixes
are published as source changes; this document is not a guarantee that all
vulnerabilities have been found.

- On Windows, saved account tokens and the optional CurseForge API key are
  encrypted with user-bound Windows DPAPI. Existing plaintext records migrate
  on load. Keep the original Windows user profile: another user, machine, or an
  older launcher build may require signing in again. This does not protect
  credentials in a running process from malware running as the same user.
- Authentication requires HTTPS. Redirects reject HTTPS downgrades and remove
  credentials when crossing origins. The general game downloader still permits
  HTTP for compatible repositories; only use repositories you trust.
- Downloads enforce size limits and check supplied SHA-1/SHA-256 digests.
  Resumed responses must match the requested byte range and declared length.
  Resource indexes are bounded and checked against published metadata when available;
  malformed cached indexes are repaired rather than silently accepted.
  ZIP extraction streams files with bounds on file count, expansion size and
  compression ratio, rejects unsafe paths and links, and supports cancellation
  in pack imports and world restoration. NBT parsing has size and depth limits.
- Launcher logs, game output and diagnostic exports redact credential-like fields.
  Long log lines and report reads are bounded. This is best-effort redaction, not
  a reason to publish unreviewed logs containing personal information.
- Deferred runtime compression restores byte-identical libraries in PyInstaller's
  private temporary directory and verifies every restored file's SHA-256 before
  loading it. It does not patch DLLs or remove their original security metadata.
- HTTPS certificate and hostname checks remain required. Only the TLS trust
  configuration is cached (up to five minutes); account credentials, connections
  and proxy routes are not cached by that mechanism.
- The optional authlib-injector is pinned to version 1.2.8 and its SHA-256,
  obtained from the [upstream release](https://github.com/yushijinhun/authlib-injector/releases/tag/v1.2.8).
- Source publication excludes accounts, local settings, logs, game data and
  private application configuration. Do not attach these files to public issues.

If you find a vulnerability, contact the maintainer through the GitHub profile
before publishing reproduction material containing credentials or personal data.
For ordinary bug reports, provide a minimal, redacted reproduction.
