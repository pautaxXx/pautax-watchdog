#!/usr/bin/env python3
"""PAUTAX EXTERNAL WATCHDOG — runs on GitHub's servers (Actions), never on the trading Mac.

The Mac posts a heartbeat to a private ntfy topic every 5 minutes (08:00-18:00 ET weekdays). Every
5 minutes in the watch window (08:35-16:25 ET, trading days) this job reads that topic. If the newest
heartbeat is older than 13 minutes, the Mac is silent — crashed, asleep, off, off the network, or its
DNS is broken; from outside these look the same, and the Mac names the real cause itself when it comes
back. The job then pushes an URGENT alert to the phone topic, repeats it every 30 minutes while the
silence lasts, and sends "heartbeat back" once it returns. It also relays an outage the heartbeat
reports if the Mac's own push did not arrive.

It has no broker access and holds no broker keys: its only inputs are the two ntfy topic names
(repository secrets). Standard library only."""
import json, os, sys, urllib.request
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SRV = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
ALERT, BEAT = os.environ.get("NTFY_ALERT", ""), os.environ.get("NTFY_BEAT", "")
SILENT_MIN, REPEAT_MIN = 13, 30
# NYSE full-day closures 2026-2027 (update each December)
HOLIDAYS = {"2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
            "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
            "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}


def poll(topic, since):
    with urllib.request.urlopen(f"{SRV}/{topic}/json?poll=1&since={since}", timeout=20) as r:
        return [json.loads(x) for x in r.read().decode().splitlines() if x.strip()]


def push(title, msg, prio, tags):
    rq = urllib.request.Request(f"{SRV}/{ALERT}", data=msg.encode(), method="POST",
                                headers={"Title": title, "Priority": str(prio), "Tags": ",".join(tags)})
    with urllib.request.urlopen(rq, timeout=20) as r: print("pushed", r.status, title)


def hm(ts): return datetime.fromtimestamp(ts, ET).strftime("%H:%M")


def main():
    if not ALERT or not BEAT: sys.exit("NTFY_ALERT / NTFY_BEAT secrets are not set")
    now = datetime.now(ET)
    if os.environ.get("WATCHDOG_TEST") == "true":
        push("PAUTAX watchdog test", f"The external watchdog on GitHub can reach your phone ({now:%H:%M} ET).", 3, ["watchdog", "white_check_mark"]); return
    if now.weekday() >= 5 or now.date().isoformat() in HOLIDAYS or not ((8, 35) <= (now.hour, now.minute) <= (16, 25)):
        print(f"{now:%a %H:%M} ET: outside the watch window"); return
    beats = [m for m in poll(BEAT, "40m") if m.get("event") == "message"]
    sent = [m for m in poll(ALERT, "3h") if m.get("event") == "message"]
    mine = [m for m in sent if "watchdog" in (m.get("tags") or [])]
    last_silent = max([m["time"] for m in mine if "silent" in m.get("tags", [])], default=0)
    last_back = max([m["time"] for m in mine if "recovered" in m.get("tags", [])], default=0)
    t_now = now.timestamp()
    last = max(beats, key=lambda m: m["time"]) if beats else None
    age = (t_now - last["time"]) / 60 if last else None
    print(f"{now:%H:%M} ET: newest heartbeat {'none in 40 min' if last is None else f'{age:.1f} min old'}")
    if last is None or age > SILENT_MIN:
        if (t_now - last_silent) / 60 >= REPEAT_MIN:
            since = f"since {hm(last['time'])} ET ({age:.0f} min)" if last else "for more than 40 minutes"
            push("PAUTAX: TRADING MAC IS SILENT",
                 f"No heartbeat from the trading Mac {since}. It has crashed, slept, lost power or network, or its DNS failed. "
                 "The bots are not running and NO STOP IS BEING CHECKED. Wake/restart the Mac, or manage positions in the Alpaca app.",
                 5, ["watchdog", "silent", "rotating_light"])
        return
    try: b = json.loads(last.get("message") or "{}")
    except ValueError: b = {}
    if last_silent > last_back and last_silent > t_now - 6 * 3600:
        push("PAUTAX: heartbeat back", f"The trading Mac is posting again (newest {hm(last['time'])} ET). It reports the cause in its own alert.", 3, ["watchdog", "recovered", "white_check_mark"])
    if b.get("out") and not any(m["time"] > t_now - 1800 for m in sent):
        push("PAUTAX: outage reported by heartbeat", f"The Mac is up but reports its bots blind since {str(b.get('outs'))[11:16]} ET "
             f"(trend misses in a row {b.get('trc')}, network {'ok' if b.get('conn') else 'FAILING'}). About ${b.get('exp', 0):,} unmonitored.", 5, ["watchdog", "rotating_light"])


if __name__ == "__main__":
    main()
