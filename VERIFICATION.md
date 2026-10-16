# Verification record

Date: **2 October 2026** (Asia/Calcutta).

## Image-search update

The subsequent Gemini diagnostics fix ran **70 tests: 68 passed and 2 MySQL-only
tests were skipped on SQLite**. Eleven added diagnostic tests cover safe HTTP
error classification, connection/TLS/timeout failures, placeholder keys, multipart
JSON, blocked/truncated responses, bounded transient retries, timeout bounds,
paginated model listing, and diagnostic output that does not expose keys.
Live Gemini still requires operator verification with `python manage.py check_ai`.

### Earlier image-search update

The updated suite ran **59 tests: 57 passed and 2 MySQL-only concurrency tests were
skipped on SQLite**. The separate MySQL test instance from initial generation was
no longer running. The original MySQL results below are retained as historical
verification; the new image-search workflow has not been rerun against MySQL.

Eleven added tests cover the upload/results/claim-link flow, authentication,
configuration notices, candidate visibility, absence of eligible reports,
invalid or duplicate AI item IDs, low-score filtering, availability rechecks,
provider failures, consent/file validation, and request throttling. Provider calls
are mocked; live image accuracy and API-account connectivity remain unverified
until a valid Gemini key is configured by the operator.

## Executed checks

* **48 Django tests passed on MySQL 8.0.45 / InnoDB**, Python 3.12, Django 5.2.17.
* Real concurrent MySQL transactions tested duplicate submissions and competing
  approvals: exactly one successful active claim/approved owner in each scenario.
* All initial migrations and the category data migration applied successfully.
* `makemigrations --check --dry-run`: no changes detected.
* `manage.py check`: no issues.
* `manage.py check --deploy` with production configuration: no issues.
* Python static checks for undefined names, unused imports, and syntax were fixed;
  Python source was formatted with Ruff.
* JavaScript syntax checked with Node.js.
* Public, user, and administrator templates rendered in the automated suite.
* Browser inspection exercised sign-in, the live dashboard, search filtering,
  mobile navigation, and theme switching. No JavaScript console errors were
  observed in the checked pages.
* Desktop layout inspected at 1440 px; mobile inspected at 390 px. A filter-grid
  overflow was found and corrected, then measured without horizontal page overflow.

## Boundaries

* Gemini network requests were mocked; **no live Gemini account/key was supplied**.
* SMTP failure handling and reset token workflows were tested; **no live SMTP
  credentials were supplied**, so actual email delivery is not verified.
* No public deployment, external penetration test, load test, or exhaustive browser
  compatibility test was performed.
* The local existing MySQL service was not modified. Checks used a separate
  loopback-only MySQL instance under the working directory.
* Demonstration data is optional and explicitly labeled; it is not baked into
  dashboard counters or included as an unlabelled production database dump.
