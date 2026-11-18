#!/usr/bin/env python3
"""Niemeyer Family Tracker - Home Assistant app backend.

Stdlib only: a tiny JSON document store on SQLite, photo blobs on disk,
a long-poll change feed for the page, Home Assistant sensors/notifications
through the Supervisor API, a daily reminder check and an ICS calendar feed.
"""
import base64
import calendar
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import traceback
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

VERSION = "1.2.1"
DATA_DIR = os.environ.get("FT_DATA", "/data")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
BLOB_DIR = os.path.join(DATA_DIR, "blobs")
DB_PATH = os.path.join(DATA_DIR, "tracker.db")
OPTIONS_PATH = os.path.join(DATA_DIR, "options.json")
INGRESS_PORT = int(os.environ.get("FT_PORT", "8099"))
ICS_PORT = int(os.environ.get("FT_ICS_PORT", "8100"))
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HA_API = os.environ.get("FT_HA_API", "http://supervisor/core/api")
# Ingress traffic always comes from the Supervisor at 172.30.32.2.
ALLOWED_IPS = {"172.30.32.2", "127.0.0.1", "::1"}
OPEN_ACCESS = os.environ.get("FT_OPEN_ACCESS") == "1"  # local testing only
MAX_BLOB = 15 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}

os.makedirs(BLOB_DIR, exist_ok=True)


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def load_options():
    opts = {"notify_service": "", "persistent_notification": True, "reminder_time": "06:30",
            "due_window_days": 14, "repeat_days": 7}
    try:
        with open(OPTIONS_PATH) as f:
            opts.update(json.load(f) or {})
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        log("options read failed:", e)
    return opts


OPTIONS = load_options()


def tz():
    name = os.environ.get("TZ") or "America/Chicago"
    try:
        return ZoneInfo(name) if ZoneInfo else None
    except Exception:  # noqa: BLE001
        return None


def now():
    return dt.datetime.now(tz())


def today():
    return now().date()


# --------------------------------------------------------------------------- store
class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS docs(
            path TEXT PRIMARY KEY, parent TEXT NOT NULL, id TEXT NOT NULL,
            data TEXT NOT NULL, version INTEGER NOT NULL, updated TEXT NOT NULL)""")
        self.conn.execute("CREATE INDEX IF NOT EXISTS docs_parent ON docs(parent)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS changes(seq INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT)")
        self.conn.commit()
        self.listeners = []

    @staticmethod
    def check_path(path, kind):
        parts = [p for p in str(path or "").split("/")]
        if not parts or any(not re.fullmatch(r"[A-Za-z0-9_.\-]{1,120}", p) for p in parts):
            raise ValueError("bad path")
        if kind == "doc" and len(parts) % 2:
            raise ValueError("a document path needs collection/id")
        if kind == "col" and not len(parts) % 2:
            raise ValueError("a collection path needs an odd number of segments")
        return "/".join(parts)

    def seq(self):
        with self.lock:
            r = self.conn.execute("SELECT COALESCE(MAX(seq),0) FROM changes").fetchone()
            return r[0]

    def _changed(self, path):
        self.conn.execute("INSERT INTO changes(path) VALUES(?)", (path,))
        self.conn.execute("DELETE FROM changes WHERE seq < (SELECT MAX(seq) - 5000 FROM changes)")

    def get(self, path):
        path = self.check_path(path, "doc")
        with self.lock:
            r = self.conn.execute("SELECT data, version, updated FROM docs WHERE path=?", (path,)).fetchone()
        if not r:
            return None
        return {"id": path.split("/")[-1], "data": json.loads(r[0]), "version": r[1], "updatedAt": r[2]}

    def list(self, col):
        col = self.check_path(col, "col")
        with self.lock:
            rows = self.conn.execute("SELECT id, data, version, updated FROM docs WHERE parent=? ORDER BY id", (col,)).fetchall()
        return [{"id": r[0], "data": json.loads(r[1]), "version": r[2], "updatedAt": r[3]} for r in rows]

    def set(self, path, data, notify=True):
        path = self.check_path(path, "doc")
        if not isinstance(data, dict):
            raise ValueError("document data must be an object")
        parent, _, did = path.rpartition("/")
        stamp = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        with self.cond:
            cur = self.conn.execute("SELECT version FROM docs WHERE path=?", (path,)).fetchone()
            ver = (cur[0] + 1) if cur else 1
            self.conn.execute("INSERT OR REPLACE INTO docs(path,parent,id,data,version,updated) VALUES(?,?,?,?,?,?)",
                              (path, parent, did, json.dumps(data, separators=(",", ":")), ver, stamp))
            self._changed(path)
            self.conn.commit()
            self.cond.notify_all()
        if notify:
            self._fire(path)
        return ver

    def delete(self, path):
        path = self.check_path(path, "doc")
        with self.cond:
            self.conn.execute("DELETE FROM docs WHERE path=? OR path LIKE ?", (path, path + "/%"))
            self._changed(path)
            self.conn.commit()
            self.cond.notify_all()
        self._fire(path)

    def add(self, col, data):
        col = self.check_path(col, "col")
        did = secrets.token_hex(10)
        self.set(col + "/" + did, data)
        return did

    def changes_since(self, since, timeout=25.0):
        deadline = time.time() + timeout
        with self.cond:
            while True:
                cur = self.seq()
                if since < 0:
                    return cur, None
                if cur > since:
                    rows = self.conn.execute("SELECT path FROM changes WHERE seq>?", (since,)).fetchall()
                    oldest = self.conn.execute("SELECT MIN(seq) FROM changes").fetchone()[0] or 0
                    if oldest > since + 1:
                        return cur, None  # gap: tell the page to refresh everything
                    return cur, sorted({r[0] for r in rows})
                left = deadline - time.time()
                if left <= 0:
                    return cur, []
                self.cond.wait(left)

    def dump(self):
        with self.lock:
            rows = self.conn.execute("SELECT path, data FROM docs ORDER BY path").fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}

    def replace_all(self, docs):
        with self.cond:
            self.conn.execute("DELETE FROM docs")
            stamp = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
            for path, data in docs.items():
                path = self.check_path(path, "doc")
                parent, _, did = path.rpartition("/")
                self.conn.execute("INSERT INTO docs(path,parent,id,data,version,updated) VALUES(?,?,?,?,1,?)",
                                  (path, parent, did, json.dumps(data, separators=(",", ":")), stamp))
            self._changed("*")
            self.conn.commit()
            self.cond.notify_all()
        self._fire("*")

    def on_change(self, fn):
        self.listeners.append(fn)

    def _fire(self, path):
        for fn in self.listeners:
            try:
                fn(path)
            except Exception:  # noqa: BLE001
                traceback.print_exc()


STORE = Store(DB_PATH)


# --------------------------------------------------------------------------- blobs
def blob_path(bid):
    if not re.fullmatch(r"[a-f0-9]{16,64}", bid or ""):
        return None
    for ext in IMAGE_TYPES.values():
        p = os.path.join(BLOB_DIR, f"{bid}.{ext}")
        if os.path.exists(p):
            return p
    return None


def save_blob(raw, ctype, bid=None):
    ext = IMAGE_TYPES.get((ctype or "").split(";")[0].strip().lower())
    if not ext:
        raise ValueError("unsupported_type")
    if len(raw) > MAX_BLOB:
        raise ValueError("too_large")
    bid = bid or hashlib.sha256(raw).hexdigest()[:32]
    if not re.fullmatch(r"[a-f0-9]{16,64}", bid):
        raise ValueError("bad blob id")
    with open(os.path.join(BLOB_DIR, f"{bid}.{ext}"), "wb") as f:
        f.write(raw)
    return bid


# --------------------------------------------------------------------------- dates & status
FULL = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH = re.compile(r"^\d{4}-\d{2}$")
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def is_date(v):
    return isinstance(v, str) and (FULL.match(v) or MONTH.match(v)) is not None


def start_date(v):
    if isinstance(v, str) and FULL.match(v):
        y, m, d = map(int, v.split("-"))
        return dt.date(y, m, d)
    if isinstance(v, str) and MONTH.match(v):
        y, m = map(int, v.split("-"))
        return dt.date(y, m, 1)
    return None


def due_date(v):
    if isinstance(v, str) and MONTH.match(v):
        y, m = map(int, v.split("-"))
        return dt.date(y, m, calendar.monthrange(y, m)[1])
    return start_date(v)


def add_months(v, n):
    d = start_date(v)
    if not d:
        return ""
    t = d.month - 1 + int(n)
    y, m = d.year + t // 12, t % 12 + 1
    if MONTH.match(v):
        return f"{y}-{m:02d}"
    return f"{y}-{m:02d}-{min(d.day, calendar.monthrange(y, m)[1]):02d}"


def fmt(d):
    return f"{MON[d.month - 1]} {d.day}, {d.year}"


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def vname(v):
    return " ".join(str(x) for x in [v.get("year"), v.get("make"), v.get("model")] if x)


def unit_of(v):
    return v.get("usageUnit") or ("hrs" if v.get("type") in ("UTV", "Mower", "Watercraft") else "mi")


def list_cycle(c, t):
    s = int(c.get("startMonth") or 1)
    d = int(c.get("dueMonth") or s)
    ws = dt.date(t.year, s, 1)
    if ws > t:
        ws = dt.date(t.year - 1, s, 1)
    dy = ws.year + (1 if d < s else 0)
    due = dt.date(dy, d, calendar.monthrange(dy, d)[1])
    return ws, due


def collect_items(t=None, window=None):
    """Everything due/overdue/low, as dicts the page, sensors, calendar and reminder all share."""
    t = t or today()
    window = OPTIONS.get("due_window_days", 14) if window is None else window
    horizon = t + dt.timedelta(days=window)
    items = []

    def add(**k):
        if k.get("date"):
            k["days"] = (k["date"] - t).days
        items.append(k)

    for d in STORE.list("vehicles"):
        v, vid = d["data"], d["id"]
        if v.get("status") == "gone":
            continue
        name = vname(v)
        r = v.get("regDue")
        if is_date(r):
            add(section="Garage", key=f"{vid}|reg|{r}", title=f"{name} — Registration", date=due_date(r), link=f"v-{vid}", kind="reg")
        if v.get("oilTracked"):
            nxt = ""
            if (num(v.get("oilIntervalMonths")) or 0) > 0 and is_date(v.get("lastOil")):
                nxt = add_months(v["lastOil"], v["oilIntervalMonths"])
            elif is_date(v.get("nextOil")):
                nxt = v["nextOil"]
            left = None
            if num(v.get("oilIntervalMiles")) and num(v.get("lastOilMiles")) is not None and num(v.get("mileage")) is not None:
                left = v["lastOilMiles"] + v["oilIntervalMiles"] - v["mileage"]
            u = unit_of(v)
            thresh = max(5, v["oilIntervalMiles"] * 0.1) if (u == "hrs" and num(v.get("oilIntervalMiles"))) else 500
            usage_due = left is not None and left <= thresh
            if nxt or left is not None:
                dd = due_date(nxt) if nxt else None
                add(section="Garage", key=f"{vid}|oil|{dd.isoformat() if dd else 'usage'}", title=f"{name} — Oil change",
                    date=dd, link=f"v-{vid}", kind="oil", usage_due=usage_due,
                    left=(f"{left:,.0f} {u} left" if left is not None else None))
    for d in STORE.list("home"):
        h, hid = d["data"], d["id"]
        if h.get("status") == "archived":
            continue
        nxt = ""
        if (num(h.get("intervalMonths")) or 0) > 0 and is_date(h.get("lastDone")):
            nxt = add_months(h["lastDone"], h["intervalMonths"])
        elif is_date(h.get("nextDue")):
            nxt = h["nextDue"]
        if nxt:
            dd = due_date(nxt)
            add(section="Home", key=f"{hid}|home|{dd.isoformat()}", title=h.get("name", "Home task"), date=dd, link=f"h-{hid}", kind="home")
    for d in STORE.list("equipment"):
        e = d["data"]
        if is_date(e.get("warrantyEnds")):
            dd = due_date(e["warrantyEnds"])
            if dd >= t:
                add(section="Home", key=f"{d['id']}|warranty|{e['warrantyEnds']}", title=f"{e.get('name', 'Equipment')} — warranty ends",
                    date=dd, link="home", kind="warranty")
    for d in STORE.list("checklists"):
        c = d["data"]
        ws, due = list_cycle(c, t)
        its = c.get("items") or []
        done = sum(1 for it in its if start_date(it.get("doneAt")) and start_date(it.get("doneAt")) >= ws)
        complete = (start_date(c.get("completedAt")) and start_date(c.get("completedAt")) >= ws) or (its and done == len(its))
        add(section="Seasonal", key=f"{d['id']}|season|{ws.strftime('%Y-%m')}", title=c.get("name", "Checklist"), date=due,
            link=f"s-{d['id']}", kind="season", window_start=ws, complete=bool(complete), progress=f"{done}/{len(its)} done")
    for d in STORE.list("parts"):
        p = d["data"]
        if num(p.get("qty")) is not None and num(p.get("minQty")) is not None and p["qty"] <= p["minQty"]:
            pn = f" ({p['partNumber']})" if p.get("partNumber") else ""
            add(section="Low stock", key=f"{d['id']}|low", title=f"{p.get('name', 'Part')}{pn}", date=None, link="parts", kind="low",
                detail=f"{p['qty']:g} on hand, min {p['minQty']:g}")

    due_items = []
    for it in items:
        k = it["kind"]
        if k == "season":
            if it["complete"] or not (it["window_start"] <= t <= it["date"] + dt.timedelta(days=60)):
                continue
        elif k == "low":
            pass
        elif k == "oil":
            if not ((it["date"] and it["date"] <= horizon) or it.get("usage_due")):
                continue
        elif k == "warranty":
            if not it["date"] <= horizon:
                continue
        else:
            if not (it["date"] and it["date"] <= horizon):
                continue
        due_items.append(it)
    order = {"Garage": 0, "Home": 1, "Seasonal": 2, "Low stock": 3}
    due_items.sort(key=lambda i: (order[i["section"]], i.get("days") if i.get("days") is not None else -9999))
    return due_items, items


def line_for(it):
    if it["kind"] == "low":
        return f"{it['title']} — {it['detail']}"
    if it["kind"] == "warranty":
        return f"{it['title']} {fmt(it['date'])}"
    when = ""
    if it.get("date"):
        n = it["days"]
        rel = f"{-n} days overdue" if n < 0 else ("due today" if n == 0 else f"due in {n} days")
        when = f" — due {fmt(it['date'])} ({rel})"
    if it["kind"] == "season":
        when = f" — {it['progress']}" + when.replace("— due", "— due by")
    extra = f", {it['left']}" if it.get("left") else ""
    return f"{it['title']}{when}{extra}"


# --------------------------------------------------------------------------- Home Assistant
HA_STATUS = {"connected": False, "error": "", "last_publish": None, "last_reminder": None, "last_reminder_result": ""}


def ha_call(method, path, body=None, timeout=10):
    if not SUPERVISOR_TOKEN:
        raise RuntimeError("no Supervisor token (not running under Home Assistant)")
    req = urllib.request.Request(HA_API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def publish_sensors():
    try:
        due, _ = collect_items()
        t = today()
        overdue = [i for i in due if i.get("days") is not None and i["days"] < 0]
        soon = [i for i in due if i["kind"] != "low" and not (i.get("days") is not None and i["days"] < 0)]
        low = [i for i in due if i["kind"] == "low"]
        dated = sorted([i for i in due if i.get("date")], key=lambda i: i["date"])

        def attrs(lst):
            return [{"section": i["section"], "item": line_for(i), "due": i["date"].isoformat() if i.get("date") else None} for i in lst]

        common = {"attribution": "Niemeyer Family Tracker"}
        ha_call("POST", "/states/sensor.family_tracker_overdue", {"state": len(overdue), "attributes": {
            **common, "friendly_name": "Family Tracker overdue", "icon": "mdi:alert-circle", "unit_of_measurement": "items", "items": attrs(overdue)}})
        ha_call("POST", "/states/sensor.family_tracker_due_soon", {"state": len(soon), "attributes": {
            **common, "friendly_name": "Family Tracker due soon", "icon": "mdi:calendar-clock", "unit_of_measurement": "items", "items": attrs(soon)}})
        ha_call("POST", "/states/sensor.family_tracker_low_stock", {"state": len(low), "attributes": {
            **common, "friendly_name": "Family Tracker low stock", "icon": "mdi:package-variant", "unit_of_measurement": "items", "items": attrs(low)}})
        nxt = dated[0] if dated else None
        ha_call("POST", "/states/sensor.family_tracker_next_due", {"state": nxt["date"].isoformat() if nxt else "unknown", "attributes": {
            **common, "friendly_name": "Family Tracker next due", "icon": "mdi:calendar-arrow-right", "device_class": "date",
            "item": line_for(nxt) if nxt else None, "as_of": t.isoformat()}})
        HA_STATUS.update(connected=True, error="", last_publish=now().isoformat(timespec="seconds"))
    except Exception as e:  # noqa: BLE001
        HA_STATUS.update(connected=False, error=str(e)[:200])


def app_slug():
    # Supervisor sets HOSTNAME to "<repo-hash>-family-tracker"; the panel slug is the same with underscores.
    h = os.environ.get("HOSTNAME", "")
    return h.replace("-", "_") if h.endswith("family-tracker") else "family_tracker"


def run_reminder(force=False):
    """Send one notification listing everything due; repeat per item every repeat_days."""
    due, _ = collect_items()
    t = today()
    repeat = int(OPTIONS.get("repeat_days", 7))
    state_doc = STORE.get("meta/notifications")
    sent = dict((state_doc or {}).get("data", {}).get("sent", {}))
    need = [i for i in due if i["key"] not in sent or (start_date(sent[i["key"]]) and (t - start_date(sent[i["key"]])).days >= repeat)]
    keep = {i["key"]: sent[i["key"]] for i in due if i["key"] in sent}
    if not need and not force:
        if keep != sent:
            STORE.set("meta/notifications", {"sent": keep})
        HA_STATUS.update(last_reminder=now().isoformat(timespec="seconds"), last_reminder_result="Nothing new to remind about")
        return {"sent": False, "due": len(due)}
    if not due:
        HA_STATUS.update(last_reminder=now().isoformat(timespec="seconds"), last_reminder_result="Nothing due")
        return {"sent": False, "due": 0}
    names = []
    for i in due[:4]:
        names.append(i["title"].replace(" — ", " "))
    title = f"Family Tracker: {len(due)} item{'s' if len(due) != 1 else ''} due"
    lines, last = [], None
    for i in due:
        if i["section"] != last:
            lines.append(("" if last is None else "\n") + i["section"].upper())
            last = i["section"]
        lines.append("• " + line_for(i))
    message = "\n".join(lines)
    errors = []
    try:
        ha_call("POST", "/events/family_tracker_reminder", {"count": len(due), "items": [line_for(i) for i in due]})
    except Exception as e:  # noqa: BLE001
        errors.append(f"event: {e}")
    if OPTIONS.get("persistent_notification", True):
        try:
            ha_call("POST", "/services/persistent_notification/create",
                    {"title": title, "message": message.replace("\n", "  \n"), "notification_id": "family_tracker_due"})
        except Exception as e:  # noqa: BLE001
            errors.append(f"persistent notification: {e}")
    svc = (OPTIONS.get("notify_service") or "").strip().removeprefix("notify.")
    if svc:
        try:
            url = f"/hassio/ingress/{app_slug()}"
            ha_call("POST", f"/services/notify/{svc}", {"title": title, "message": message,
                                                         "data": {"url": url, "clickAction": url}})
        except Exception as e:  # noqa: BLE001
            errors.append(f"notify.{svc}: {e}")
    ok = not (svc and any(x.startswith("notify.") for x in errors)) and len(errors) < 3
    if ok:
        for i in due:
            keep[i["key"]] = t.isoformat()
        STORE.set("meta/notifications", {"sent": keep})
    HA_STATUS.update(last_reminder=now().isoformat(timespec="seconds"),
                     last_reminder_result=("Sent: " + title) if ok else ("Failed — " + "; ".join(errors))[:300])
    return {"sent": ok, "due": len(due), "errors": errors, "title": title, "message": message}


def scheduler():
    publish_sensors()
    last_publish = time.time()
    last_run_day = None
    state = STORE.get("meta/scheduler")
    if state:
        last_run_day = state["data"].get("lastRunDay")
    while True:
        try:
            n = now()
            hh, mm = map(int, str(OPTIONS.get("reminder_time", "06:30")).split(":"))
            if n.hour * 60 + n.minute >= hh * 60 + mm and last_run_day != n.date().isoformat():
                log("daily reminder check:", run_reminder())
                last_run_day = n.date().isoformat()
                STORE.set("meta/scheduler", {"lastRunDay": last_run_day}, notify=False)
            if time.time() - last_publish > 300:
                publish_sensors()
                last_publish = time.time()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        time.sleep(30)


_pub_timer = None


def on_store_change(path):
    global _pub_timer
    if path.startswith("meta/"):
        return
    if _pub_timer:
        _pub_timer.cancel()
    _pub_timer = threading.Timer(3.0, publish_sensors)
    _pub_timer.daemon = True
    _pub_timer.start()


STORE.on_change(on_store_change)


# --------------------------------------------------------------------------- calendar
def ics_escape(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_ics():
    _, items = collect_items(window=3650)
    stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Niemeyer Family Tracker//EN", "CALSCALE:GREGORIAN",
           "X-WR-CALNAME:Family Tracker"]
    for i in items:
        if not i.get("date") or i["kind"] == "low":
            continue
        if i["kind"] == "season" and i.get("complete"):
            continue
        d = i["date"]
        uid = hashlib.sha1(i["key"].encode()).hexdigest()[:20] + "@family-tracker"
        summary = i["title"] + (f" ({i['progress']})" if i["kind"] == "season" else "")
        out += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{(d + dt.timedelta(days=1)).strftime('%Y%m%d')}", f"SUMMARY:{ics_escape(summary)}",
                f"CATEGORIES:{ics_escape(i['section'])}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "FamilyTracker/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt_, *args):  # quieter logs
        if not str(args[1] if len(args) > 1 else "").startswith("2"):
            log("http", self.address_string(), fmt_ % args)

    # -- helpers
    def allowed(self):
        if self.server.ics_only:
            return True
        return OPEN_ACCESS or self.client_address[0] in ALLOWED_IPS

    def send(self, code, body=b"", ctype="application/json", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def body(self, limit=60 * 1024 * 1024):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("too_large")
        return self.rfile.read(n) if n else b""

    def jbody(self):
        raw = self.body()
        return json.loads(raw or b"null")

    def q(self):
        u = urlparse(self.path)
        return u.path, {k: v[0] for k, v in parse_qs(u.query).items()}

    # -- routes
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {"error": "forbidden"})
        path, q = self.q()
        try:
            if self.server.ics_only:
                if path in ("/calendar.ics", "/"):
                    return self.send(200, build_ics(), "text/calendar; charset=utf-8")
                return self.send(404, {"error": "not found"})
            if path in ("/", "/index.html"):
                with open(os.path.join(STATIC_DIR, "index.html"), "rb") as f:
                    return self.send(200, f.read(), "text/html; charset=utf-8")
            if path == "/api/col":
                return self.send(200, {"docs": STORE.list(q.get("path"))})
            if path == "/api/doc":
                d = STORE.get(q.get("path"))
                return self.send(200, {"exists": bool(d), **(d or {})})
            if path == "/api/changes":
                seq, paths = STORE.changes_since(int(q.get("since", "-1")), timeout=min(25.0, float(q.get("wait", "25"))))
                return self.send(200, {"seq": seq, "paths": paths})
            if path.startswith("/_blob/"):
                p = blob_path(path[len("/_blob/"):])
                if not p:
                    return self.send(404, {"error": "not found"})
                ext = p.rsplit(".", 1)[1]
                ctype = {v: k for k, v in IMAGE_TYPES.items()}[ext]
                with open(p, "rb") as f:
                    return self.send(200, f.read(), ctype, {"Cache-Control": "private, max-age=31536000, immutable"})
            if path == "/api/status":
                due, _ = collect_items()
                return self.send(200, {"version": VERSION, "ha": HA_STATUS, "underHA": bool(SUPERVISOR_TOKEN),
                                       "options": {k: OPTIONS.get(k) for k in ("notify_service", "persistent_notification", "reminder_time", "due_window_days", "repeat_days")},
                                       "due": [line_for(i) for i in due], "hostname": os.environ.get("HOSTNAME", ""), "icsPort": ICS_PORT,
                                       "timezone": os.environ.get("TZ", "")})
            if path == "/api/export":
                blobs = {}
                for fn in os.listdir(BLOB_DIR):
                    bid, ext = fn.rsplit(".", 1)
                    with open(os.path.join(BLOB_DIR, fn), "rb") as f:
                        blobs[bid] = {"type": {v: k for k, v in IMAGE_TYPES.items()}.get(ext, "image/jpeg"), "data": base64.b64encode(f.read()).decode()}
                body = json.dumps({"format": "family-tracker-backup", "version": 1, "exportedAt": now().isoformat(timespec="seconds"),
                                   "docs": STORE.dump(), "blobs": blobs}).encode()
                return self.send(200, body, "application/json",
                                 {"Content-Disposition": f'attachment; filename="family-tracker-backup-{today().isoformat()}.json"'})
            if path == "/calendar.ics":
                return self.send(200, build_ics(), "text/calendar; charset=utf-8")
            return self.send(404, {"error": "not found"})
        except ValueError as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self.send(500, {"error": str(e)})

    def do_PUT(self):
        if not self.allowed() or self.server.ics_only:
            return self.send(403, {"error": "forbidden"})
        path, q = self.q()
        try:
            if path == "/api/doc":
                ver = STORE.set(q.get("path"), self.jbody())
                return self.send(200, {"ok": True, "version": ver})
            return self.send(404, {"error": "not found"})
        except ValueError as e:
            return self.send(400, {"error": str(e)})

    def do_DELETE(self):
        if not self.allowed() or self.server.ics_only:
            return self.send(403, {"error": "forbidden"})
        path, q = self.q()
        try:
            if path == "/api/doc":
                STORE.delete(q.get("path"))
                return self.send(200, {"ok": True})
            if path.startswith("/api/blob/"):
                p = blob_path(path[len("/api/blob/"):])
                if p:
                    os.remove(p)
                return self.send(200, {"ok": True})
            return self.send(404, {"error": "not found"})
        except ValueError as e:
            return self.send(400, {"error": str(e)})

    def do_POST(self):
        if not self.allowed() or self.server.ics_only:
            return self.send(403, {"error": "forbidden"})
        path, q = self.q()
        try:
            if path == "/api/col":
                did = STORE.add(q.get("path"), self.jbody())
                return self.send(200, {"ok": True, "id": did})
            if path == "/api/blob":
                bid = save_blob(self.body(MAX_BLOB + 1), self.headers.get("Content-Type"))
                return self.send(200, {"id": bid})
            if path == "/api/remind":
                return self.send(200, run_reminder(force=True), "application/json")
            if path == "/api/publish":
                publish_sensors()
                return self.send(200, HA_STATUS)
            if path == "/api/import":
                data = self.jbody()
                if not isinstance(data, dict) or data.get("format") != "family-tracker-backup" or not isinstance(data.get("docs"), dict):
                    raise ValueError("That isn't a Family Tracker backup file")
                n_blobs = 0
                for bid, b in (data.get("blobs") or {}).items():
                    save_blob(base64.b64decode(b["data"]), b.get("type", "image/jpeg"), bid)
                    n_blobs += 1
                STORE.replace_all(data["docs"])
                log(f"imported {len(data['docs'])} documents and {n_blobs} photos")
                return self.send(200, {"ok": True, "docs": len(data["docs"]), "photos": n_blobs})
            return self.send(404, {"error": "not found"})
        except ValueError as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self.send(500, {"error": str(e)})


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, handler, ics_only=False):
        self.ics_only = ics_only
        super().__init__(addr, handler)


def main():
    log(f"Niemeyer Family Tracker {VERSION} starting (data in {DATA_DIR}, HA API {'available' if SUPERVISOR_TOKEN else 'not available'})")
    threading.Thread(target=scheduler, daemon=True).start()
    ics = Server(("0.0.0.0", ICS_PORT), Handler, ics_only=True)
    threading.Thread(target=ics.serve_forever, daemon=True).start()
    Server(("0.0.0.0", INGRESS_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
