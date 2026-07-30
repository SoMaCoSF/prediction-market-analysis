# SoMaCo · Prediction-Market UUID Engine — Status Site

Vercel-deployable status dashboard for the GYST UUIDv8 prediction-market engine.

## What it shows
- `uuid_trades` row count (trades minted as 0x3A2, stored in local Postgres)
- Wirespeed bitmask proof: `((uuid_hi >> 52) & 4095) = 0x3A2` matched ratio
- Build-time snapshot in `public/status.json` + live `/api/status` when a cloud PG is wired

## Access gate
Passkey = SHA-256( OMEN-01 primary MAC | "omen-01" | STATUS_SALT ).
MAC is used as a simple obfuscation gate (not cryptographic auth) — adequate for a
status page limited to this box / Tailscale. Set `STATUS_SALT` in Vercel env to harden.

## Deploy
```
cd app
vercel env add STATUS_SALT        # set a salt
vercel deploy --prod             # requires explicit GO from user
```
The build runs `scripts/collect_status.js` against local Postgres (or
`PG_CONNECTION_STRING` for a hosted DB) and bakes a real snapshot.

## Local engine (no-admin)
`scripts/start_pg.bat` brings up local Postgres + the localhost:4242 viewer.
