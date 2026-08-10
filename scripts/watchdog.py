import time, json, os, sys, subprocess, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
import sb

LOG = os.path.join(os.path.dirname(__file__), 'data', 'watchdog.log')
os.makedirs(os.path.dirname(LOG), exist_ok=True)
FLOOR = 25.0
DAEMONS = [
    ("micro_trader", "scripts/micro_trader.py"),
    ("profit_scalp", "scripts/profit_scalp.py"),
]

def log(msg):
    ts = datetime.datetime.utcnow().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    with open(LOG, 'a') as f:
        f.write(line + '\n')

def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, ValueError, TypeError):
        return False

def check_pids():
    # Check known PIDs from process list
    known = [8644]  # micro_trader from earlier
    for pid in known:
        if not pid_alive(pid):
            log(f"ALERT: PID {pid} dead")
            return False
    return True

def main():
    log("watchdog starting")
    while True:
        try:
            con = sb.sb_conn()
            cur = con.cursor()
            cur.execute("SELECT v FROM mc_state WHERE k='watcher:state'")
            row = cur.fetchone()
            cash = 0.0
            if row:
                d = json.loads(row[0])
                cash = float(d.get('cash', 0))
            con.close()

            pids_ok = check_pids()
            if cash < FLOOR:
                log(f"ALERT: cash ${cash:.2f} < floor ${FLOOR}")
            elif not pids_ok:
                log(f"ALERT: daemon down, cash ${cash:.2f}")
            else:
                log(f"ok: cash ${cash:.2f}, pids ok")

            time.sleep(600)  # 10 min
        except Exception as e:
            log(f"watchdog error: {e}")
            time.sleep(600)

if __name__ == '__main__':
    main()
