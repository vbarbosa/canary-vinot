"""Cockpit: web admin panel for the VinOT game master.

Pages are server-rendered Jinja templates; htmx swaps small fragments and
SortableJS does drag and drop. Anything that touches a live player is queued in
`cockpit_commands` and executed by data/scripts/globalevents/cockpit.lua.
"""

import hashlib
import html
import hmac
import os
import re
import secrets
import time
from collections import defaultdict

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import db, gamedata, system
from .palette import PALETTE

HERE = os.path.dirname(__file__)
ICON_DIR = os.environ.get("COCKPIT_ICON_DIR", os.path.join(HERE, "..", "icons"))
GOD_GROUP = 6
SESSION_HOURS = 12

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("COCKPIT_SECRET") or secrets.token_hex(32),
    max_age=SESSION_HOURS * 3600,
    same_site="strict",
    session_cookie="cockpit",
)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))
templates.env.globals.update(vocations=gamedata.vocations(), now=lambda: int(time.time()), hb=system.human_bytes, hd=system.human_duration)


@app.on_event("startup")
def startup():
    db.init_schema()


# ---------------------------------------------------------------- auth

_failures = defaultdict(list)


def _password_ok(stored, password):
    # Canary uses passwordType = "sha1"; the panel checks the same hash the game does.
    return hmac.compare_digest(stored.lower(), hashlib.sha1(password.encode()).hexdigest())


def _fingerprint(stored):
    return hashlib.sha256(("cockpit:" + stored).encode()).hexdigest()[:16]


def current_user(request: Request):
    """Re-checks the game account on every request, so a password change or a lost God
    group logs the panel out immediately (the login is the game's own)."""
    s = request.session
    if not s.get("acc"):
        return None
    acc = db.one("SELECT id, name, password FROM accounts WHERE id = %s", s["acc"])
    if not acc or _fingerprint(acc["password"]) != s.get("fp"):
        s.clear()
        return None
    god = db.one("SELECT name FROM players WHERE account_id = %s AND group_id >= %s ORDER BY id LIMIT 1", acc["id"], GOD_GROUP)
    if not god:
        s.clear()
        return None
    return {"account": acc["name"], "me": god["name"], "csrf": s["csrf"]}


class NotLoggedIn(Exception):
    pass


@app.exception_handler(NotLoggedIn)
def not_logged_in(request: Request, exc: NotLoggedIn):
    if request.headers.get("HX-Request"):
        return Response(headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


def require(request: Request, post=False):
    user = current_user(request)
    if not user:
        raise NotLoggedIn()
    if post:
        token = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(token, user["csrf"]):
            raise HTTPException(status_code=403, detail="CSRF")
    return user


def page(request, name, user, **ctx):
    return templates.TemplateResponse(request, name, {"user": user, **ctx})


def toast(msg, ok=True):
    cls = "ok" if ok else "err"
    return HTMLResponse(f'<div class="toast {cls}">{html.escape(msg)}</div>')


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    ip = request.client.host if request.client else "?"
    recent = [t for t in _failures[ip] if t > time.time() - 300]
    _failures[ip] = recent
    if len(recent) >= 5:
        return templates.TemplateResponse(request, "login.html", {"error": "Muitas tentativas. Espere 5 minutos."}, status_code=429)
    acc = db.one("SELECT id, name, password FROM accounts WHERE email = %s OR name = %s LIMIT 1", email.strip(), email.strip())
    god = acc and db.one("SELECT 1 AS ok FROM players WHERE account_id = %s AND group_id >= %s LIMIT 1", acc["id"], GOD_GROUP)
    if not acc or not _password_ok(acc["password"], password) or not god:
        _failures[ip].append(time.time())
        return templates.TemplateResponse(request, "login.html", {"error": "Conta, senha ou permissão inválida."}, status_code=401)
    request.session.clear()
    request.session.update(acc=acc["id"], fp=_fingerprint(acc["password"]), csrf=secrets.token_urlsafe(24))
    db.audit(acc["name"], "login", "", ip)
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    require(request, post=True)
    request.session.clear()
    return Response(headers={"HX-Redirect": "/login"})


# ---------------------------------------------------------------- helpers


def online_names():
    return {r["name"] for r in db.all("SELECT name FROM cockpit_online")}


def group_players():
    return db.all(
        "SELECT p.id, p.name, p.level, p.vocation, p.looktype, p.sex, o.player_id IS NOT NULL AS online, o.health, o.healthmax "
        "FROM cockpit_group g JOIN players p ON p.id = g.player_id LEFT JOIN cockpit_online o ON o.player_id = p.id ORDER BY p.name"
    )


def bridge_status():
    row = db.one("SELECT MAX(updated_at) AS t FROM cockpit_online")
    pending = db.one("SELECT MIN(created_at) AS t FROM cockpit_commands WHERE status = 'pending' AND action IN ('broadcast','save')")
    if pending and pending["t"] and pending["t"] < time.time() - 10:
        return "parada"
    if row and row["t"]:
        return "ok"
    return "sem jogadores"


def resolve_targets(alvo):
    """'turma' -> every group member, 'todos' -> everyone online, a number -> that player."""
    if alvo == "turma":
        return [p["name"] for p in group_players()]
    if alvo == "todos":
        return sorted(online_names())
    if alvo.isdigit():
        p = db.one("SELECT name FROM players WHERE id = %s", int(alvo))
        return [p["name"]] if p else []
    return []


def clamp(v, lo, hi):
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = lo
    return max(lo, min(hi, v))


# Allowlist of what the panel can ask the game to do, with the bounds of each argument.
ACTIONS = {
    "give_item": {"arg1": (100, 100000), "arg2": (1, 1000)},
    "give_money": {"arg1": (1, 100000000)},
    "set_level": {"arg1": (1, 2000)},
    "set_skill": {"arg1": (0, 99), "arg2": (0, 200)},
    "set_outfit": {"arg1": (0, 5000), "arg2": (0, 3), "arg3": (0, 1000)},
    "add_mount": {"arg1": (1, 1000)},
    "heal": {},
    "temple": {},
    "summon_to": {},
    "effect": {"arg1": (1, 300)},
    "say_over": {"text": True},
    "narrate_to": {"text": True},
    "kick": {},
}
GLOBAL_ACTIONS = {"broadcast": {"text": True}, "save": {}, "close_server": {}, "open_server": {}, "clean_map": {}}


# ---------------------------------------------------------------- pages


@app.get("/", response_class=HTMLResponse)
def overview(request: Request):
    user = require(request)
    return page(request, "overview.html", user, bridge=bridge_status(), effects=gamedata.EFFECTS)


@app.get("/parts/online", response_class=HTMLResponse)
def part_online(request: Request):
    user = require(request)
    rows = db.all("SELECT o.*, p.id FROM cockpit_online o JOIN players p ON p.id = o.player_id ORDER BY o.name")
    return page(request, "_online.html", user, rows=rows, bridge=bridge_status())


@app.get("/parts/feed", response_class=HTMLResponse)
def part_feed(request: Request, alvo: str = ""):
    user = require(request)
    if alvo.isdigit():
        p = db.one("SELECT name FROM players WHERE id = %s", int(alvo))
        rows = db.all("SELECT * FROM cockpit_commands WHERE target = %s ORDER BY id DESC LIMIT 15", p["name"] if p else "")
    else:
        rows = db.all("SELECT * FROM cockpit_commands ORDER BY id DESC LIMIT 20")
    return page(request, "_feed.html", user, rows=rows, names=gamedata.item_names())


@app.get("/jogadores", response_class=HTMLResponse)
def players(request: Request, q: str = ""):
    user = require(request)
    rows = db.all(
        "SELECT p.id, p.name, p.level, p.vocation, p.group_id, a.name AS account, a.email, "
        "o.player_id IS NOT NULL AS online, g.player_id IS NOT NULL AS in_group, "
        "(SELECT 1 FROM account_bans b WHERE b.account_id = p.account_id) AS banned "
        "FROM players p JOIN accounts a ON a.id = p.account_id "
        "LEFT JOIN cockpit_online o ON o.player_id = p.id LEFT JOIN cockpit_group g ON g.player_id = p.id "
        "WHERE p.name LIKE %s ORDER BY online DESC, p.level DESC LIMIT 100",
        f"%{q}%",
    )
    name = "_players_rows.html" if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "rows" else "players.html"
    return page(request, name, user, rows=rows, q=q)


@app.post("/jogadores/{pid}/turma", response_class=HTMLResponse)
def toggle_group(request: Request, pid: int):
    user = require(request, post=True)
    if db.one("SELECT 1 AS x FROM cockpit_group WHERE player_id = %s", pid):
        db.run("DELETE FROM cockpit_group WHERE player_id = %s", pid)
        inside = False
    else:
        db.run("INSERT INTO cockpit_group (player_id) VALUES (%s)", pid)
        inside = True
    db.audit(user["account"], "turma", str(pid), "entrou" if inside else "saiu")
    return HTMLResponse(
        f'<button class="{"" if inside else "outline"} secondary small" hx-post="/jogadores/{pid}/turma" hx-swap="outerHTML">'
        f'{"Na turma" if inside else "Pôr na turma"}</button>'
    )


@app.post("/jogadores/{pid}/ban", response_class=HTMLResponse)
def ban(request: Request, pid: int, dias: int = Form(7), motivo: str = Form("")):
    user = require(request, post=True)
    p = db.one("SELECT name, account_id, group_id FROM players WHERE id = %s", pid)
    if not p or p["group_id"] >= GOD_GROUP:
        return toast("Não dá pra banir esse jogador.", ok=False)
    now = int(time.time())
    me = db.one("SELECT id FROM players WHERE name = %s", user["me"])
    db.run(
        "REPLACE INTO account_bans (account_id, reason, banned_at, expires_at, banned_by) VALUES (%s,%s,%s,%s,%s)",
        p["account_id"], motivo[:200] or "Cockpit", now, now + clamp(dias, 1, 3650) * 86400, me["id"],
    )
    db.enqueue(user["account"], "kick", p["name"])
    db.audit(user["account"], "ban", p["name"], f"{dias} dias {motivo}")
    return toast(f"{p['name']} banido por {dias} dias.")


@app.post("/jogadores/{pid}/desban", response_class=HTMLResponse)
def unban(request: Request, pid: int):
    user = require(request, post=True)
    p = db.one("SELECT name, account_id FROM players WHERE id = %s", pid)
    if not p:
        return toast("Jogador não encontrado.", ok=False)
    db.run("DELETE FROM account_bans WHERE account_id = %s", p["account_id"])
    db.audit(user["account"], "unban", p["name"])
    return toast(f"{p['name']} desbanido.")


@app.get("/turma", response_class=HTMLResponse)
def group(request: Request):
    user = require(request)
    kits = db.all("SELECT * FROM cockpit_kits ORDER BY name")
    return page(request, "group.html", user, members=group_players(), kits=kits, effects=gamedata.EFFECTS, outfits=gamedata.outfits(), cats=gamedata.CATEGORIES)


@app.get("/parts/turma", response_class=HTMLResponse)
def part_group(request: Request):
    user = require(request)
    return page(request, "_group_cards.html", user, members=group_players())


@app.get("/jogador/{pid}", response_class=HTMLResponse)
def studio(request: Request, pid: int):
    user = require(request)
    p = db.one(
        "SELECT p.*, o.player_id IS NOT NULL AS online FROM players p LEFT JOIN cockpit_online o ON o.player_id = p.id WHERE p.id = %s", pid
    )
    if not p:
        raise HTTPException(404)
    kits = db.all("SELECT * FROM cockpit_kits ORDER BY name")
    return page(
        request, "studio.html", user, p=p, skills=gamedata.SKILLS, outfits=gamedata.outfits().get(p["sex"], []),
        mounts=gamedata.mounts(), effects=gamedata.EFFECTS, palette=PALETTE, kits=kits, cats=gamedata.CATEGORIES,
    )


@app.get("/itens", response_class=HTMLResponse)
def catalog(request: Request, q: str = "", cat: str = ""):
    user = require(request)
    return page(request, "_catalog.html", user, items=gamedata.search_items(q, cat))


@app.get("/icone/{item_id}.png")
def icon(item_id: int):
    path = os.path.join(ICON_DIR, f"{item_id}.png")
    if os.path.isfile(path):
        return FileResponse(path, headers={"Cache-Control": "public, max-age=604800"})
    return FileResponse(os.path.join(HERE, "static", "no-icon.svg"), media_type="image/svg+xml")


@app.get("/kits", response_class=HTMLResponse)
def kits_page(request: Request):
    user = require(request)
    kits = db.all("SELECT * FROM cockpit_kits ORDER BY name")
    names = gamedata.item_names()
    for k in kits:
        k["list"] = [(int(i), int(c), names.get(int(i), "?")) for i, c in (x.split(":") for x in k["items"].split(",") if x)]
    return page(request, "kits.html", user, kits=kits, cats=gamedata.CATEGORIES)


def _parse_kit(items):
    out = []
    for part in items.split(",")[:40]:
        if ":" not in part:
            continue
        i, c = part.split(":", 1)
        if i.isdigit() and int(i) in gamedata.item_names():
            out.append(f"{int(i)}:{clamp(c, 1, 1000)}")
    return ",".join(out)


@app.post("/kits", response_class=HTMLResponse)
def kit_create(request: Request, nome: str = Form(...), itens: str = Form("")):
    user = require(request, post=True)
    items = _parse_kit(itens)
    if not nome.strip() or not items:
        return toast("Dê um nome e arraste ao menos um item.", ok=False)
    db.run("INSERT INTO cockpit_kits (name, items) VALUES (%s, %s)", nome.strip()[:64], items)
    db.audit(user["account"], "kit_criado", nome.strip()[:64], items)
    return Response(headers={"HX-Redirect": "/kits"})


@app.post("/kits/{kid}/apagar")
def kit_delete(request: Request, kid: int):
    user = require(request, post=True)
    db.run("DELETE FROM cockpit_kits WHERE id = %s", kid)
    db.audit(user["account"], "kit_apagado", str(kid))
    return Response(headers={"HX-Redirect": "/kits"})


@app.get("/historico", response_class=HTMLResponse)
def history(request: Request):
    user = require(request)
    return page(request, "history.html", user, rows=db.all("SELECT * FROM cockpit_audit ORDER BY id DESC LIMIT 200"))


# ---------------------------------------------------------------- the one action endpoint


@app.post("/acao", response_class=HTMLResponse)
async def action(request: Request):
    user = require(request, post=True)
    form = await request.form()
    name = form.get("action", "")
    alvo = str(form.get("alvo", ""))
    text = str(form.get("text", "")).strip()[:500]

    if name in GLOBAL_ACTIONS:
        if GLOBAL_ACTIONS[name].get("text") and not text:
            return toast("Escreva a mensagem.", ok=False)
        db.enqueue(user["account"], name, text=text)
        return toast("Enviado ao servidor.")

    if name == "give_kit":
        kit = db.one("SELECT * FROM cockpit_kits WHERE id = %s", clamp(form.get("arg1"), 0, 10**9))
        if not kit:
            return toast("Kit não encontrado.", ok=False)
        targets = resolve_targets(alvo)
        for t in targets:
            for part in kit["items"].split(","):
                i, c = part.split(":")
                db.enqueue(user["account"], "give_item", t, int(i), int(c))
        return toast(f"{kit['name']} enviado para {len(targets)} jogador(es).")

    spec = ACTIONS.get(name)
    if spec is None:
        return toast("Ação não permitida.", ok=False)
    if spec.get("text") and not text:
        return toast("Escreva a mensagem.", ok=False)
    args = {k: clamp(form.get(k), *spec[k]) if k in spec else 0 for k in ("arg1", "arg2", "arg3", "arg4")}
    if name == "give_item" and args["arg1"] not in gamedata.item_names():
        return toast("Item desconhecido.", ok=False)
    if name == "summon_to":
        text = user["me"]
    if name == "set_outfit":
        text = ",".join(str(clamp(form.get(k), 0, 132)) for k in ("head", "body", "legs", "feet"))

    targets = resolve_targets(alvo)
    if not targets:
        return toast("Ninguém para receber.", ok=False)
    for t in targets:
        db.enqueue(user["account"], name, t, text=text, **args)
    label = targets[0] if len(targets) == 1 else f"{len(targets)} jogadores"
    offline = [t for t in targets if t not in online_names()]
    note = " Quem está offline recebe ao logar." if offline and name not in ("kick", "heal", "temple", "summon_to", "effect", "say_over") else ""
    return toast(f"Enviado para {label}.{note}")


# ---------------------------------------------------------------- accounts and characters

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z ']{1,27}[A-Za-z]$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")
GROUPS = [(1, "Jogador"), (2, "Tutor"), (3, "Senior tutor"), (4, "Gamemaster"), (5, "Community manager"), (6, "God")]
# Starting stats for a new level 8 character, same as the Canary sample characters.
NEW_CHAR = {"level": 8, "experience": 4200, "health": 185, "mana": 90, "cap": 470}


def sha1(text):
    return hashlib.sha1(text.encode()).hexdigest()


def towns():
    return db.all("SELECT id, name FROM towns ORDER BY name") or [{"id": 8, "name": "Thais"}]


def is_online(pid):
    return bool(db.one("SELECT 1 AS x FROM cockpit_online WHERE player_id = %s", pid))


def create_character(account_id, name, sex, vocation, town):
    name = " ".join(name.split())
    if not NAME_RE.match(name):
        return "Nome inválido: use de 3 a 29 letras e espaços."
    if db.one("SELECT 1 AS x FROM players WHERE name = %s", name):
        return f"Já existe um personagem chamado {name}."
    sex = 1 if int(sex) else 0
    db.run(
        "INSERT INTO players (name, group_id, account_id, level, vocation, health, healthmax, experience, "
        "lookbody, lookfeet, lookhead, looklegs, looktype, mana, manamax, town_id, conditions, cap, sex) "
        "VALUES (%s, 1, %s, %s, %s, %s, %s, %s, 106, 95, 78, 116, %s, %s, %s, %s, '', %s, %s)",
        name, account_id, NEW_CHAR["level"], clamp(vocation, 0, 4), NEW_CHAR["health"], NEW_CHAR["health"], NEW_CHAR["experience"],
        128 if sex else 136, NEW_CHAR["mana"], NEW_CHAR["mana"], clamp(town, 1, 1000), NEW_CHAR["cap"], sex,
    )
    return None


@app.get("/contas", response_class=HTMLResponse)
def accounts(request: Request, q: str = ""):
    user = require(request)
    rows = db.all(
        "SELECT a.id, a.name, a.email, a.coins, a.coins_transferable, a.premdays, a.lastday, "
        "(SELECT COUNT(*) FROM players p WHERE p.account_id = a.id) AS chars, "
        "(SELECT GROUP_CONCAT(p.name ORDER BY p.name SEPARATOR ', ') FROM players p WHERE p.account_id = a.id) AS names "
        "FROM accounts a WHERE a.name LIKE %s OR a.email LIKE %s ORDER BY a.id DESC LIMIT 100",
        f"%{q}%", f"%{q}%",
    )
    purchases = db.all(
        "SELECT h.*, a.name AS account FROM store_history h JOIN accounts a ON a.id = h.account_id ORDER BY h.id DESC LIMIT 15"
    )
    return page(request, "accounts.html", user, rows=rows, q=q, towns=towns(), vocations_list=list(gamedata.vocations().items())[:5], purchases=purchases)


@app.post("/contas", response_class=HTMLResponse)
def account_create(
    request: Request, nome: str = Form(...), email: str = Form(...), senha: str = Form(...),
    personagem: str = Form(""), sexo: int = Form(1), vocacao: int = Form(4), cidade: int = Form(8),
):
    user = require(request, post=True)
    nome, email = nome.strip(), email.strip()
    if not re.match(r"^[A-Za-z0-9_]{3,32}$", nome):
        return toast("Nome da conta: 3 a 32 letras, números ou _.", ok=False)
    if not EMAIL_RE.match(email):
        return toast("E-mail inválido.", ok=False)
    if len(senha) < 6:
        return toast("A senha precisa de pelo menos 6 caracteres.", ok=False)
    if db.one("SELECT 1 AS x FROM accounts WHERE name = %s OR email = %s", nome, email):
        return toast("Já existe conta com esse nome ou e-mail.", ok=False)
    acc = db.run(
        "INSERT INTO accounts (name, email, password, type, creation) VALUES (%s, %s, %s, 1, %s)", nome, email, sha1(senha), int(time.time())
    )
    db.audit(user["account"], "conta_criada", nome, email)
    if personagem.strip():
        err = create_character(acc, personagem, sexo, vocacao, cidade)
        if err:
            return toast(f"Conta criada, mas o personagem não: {err}", ok=False)
        db.audit(user["account"], "personagem_criado", personagem.strip(), nome)
    return Response(headers={"HX-Redirect": f"/conta/{acc}"})


@app.get("/conta/{aid}", response_class=HTMLResponse)
def account_detail(request: Request, aid: int):
    user = require(request)
    acc = db.one("SELECT * FROM accounts WHERE id = %s", aid)
    if not acc:
        raise HTTPException(404)
    chars = db.all(
        "SELECT p.id, p.name, p.level, p.vocation, p.group_id, p.town_id, o.player_id IS NOT NULL AS online "
        "FROM players p LEFT JOIN cockpit_online o ON o.player_id = p.id WHERE p.account_id = %s ORDER BY p.name", aid,
    )
    premium = max(0, (acc["lastday"] - int(time.time()) + 86399) // 86400) if acc["lastday"] else 0
    purchases = db.all("SELECT * FROM store_history WHERE account_id = %s ORDER BY id DESC LIMIT 20", aid)
    coin_log = db.all("SELECT * FROM coins_transactions WHERE account_id = %s ORDER BY id DESC LIMIT 20", aid)
    return page(
        request, "account.html", user, acc=acc, chars=chars, premium=premium, groups=GROUPS, towns=towns(),
        vocations_list=list(gamedata.vocations().items())[:5], purchases=purchases, coin_log=coin_log,
    )


@app.post("/conta/{aid}/senha", response_class=HTMLResponse)
def account_password(request: Request, aid: int, senha: str = Form(...)):
    user = require(request, post=True)
    if len(senha) < 6:
        return toast("A senha precisa de pelo menos 6 caracteres.", ok=False)
    db.run("UPDATE accounts SET password = %s WHERE id = %s", sha1(senha), aid)
    db.audit(user["account"], "senha_trocada", str(aid))
    return toast("Senha trocada. Vale para o jogo e para o painel.")


@app.post("/conta/{aid}/premium", response_class=HTMLResponse)
def account_premium(request: Request, aid: int, dias: int = Form(...)):
    user = require(request, post=True)
    acc = db.one("SELECT lastday FROM accounts WHERE id = %s", aid)
    now = int(time.time())
    left = max(0, acc["lastday"] - now) if acc and acc["lastday"] else 0
    total = max(0, left + clamp(dias, -3650, 3650) * 86400)
    db.run("UPDATE accounts SET premdays = %s, lastday = %s WHERE id = %s", total // 86400, now + total if total else 0, aid)
    db.audit(user["account"], "premium", str(aid), f"{dias} dias")
    return toast(f"Premium agora: {total // 86400} dias. Se o jogador estiver online, vale depois de relogar.")


@app.post("/conta/{aid}/coins", response_class=HTMLResponse)
def account_coins(request: Request, aid: int, quantidade: int = Form(...), tipo: str = Form("coins")):
    """Tibia coins live only in the database (the server re-reads them on every use), so this is safe online too."""
    user = require(request, post=True)
    col, coin_type = ("coins_transferable", 3) if tipo == "transferable" else ("coins", 1)
    amount = clamp(quantidade, -1000000, 1000000)
    if amount == 0:
        return toast("Quantidade zero.", ok=False)
    db.run(f"UPDATE accounts SET {col} = GREATEST(0, CAST({col} AS SIGNED) + %s) WHERE id = %s", amount, aid)
    db.run(
        "INSERT INTO coins_transactions (account_id, type, coin_type, amount, description) VALUES (%s, %s, %s, %s, %s)",
        aid, 1 if amount > 0 else 2, coin_type, abs(amount), "Cockpit: " + user["account"],
    )
    db.audit(user["account"], "coins", str(aid), f"{amount} {col}")
    acc = db.one(f"SELECT {col} AS c FROM accounts WHERE id = %s", aid)
    return toast(f"Saldo agora: {acc['c']} {'coins transferíveis' if coin_type == 3 else 'Tibia coins'}.")


@app.post("/conta/{aid}/apagar", response_class=HTMLResponse)
def account_delete(request: Request, aid: int):
    user = require(request, post=True)
    if db.one("SELECT 1 AS x FROM players WHERE account_id = %s AND group_id >= %s", aid, GOD_GROUP):
        return toast("Conta com personagem God não pode ser apagada pelo painel.", ok=False)
    if db.one("SELECT 1 AS x FROM players p JOIN cockpit_online o ON o.player_id = p.id WHERE p.account_id = %s", aid):
        return toast("Tem personagem dessa conta online. Kicke antes.", ok=False)
    acc = db.one("SELECT name FROM accounts WHERE id = %s", aid)
    db.run("DELETE FROM cockpit_group WHERE player_id IN (SELECT id FROM players WHERE account_id = %s)", aid)
    db.run("DELETE FROM accounts WHERE id = %s", aid)
    db.audit(user["account"], "conta_apagada", acc["name"] if acc else str(aid))
    return Response(headers={"HX-Redirect": "/contas"})


@app.post("/conta/{aid}/personagem", response_class=HTMLResponse)
def character_create(request: Request, aid: int, nome: str = Form(...), sexo: int = Form(1), vocacao: int = Form(4), cidade: int = Form(8)):
    user = require(request, post=True)
    if not db.one("SELECT 1 AS x FROM accounts WHERE id = %s", aid):
        return toast("Conta não encontrada.", ok=False)
    err = create_character(aid, nome, sexo, vocacao, cidade)
    if err:
        return toast(err, ok=False)
    db.audit(user["account"], "personagem_criado", nome.strip(), str(aid))
    return Response(headers={"HX-Redirect": f"/conta/{aid}"})


@app.post("/jogador/{pid}/apagar", response_class=HTMLResponse)
def character_delete(request: Request, pid: int):
    user = require(request, post=True)
    p = db.one("SELECT name, account_id, group_id FROM players WHERE id = %s", pid)
    if not p:
        return toast("Personagem não encontrado.", ok=False)
    if p["group_id"] >= GOD_GROUP:
        return toast("Personagem God não pode ser apagado pelo painel.", ok=False)
    if is_online(pid):
        return toast(f"{p['name']} está online. Kicke antes de apagar.", ok=False)
    db.run("DELETE FROM cockpit_group WHERE player_id = %s", pid)
    db.run("DELETE FROM players WHERE id = %s", pid)
    db.audit(user["account"], "personagem_apagado", p["name"])
    return Response(headers={"HX-Redirect": f"/conta/{p['account_id']}"})


@app.post("/jogador/{pid}/renomear", response_class=HTMLResponse)
def character_rename(request: Request, pid: int, nome: str = Form(...)):
    user = require(request, post=True)
    p = db.one("SELECT name, account_id FROM players WHERE id = %s", pid)
    nome = " ".join(nome.split())
    if not p:
        return toast("Personagem não encontrado.", ok=False)
    if is_online(pid):
        return toast(f"{p['name']} está online. Kicke antes de renomear.", ok=False)
    if not NAME_RE.match(nome):
        return toast("Nome inválido: use de 3 a 29 letras e espaços.", ok=False)
    if db.one("SELECT 1 AS x FROM players WHERE name = %s AND id <> %s", nome, pid):
        return toast(f"Já existe um personagem chamado {nome}.", ok=False)
    db.run("UPDATE players SET name = %s WHERE id = %s", nome, pid)
    db.audit(user["account"], "personagem_renomeado", p["name"], nome)
    return Response(headers={"HX-Redirect": f"/conta/{p['account_id']}"})


@app.post("/jogador/{pid}/grupo", response_class=HTMLResponse)
def character_group(request: Request, pid: int, grupo: int = Form(...)):
    user = require(request, post=True)
    p = db.one("SELECT name FROM players WHERE id = %s", pid)
    if not p:
        return toast("Personagem não encontrado.", ok=False)
    grupo = clamp(grupo, 1, 6)
    if p["name"] == user["me"] and grupo < GOD_GROUP:
        return toast("Você não pode tirar o God do seu próprio personagem por aqui.", ok=False)
    if is_online(pid):
        db.enqueue(user["account"], "set_group", p["name"], grupo)
    else:
        db.run("UPDATE players SET group_id = %s WHERE id = %s", grupo, pid)
        db.audit(user["account"], "grupo", p["name"], str(grupo))
    return toast(f"{p['name']} agora é {dict(GROUPS)[grupo]}.")


# ---------------------------------------------------------------- metrics and logs


@app.get("/metricas", response_class=HTMLResponse)
def metrics(request: Request):
    user = require(request)
    return page(request, "metrics.html", user)


@app.get("/parts/metricas", response_class=HTMLResponse)
def part_metrics(request: Request):
    user = require(request)
    since = int(time.time()) - 86400
    rows = db.all("SELECT ts, players, monsters, npcs, lua_kb, started_at FROM cockpit_metrics WHERE ts >= %s ORDER BY ts", since)
    last = rows[-1] if rows else None
    counts = db.one(
        "SELECT (SELECT COUNT(*) FROM accounts) AS accounts, (SELECT COUNT(*) FROM players) AS players, "
        "(SELECT COALESCE(SUM(data_length + index_length), 0) FROM information_schema.tables WHERE table_schema = DATABASE()) AS db_size"
    )
    online = db.one("SELECT COUNT(*) AS n, MAX(updated_at) AS t FROM cockpit_online")
    return page(
        request, "_metrics.html", user, host=system.host(), services=system.services(), last=last, counts=counts, online=online,
        spark=system.sparkline([r["players"] for r in rows]), peak=max((r["players"] for r in rows), default=0),
        spark_monsters=system.sparkline([r["monsters"] for r in rows]),
    )


@app.get("/logs", response_class=HTMLResponse)
def logs(request: Request):
    user = require(request)
    return page(request, "logs.html", user, dirs=system.log_files())


@app.get("/logs/ver", response_class=HTMLResponse)
def log_view(request: Request, pasta: str, arquivo: str, linhas: int = 500, filtro: str = ""):
    user = require(request)
    path = system.log_path(pasta, arquivo)
    if not path:
        raise HTTPException(404)
    rows = [(line, system.level(line)) for line in system.tail(path, linhas, filtro)]
    name = "_log_lines.html" if request.headers.get("HX-Request") else "log_view.html"
    return page(request, name, user, rows=rows, pasta=pasta, arquivo=arquivo, linhas=linhas, filtro=filtro)


@app.get("/logs/baixar")
def log_download(request: Request, pasta: str, arquivo: str):
    require(request)
    path = system.log_path(pasta, arquivo)
    if not path:
        raise HTTPException(404)
    return FileResponse(path, filename=arquivo, media_type="text/plain")
