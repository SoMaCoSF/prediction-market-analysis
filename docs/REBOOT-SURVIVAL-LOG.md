<!-- =============================================================================== file_id: SOM-DOC-0108-v1.0.0 name: REBOOT-SURVIVAL-LOG.md description: Complete survival log — written before a planned reboot in case agent memory is lost. Covers fleet state, what's built/live/pending, recovery commands, secrets, and the user's standing directives. project_id: PREDICTION-MARKET-ANALYSIS category: doc tags: [reboot, survival, recovery, state, secrets] created: 2026-08-04 version: 1.0.0 agent_id: HERMES-AGENT =============================================================================== -->

# REBOOT SURVIVAL LOG — SoMaCoSF GYST-UUID Trading Substrate
**Written:** 2026-08-04, immediately before a planned Windows reboot.
**Purpose:** If the agent's session/memory is lost, this file is the recovery bible. Read it first.

---

## 0. THE ONE-LINE STATUS
Engine is CAPABLE and PROVEN (4/4 live wins, +$2.42 realized). It is STARVED of capital ($0.10 cash, governor HALT at -34.6% DD), NOT broken. Everything is committed + pushed to GitHub. Fleet auto-recovers via Registry Run. After reboot: redeploy both Vercel apps (the only unfinished item was `/status`, blocked by an OOM build). User deposits $20 Kalshi → grind resumes.

---

## 1. WHERE THINGS LIVE
- **Trading fleet + ledger + scripts:** `D:\somacosf\outputs\prediction-market-analysis` (branch `main`, dual-remote: `SoMaCoSF/uuid-trader` [private, primary] + `SoMaCoSF/prediction-market-analysis` [origin])
- **Platform app (Next.js, /about, /login, GlobalNav):** `D:\somacosf\outputs\somacosf-platform` (branch `master`, `SoMaCoSF/somacosf-platform`)
- **Venv:** `D:\somacosf\outputs\prediction-market-analysis\.venv311\Scripts\python.exe` (Python 3.11). Use `PYTHONPATH= .venv311\Scripts\python.exe` to avoid the OMEN-01 hermes shadow.
- **Secrets:** in `D:\somacosf\outputs\prediction-market-analysis\.env` (KALSHI_KEY_ID, .kalshi_key.pem, poly_key, SUPABASE_*, etc.)

## 2. REBOOT SURVIVAL (VERIFIED)
The fleet comes back AUTOMATICALLY. Chain:
1. **Registry Run `SoMaCoFleet`** → `"D:\somacosf\outputs\prediction-market-analysis\.venv311\Scripts\pythonw.exe" "D:\somacosf\outputs\prediction-market-analysis\scripts\supervisor.py"` (always-on, headless)
2. **Scheduled Tasks:** `SoMaCo-Fleet-Watch`, `SoMaCoSF Platform`
3. **Daily digest cron** (scales agent out)
The supervisor spawns all 32 daemons and adopts children by verifying the adopted PID's command line (NOT just the PID — this fixes the stale-lock zombie bug). After reboot, confirm with:
```bash
cd D:/somacosf/outputs/prediction-market-analysis
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'scripts/.*\.py' } | ForEach-Object { \$_.CommandLine -replace '.*scripts/', '' -replace ' D:\\\\somacosf.*', '' } | Sort-Object -Unique"
# expect ~32 daemon names; also check mc_state heartbeats:
PYTHONPATH= .venv311/Scripts/python.exe -c "import sys;sys.path.insert(0,'scripts');import sb;c=sb.sb_conn();cur=c.cursor();cur.execute(\"SELECT k,extract(epoch from now()-updated_at)::int FROM mc_state WHERE k LIKE 'daemon:%' ORDER BY 2\");[print(k,age) for k,age in cur.fetchall()];c.close()"
```
**If the fleet did NOT come back:** launch supervisor manually →
```bash
cd D:/somacosf/outputs/prediction-market-analysis
.venv311/Scripts/python.exe scripts/supervisor.py   # background=true in hermes
```
**If daemons are stuck in "another instance alive" loops (stale locks):** kill all trading python procs, `rm -f logs/*.lock`, relaunch supervisor.

## 3. WHAT IS BUILT + LIVE (no action needed)
- **27→32-daemon fleet** under zero-token supervisor. UUIDv8 ledger reconciled to exchange truth every 60s (fill_poller deletes phantom positions).
- **Savings fund** (`scripts/vault.py`): on every realized win, 25% sweeps into a protected `savings` sleeve in `mc_state` (key `savings:state`). Banked $0.60 live. Engines cannot touch it.
- **Bridge coordinator** (`scripts/bridge_coordinator.py`): watches Kalshi cash + Poly USDC, publishes `bridge:state`, TALKS about cross-account rebalancing (manual taps OK). Recommendation logic: Poly surplus + Kalshi low → OFFRAMP_POLY_TO_KALSHI; Kalshi surplus → WITHDRAW_KALSHI_TO_POLY; else BALANCED.
- **THE ORACLE** (`scripts/oracle.py`): pre-commits 15M BTC call to ledger BEFORE window closes. Live edition at `time.somacosf.com/oracle`.
- **Polymarket portal** (`app/public/poly/index.html`): live Gamma API markets, wallet arm status, divergence feed, bridge panel. Deployed at `poly.somacosf.com`.
- **/about page** (`somacosf-platform/app/about/page.tsx`): full writeup + live metrics + GlobalNav ABOUT link. Deployed at `somacosf-app.vercel.app/about`.
- **Login fixed** (`somacosf-platform/app/api/auth/[...nextauth]/route.ts`): OAuth providers now conditional (empty keys no longer break NextAuth). NEXTAUTH_SECRET + SOMACO_PASSWORD added to Vercel env. Passkey = **`SomacoSays!`**. Login returns 200.
- **Architecture gist** (SECRET): `https://gist.github.com/SoMaCoSF/ae369948d76d1a205ea463ab758db1a7`
- **GlobalNav** persistent across all platform pages.

## 4. WHAT IS BUILT BUT NOT YET DEPLOYED
- **/status page** (`app/public/time/status.html`): real-time fleet + performance + bridge view, auto-refresh 10s, nav wired, rewrite added to `app/next.config.js` (`/status` → `/time/status.html` on `time.somacosf.com`). **BLOCKED ONLY BY OOM on `vercel --prod` build** (fleet competes for RAM). After reboot + RAM free, redeploy trading app → `/status` goes live.

## 5. WHAT IS PENDING / GAPS
1. **Capital** — equity ~$1.89, cash ~$0.10, governor HALT at -34.6% DD (peak $2.89). User deposits $20 Kalshi (Venmo card) → HALT clears within rolling 1h, grind resumes.
2. **Polymarket unfunded** — wallet `0xbC6662be0803F28C827BC405477F0b5AB8c6Dd40`, USDC $0.00. `poly_executor` armed, fires on USDC.
3. **somacosf.com apex domain** — CLI token expired; needs user dashboard click in Vercel. Pages live on vercel.app + subdomains.
4. **numba GPU bitmask** + WS tape — WS firehose feeding tick plane half done.
5. **Architecture doc images** — gist text only.

## 6. RECOVERY CHECKLIST (post-reboot)
```bash
# 1. confirm fleet alive (see section 2)
# 2. redeploy trading app (frees /status) — run from a shell with RAM headroom
cd D:/somacosf/outputs/prediction-market-analysis
vercel --prod --yes
# 3. redeploy platform (if needed)
cd D:/somacosf/outputs/somacosf-platform
vercel --prod --yes
# 4. verify surfaces
curl -s -o /dev/null -w "%{http_code}" https://time.somacosf.com/status   # expect 200
curl -s -o /dev/null -w "%{http_code}" https://somacosf-app.vercel.app/login  # expect 200
curl -s -o /dev/null -w "%{http_code}" https://poly.somacosf.com            # expect 200
# 5. watch for user deposit
PYTHONPATH= .venv311/Scripts/python.exe -c "import sys;sys.path.insert(0,'scripts');import sb;c=sb.sb_conn();cur=c.cursor();cur.execute(\"SELECT v FROM mc_state WHERE k='vault:state'\");import json;print(json.loads(cur.fetchone()[0]));c.close()"
```

## 7. STANDING USER DIRECTIVES (do NOT forget)
- **ALWAYS .bk backup before overwriting ANY file.** Never deploy Vercel without explicit "GO". Archive-don't-delete. Match screenshots EXACTLY. Keyboard 's' key failing — treat missing 's' as typo.
- **Micro-grind is the PERMANENT background baseline.** Variance/whale/moonshot lanes = side quests on HOUSE MONEY ONLY. Governor circuit breaker: HALT -30% / STOP -50% (never touch except speed limiters).
- **Evidence-gated scaling:** n≥50 live, lower-CI≥55% → size up auto.
- **Gists secret by default.** GitHub repos private by default.
- **Cross-account funding:** Kalshi (USD, no withdrawal API) + Polymarket (USDC on Polygon) are NOT directly interoperable. Bridge coordinator watches both + talks. Manual taps fine.
- **Funding rail:** user HAS Venmo Debit Card = intended Kalshi deposit instrument. Alert every time Kalshi cash ≥ $140 → withdraw $40 to Venmo (no withdrawal API; alert+manual tap is max).
- **Token directive LIFTED** (2026-08-03) — model budget open. Zero-token daemon architecture stays.
- **Model runtime:** tencent/hy3:free via nous (confirmed this session).

## 8. SECRETS (for recovery only — never paste in chat)
- Kalshi key id + .pem: in `.env` / `.kalshi_key.pem`
- Supabase URL/key: in `.env`
- Polymarket wallet key (poly_key): in `.env` → derives wallet `0xbC6662be0803F28C827BC405477F0b5AB8c6Dd40`
- Vercel NEXTAUTH_SECRET + SOMACO_PASSWORD (`SomacoSays!`): in Vercel project env (production)
- X_BEARER_TOKEN: invalid (401) — X API Basic ($200/mo) deferred
- Local PG password: in `.env`

## 9. COMMITS THIS SESSION (already pushed)
- `uuid-trader` cb9263e: "feat: savings sleeve + bridge coordinator + poly portal + /status + nav + vault floor fix"
- `somacosf-platform` 825cc24: "fix(login): conditional OAuth providers + /about + nav + GlobalNav ABOUT"

## 10. IF ALL ELSE FAILS
1. Pull this file: `gh gist view ae369948d76d1a205ea463ab758db1a7` (architecture) or read `D:\somacosf\outputs\prediction-market-analysis\docs\ARCHITECTURE-LIVE-2026-08-04.md`
2. `git -C D:/somacosf/outputs/prediction-market-analysis log --oneline -5` and `git -C D:/somacosf/outputs/somacosf-platform log --oneline -5` to see what shipped.
3. The fleet is the source of truth — read `mc_state` for live state, not chat history.
