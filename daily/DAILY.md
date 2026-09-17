# Daily repository practice

One useful, shippable project per day. Prefer something that advances Get247, No BS AI, GPS Kids, or the FDE portfolio.

## Constraints (as of 2026-09-17)

- This Cloud Agent can **write only** to `369Apps/369Apps`.
- It **cannot** create new GitHub repositories under the `369Apps` org.
- Until that changes, land each daily build under `daily/YYYY-MM-DD-<slug>/` as an extractable project (own README, tests, Dockerfile) and include `EXTRACT.md`.

## Checklist for the agent

1. Scan existing `369Apps` repos and recent product docs so you do not duplicate a landing page or blueprint.
2. Pick one gap with clear buyer or portfolio value.
3. Build a complete mini-repo under `daily/YYYY-MM-DD-<slug>/`.
4. Update the root profile `README.md` "Currently" / pinned-work section.
5. Open a PR on `369Apps/369Apps`.
6. Tell Bobby the exact `gh repo create` + push commands from `EXTRACT.md`.

## Log

| Date | Slug | Intent |
|---|---|---|
| 2026-09-17 | `get247-ops` | Control plane from Get247 system blueprint v1.1: catalog, policy, approvals, audit |
