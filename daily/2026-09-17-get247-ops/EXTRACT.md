# Extract this daily build into `369Apps/get247-ops`

The Cloud Agent GitHub App is currently scoped to **only** `369Apps/369Apps`, so it cannot create a new org repository. To publish today's build as a standalone repo:

## 1. Create the empty repo (human, once)

```bash
gh repo create 369Apps/get247-ops \
  --public \
  --description "Get247 ops control plane: bounded catalog, policy gates, approvals, audit" \
  --disable-wiki \
  --disable-issues=false
```

Or create it in the GitHub UI under the `369Apps` org.

## 2. Push this folder as the repo root

From a machine with write access to the new repo:

```bash
cd daily/2026-09-17-get247-ops
git init
git add .
git commit -m "Initial get247-ops control plane (daily build 2026-09-17)"
git branch -M main
git remote add origin git@github.com:369Apps/get247-ops.git
git push -u origin main
```

## 3. Grant the Cloud Agent access (optional, for future agents)

In Cursor Cloud Agent environment settings for this work:

1. Add `github.com/369Apps/get247-ops` to the environment's repository list / `repositoryDependencies`.
2. Or broaden the GitHub App installation to include new repos under `369Apps`.

## 4. Update the profile README

After the standalone repo exists, point the pinned-work entry at `https://github.com/369Apps/get247-ops` instead of the `daily/` path.
