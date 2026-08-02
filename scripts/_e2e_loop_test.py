# end-to-end loop test: bot dry-run -> ledger row -> reconcile -> cleanup
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import uuid_ledger as L

root = Path(__file__).resolve().parent.parent
bot = root / "scripts" / "kalshi_uuid_bot.py"
py = root / ".venv311" / "Scripts" / "python.exe"

r = subprocess.run([str(py), str(bot), "--dry-run", "--ticker", "E2E-LOOP-TEST",
                    "--side", "yes", "--price", "42", "--count", "1"],
                   capture_output=True, text=True)
print("--- bot stdout ---")
print(r.stdout)
if r.returncode != 0:
    print("--- bot stderr ---")
    print(r.stderr[:800])
    sys.exit(1)

con = L.local_conn(); cur = con.cursor()
cur.execute("SELECT uuid, client_order_id, ticker, side, price_cents, count, status, mode FROM uuid_orders WHERE ticker='E2E-LOOP-TEST' ORDER BY created_at DESC LIMIT 1")
row = cur.fetchone()
assert row, "no ledger row recorded!"
print("--- ledger row ---")
print(f"uuid={row[0]} coi={row[1]} {row[3]} {row[4]}c x{row[5]} status={row[6]} mode={row[7]}")
hit = L.reconcile(cur, row[1])
print("--- reconcile by coi ---")
print(hit)
assert hit and hit["uuid"] == row[0], "reconcile failed"
cur.execute("DELETE FROM uuid_orders WHERE ticker='E2E-LOOP-TEST'")
con.commit(); con.close()
print("E2E LOOP OK (test row cleaned up)")
