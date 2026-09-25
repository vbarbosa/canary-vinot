"""Background loop of the panel: once a minute it records host metrics and runs due scheduled jobs.

Runs in a daemon thread of the single uvicorn worker, so it needs no cron and no game restart.
Scheduled jobs only enqueue commands for the Lua bridge, exactly like a click on the panel.
"""

import datetime as dt
import logging
import os
import threading
import time
from zoneinfo import ZoneInfo

from . import db, economy, events, realty, system

TZ = ZoneInfo(os.environ.get("COCKPIT_TZ", "America/Sao_Paulo"))
KEEP_DAYS = 7
WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
log = logging.getLogger("cockpit.scheduler")

# What a job can do. give_item/give_kit go to the friend group or to everyone online at run time.
JOB_ACTIONS = {
    "save": "Salvar o jogo",
    "broadcast": "Anunciar mensagem",
    "clean_map": "Limpar o chão do mapa",
    "start_raid": "Soltar uma raid",
    "event": "Começar um evento pronto",
    "give_kit": "Dar um kit",
    "give_item": "Dar um item",
    "give_training": "Dar kit de treino",
    "heal": "Curar todo mundo",
    "close_server": "Fechar o servidor",
    "open_server": "Abrir o servidor",
}


def next_run(job, after):
    """Unix time of the job's next run strictly after `after`, or 0 if it can never run."""
    kind = job["kind"]
    if kind == "interval":
        every = max(1, int(job["every_min"])) * 60
        base = job["last_run"] or after
        nxt = base + every
        return nxt if nxt > after else after + every
    try:
        hh, mm = (int(x) for x in job["at_time"].split(":"))
    except ValueError:
        return 0
    days = {int(d) for d in job["weekdays"] if d.isdigit()} if kind == "weekly" else set(range(7))
    if not days:
        return 0
    start = dt.datetime.fromtimestamp(after, TZ)
    for add in range(8):
        day = (start + dt.timedelta(days=add)).date()
        when = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ)
        if day.weekday() in days and when.timestamp() > after:
            return int(when.timestamp())
    return 0


def describe(job):
    if job["kind"] == "interval":
        m = int(job["every_min"])
        return f"a cada {m // 60} h" if m % 60 == 0 else f"a cada {m} min"
    if job["kind"] == "daily":
        return f"todo dia às {job['at_time']}"
    return ", ".join(WEEKDAYS[int(d)] for d in sorted(job["weekdays"])) + f" às {job['at_time']}"


def run_job(job, dispatch):
    ok, msg = dispatch(f"agenda:{job['name']}", job["action"], job["alvo"], job["text"], {"arg1": job["arg1"], "arg2": job["arg2"]})
    now = int(time.time())
    job = dict(job, last_run=now)
    db.run(
        "UPDATE cockpit_schedules SET last_run = %s, next_run = %s, last_result = %s WHERE id = %s",
        now, next_run(job, now) if job["enabled"] else 0, ("" if ok else "erro: ") + msg[:200], job["id"],
    )
    return ok, msg


def record_metrics():
    h = system.host("recorder")
    svc = {s["name"]: s["ms"] for s in system.services()}
    ts = int(time.time()) // 60 * 60
    mem = 100 * h["mem_used"] / h["mem_total"] if h.get("mem_total") else None
    disk = 100 * h["disk_used"] / h["disk_total"] if h.get("disk_total") else None
    db.run(
        "INSERT IGNORE INTO cockpit_host_metrics (ts, cpu, mem, load1, disk, game_ms, login_ms) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        ts, h.get("cpu"), mem, float(h["load"][0]) if h.get("load") else None, disk, svc.get("Jogo"), svc.get("Login"),
    )
    db.run("DELETE FROM cockpit_host_metrics WHERE ts < %s", ts - KEEP_DAYS * 86400)


def tick(dispatch):
    try:
        record_metrics()
    except Exception:
        log.exception("metrics")
    try:
        economy.record()
    except Exception:
        log.exception("economy")
    try:
        realty.tick()
    except Exception:
        log.exception("realty")
    try:
        events.signup_tick()
    except Exception:
        log.exception("signup")
    now = int(time.time())
    for job in db.all("SELECT * FROM cockpit_schedules WHERE enabled = 1 AND next_run > 0 AND next_run <= %s", now):
        try:
            run_job(job, dispatch)
        except Exception:
            log.exception("job %s", job["id"])


def start(dispatch):
    def loop():
        time.sleep(5)
        while True:
            tick(dispatch)
            time.sleep(60 - time.time() % 60 + 1)

    threading.Thread(target=loop, name="cockpit-scheduler", daemon=True).start()
