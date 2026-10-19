# Security notes (Phase 1)

What the code enforces, and where:

- **Tenant isolation, twice.** Every query filters by organization, and Postgres row-level
  security (`FORCE ROW LEVEL SECURITY` on all tenant tables) hides other tenants' rows even if a
  filter is forgotten. The app's database role is not a superuser (superusers bypass RLS); a test
  checks this. Objects in another organization return 404, never 403. (`app/db.py`,
  `migrations/versions/0001_initial_schema.py`, `tests/security/test_tenancy.py`)
- **SSRF.** Only http/https on ports 80/443. Every DNS answer must be a public address
  (loopback, private, link-local, CGNAT, multicast, cloud metadata, IPv4-mapped/6to4/Teredo/NAT64
  and shorthand IPv4 forms are refused). The socket connects to the address that was validated,
  so DNS rebinding between check and connect does not work, and every redirect hop is re-checked.
  (`app/crawl/netguard.py`, `tests/unit/test_netguard.py`, the redirect cases in
  `tests/integration/test_pipeline.py`)
- **robots.txt** per RFC 9309: honoured by default, 4xx means no rules, 5xx/unreachable means
  disallow all. Per-host rate limit shared across workers through Redis. No CAPTCHA solving,
  login, paywall or fingerprint evasion code exists.
- **Spreadsheet formula injection.** Cells beginning with `= + - @`, tab, CR or their full-width
  forms are written as text with a leading apostrophe; nothing is ever written as a formula.
  (`app/export/cell_safety.py`, `tests/unit/test_cell_safety.py`)
- **Untrusted page text** is only ever data: it is parsed with an HTML parser, never executed, and
  rendered by React as text. Phase 1 sends nothing to any AI model, so prompt injection on pages
  has nothing to act on; Phase 2 will treat page text the same way (data, not instructions).
- **Auth.** Argon2id password hashes; server-side sessions where only a SHA-256 of the cookie is
  stored; HttpOnly SameSite=Lax cookie; CSRF token required on every write; login rate limiting
  by email and IP; same error for unknown email and wrong password.
- **Downloads** need the session cookie *and* an HMAC-signed link bound to the user and export,
  valid for five minutes. Files live outside the web root and expire.
- **Logs** are JSON with passwords, tokens, cookies and API keys redacted; request paths are
  logged without query strings; page content is never logged.
- **Admin** routes return 404 to non-admins. Admins can lower limits, disable users and
  organizations, and block domains (opt-out list).

Known limits of the MVP: no email verification or password reset (local use); invitations add an
existing account by email; there is no per-request API rate limit beyond login and job quotas.
