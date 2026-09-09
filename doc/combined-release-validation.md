# OIDC and personal API keys: combined release validation

The local `integration/oidc-user-api-keys` branch combines PR #60
(`d8f5487`) and PR #46 (`dc60b8d`) from the shared `main`/`develop` baseline
`b09f065`. Original contributor commits are retained, with separate follow-up
fixes. Nothing in this procedure requires changing the contributor's branches.

## Expected behavior

- Providers may supply profile claims in the validated ID token or at UserInfo.
  Fetched claims are accepted only when their subject matches the ID token.
  A missing subject, subject mismatch, or failed required UserInfo fetch rejects
  login without creating an account or changing an existing account's role.
- Users with no personal keys/settings continue using global integrations.
- Personal Last.fm credentials override global credentials for personal
  recommendations and previews. Missing individual Last.fm fields fall back
  to their global values. YouTube keys also fall back when absent.
- Model, seed limit, and extra-header overrides work without a personal LLM key.
- An explicitly supplied personal LLM base URL uses only personal credentials
  and personal headers. With no personal key it uses the existing keyless-endpoint
  support; it never inherits global or environment credentials. Clear the
  personal base URL to return to the global endpoint and credential fallback.
- Both password and OIDC accounts can edit personal API settings. Password
  change fields remain exclusive to password accounts.

## Automated checks

Use Python 3.12, matching the release image:

```sh
python3.12 -m venv /tmp/sonobarr-release-test
/tmp/sonobarr-release-test/bin/pip install -r requirements.txt pytest pytest-cov
PYTHONPATH=src /tmp/sonobarr-release-test/bin/python -m pytest
```

The suite includes embedded/fetched OIDC login, invalid-subject rejection,
credential isolation using a real SDK client without network requests,
global fallback, personal settings, and SQLite migrations. Migration checks
cover existing users, partially present new columns, repeated upgrades, a
fresh app-created schema, and downgrade preservation of existing users.
Downgrading removes personal API settings; it is not a credential-preserving
rollback strategy.

## Live provider checks before release

Build the combined branch locally where Docker is available:

```sh
docker build -t sonobarr:combined-review .
```

Run that image with a separate test configuration/database and register its
`https://<test-host>/oidc/callback` URL with the provider. Do not attach the
production database to a test instance. Use the same combined revision for
Pocket ID and Authelia testing.

| Check | Pocket ID | Authelia |
| --- | --- | --- |
| New user signs in and receives the expected name | Pending | Pending |
| Logout and repeat login reuse the same account | Pending | Pending |
| Configured admin group grants/removes the role correctly | Pending | Pending |
| Profile shows API settings but no password-change fields | Pending | Pending |
| Blank personal settings use working global integrations | Pending | Pending |
| Personal Last.fm/YouTube/LLM settings override globals | Pending | Pending |
| Clearing personal settings restores global behavior | Pending | Pending |

For Authelia, verify a minimal ID token with profile claims supplied by UserInfo.
Pocket ID validates the provider flow it actually uses; if its token already
contains email or username, that login does not exercise the UserInfo fallback.
Record the provider version, combined Git commit, claim *names* and outcomes.
Do not include raw tokens, secrets, or personal claim values in test reports.

## Later merge and release

After local and provider validation, retarget PR #46 from `main` to `develop`.
Merge both original PRs into `develop` and land the corresponding tested fix
commits before promoting anything to `main`. Alternatively, this integration
branch contains both PR histories and fixes for a future maintainer-controlled
merge. Preserve the original commits when possible; squash/rebase merges will
need reconciliation with the local integration history.

Revalidate the resulting `develop` tree, then promote it to `main` and publish
one release. No PR creation, remote branch change, push, or release has been
performed as part of this local preparation.
