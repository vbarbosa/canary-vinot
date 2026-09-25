"""VinOT portal: the public site (landing, news from the Sanity CMS) and the player area
(create account with e-mail confirmation, log in, account details, characters, password).

It shares only the database with the game and the Cockpit. Accounts are written exactly the way
Canary expects them (SHA-1 password, e-mail as the login), so the game client logs in with them.
"""

import datetime as dt
import json
import logging
import os
import re
import secrets
import socket
import threading
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import cms, db, mailer
from . import security as sec

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("portal")

HERE = os.path.dirname(__file__)
BASE_URL = os.environ.get("PORTAL_BASE_URL", "http://localhost:8091").rstrip("/")
HTTPS = BASE_URL.startswith("https://")
DEV = os.environ.get("PORTAL_DEV", "0") == "1"
TZ = ZoneInfo(os.environ.get("PORTAL_TZ", "America/Sao_Paulo"))
MAX_CHARS = int(os.environ.get("PORTAL_MAX_CHARS", "5"))
START_TOWN = int(os.environ.get("PORTAL_TOWN_ID", "8"))  # Thais
GAME_HOST = os.environ.get("PORTAL_GAME_HOST", "server")
GAME_PORT = int(os.environ.get("PORTAL_GAME_PORT", "7172"))
SIGNUP_HOURS = 24
RESET_MINUTES = 60
TURNSTILE_SITE = os.environ.get("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET_KEY", "")

VOCATIONS = {1: "Sorcerer", 2: "Druid", 3: "Paladin", 4: "Knight"}
VOCATION_NAMES = {0: "Sem vocação", 1: "Sorcerer", 2: "Druid", 3: "Paladin", 4: "Knight",
                  5: "Master Sorcerer", 6: "Elder Druid", 7: "Royal Paladin", 8: "Elite Knight"}
VOCATION_ART = {1: "staff", 2: "druid", 3: "bow", 4: "sword", 5: "staff", 6: "druid", 7: "bow", 8: "sword"}
VOCATION_BLURB = {
    1: "Mestre do fogo e da energia. Frágil, mas derruba tudo de longe.",
    2: "Cura a turma e congela os inimigos. Todo grupo quer um.",
    3: "Arqueiro certeiro que equilibra ataque e defesa.",
    4: "Linha de frente: aguenta a pancada pra turma brilhar.",
}
# Starting stats of a level 8 character, same as the Cockpit and the Canary sample characters.
NEW_CHAR = {"level": 8, "experience": 4200, "health": 185, "mana": 90, "cap": 470}
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z ']{1,27}[A-Za-z]$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
RESERVED = re.compile(r"\b(gm|god|cm|admin|adm|tutor|staff|support|suporte|gamemaster|vinicius)\b", re.I)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("PORTAL_SECRET") or secrets.token_hex(32),
    max_age=14 * 24 * 3600,
    same_site="lax",
    https_only=HTTPS,
    session_cookie="vinot",
)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))

login_ip = sec.Limiter(10, 600)
login_email = sec.Limiter(5, 600)
signup_ip = sec.Limiter(5, 3600)
signup_all = sec.Limiter(int(os.environ.get("PORTAL_SIGNUPS_PER_HOUR", "60")), 3600)
mail_ip = sec.Limiter(5, 3600)
create_lock = threading.Lock()


def fmt_date(value, with_time=False):
    if not value:
        return ""
    if isinstance(value, (int, float)):
        d = dt.datetime.fromtimestamp(value, TZ)
    else:
        try:
            d = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(TZ)
        except ValueError:
            return ""
    months = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    out = f"{d.day} {months[d.month - 1]} {d.year}"
    return out + (f", {d:%H:%M}" if with_time else "")


templates.env.filters.update(date=fmt_date, img=cms.image_url, pt=cms.render)
templates.env.globals.update(
    categories=cms.CATEGORIES, vocation_names=VOCATION_NAMES, vocation_art=VOCATION_ART,
    turnstile_site=TURNSTILE_SITE, year=lambda: dt.datetime.now(TZ).year,
)


@app.on_event("startup")
def startup():
    try:
        db.init_schema()
    except Exception as exc:
        log.error("could not prepare the database: %s", exc)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    return sec.headers(response, turnstile=bool(TURNSTILE_SITE))


# ---------------------------------------------------------------- helpers


def current_account(request):
    s = request.session
    if not s.get("acc"):
        return None
    acc = db.one("SELECT id, name, email, password FROM accounts WHERE id = %s", s["acc"])
    if not acc or sec.fingerprint(acc["password"]) != s.get("fp"):
        s.pop("acc", None)
        s.pop("fp", None)
        return None
    return acc


def log_in(request, acc):
    csrf = secrets.token_urlsafe(24)
    request.session.clear()
    request.session.update(acc=acc["id"], fp=sec.fingerprint(acc["password"]), csrf=csrf)


def page(request, name, status_code=200, **ctx):
    ctx.setdefault("site", cms.settings())
    ctx.setdefault("me", _me(request))
    ctx["csrf"] = sec.csrf_token(request.session)
    ctx["path"] = request.url.path
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _me(request):
    try:
        return current_account(request)
    except Exception:
        return None


def redirect(url):
    return RedirectResponse(url, status_code=303)


def flash(request, msg, kind="ok"):
    request.session["flash"] = [kind, msg]


def pop_flash(request):
    return request.session.pop("flash", None)


def bad_csrf(request, token):
    return not sec.csrf_ok(request.session, token)


def turnstile_ok(token, ip):
    if not TURNSTILE_SECRET:
        return True
    data = urllib.parse.urlencode({"secret": TURNSTILE_SECRET, "response": token or "", "remoteip": ip}).encode()
    try:
        with urllib.request.urlopen("https://challenges.cloudflare.com/turnstile/v0/siteverify", data, timeout=5) as r:
            return bool(json.loads(r.read()).get("success"))
    except Exception as exc:
        log.warning("turnstile check failed: %s", exc)
        return False


def clean_name(name):
    return " ".join((name or "").split()).title().replace("'S ", "'s ")


def name_problem(name):
    if not NAME_RE.match(name):
        return "O nome do personagem precisa ter de 3 a 29 letras (pode ter espaço e apóstrofo)."
    if RESERVED.search(name):
        return "Esse nome é reservado. Escolha outro."
    if any(len(w) < 2 for w in name.split()):
        return "Cada palavra do nome precisa ter pelo menos 2 letras."
    if db.one("SELECT 1 AS x FROM players WHERE name = %s", name):
        return f"Já existe um personagem chamado {name}."
    return None


def create_character(account_id, name, sex, vocation):
    db.run(
        "INSERT INTO players (name, group_id, account_id, level, vocation, health, healthmax, experience, "
        "lookbody, lookfeet, lookhead, looklegs, looktype, mana, manamax, town_id, conditions, cap, sex) "
        "VALUES (%s, 1, %s, %s, %s, %s, %s, %s, 106, 95, 78, 116, %s, %s, %s, %s, '', %s, %s)",
        name, account_id, NEW_CHAR["level"], vocation, NEW_CHAR["health"], NEW_CHAR["health"], NEW_CHAR["experience"],
        128 if sex else 136, NEW_CHAR["mana"], NEW_CHAR["mana"], START_TOWN, NEW_CHAR["cap"], 1 if sex else 0,
    )


def account_name_for(email):
    """accounts.name must be unique; the game logs in by e-mail, so this is only an internal label."""
    base = re.sub(r"[^a-z0-9]", "", email.split("@")[0].lower())[:20] or "conta"
    for _ in range(20):
        name = f"{base}{secrets.randbelow(10000):04d}"
        if not db.one("SELECT 1 AS x FROM accounts WHERE name = %s", name):
            return name
    return secrets.token_hex(8)


def new_token(kind, email, payload, ttl, ip):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    db.run("DELETE FROM portal_tokens WHERE (kind = %s AND email = %s) OR expires_at < %s", kind, email, now)
    db.run(
        "INSERT INTO portal_tokens (token_hash, kind, email, payload, created_at, expires_at, last_sent, ip) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        sec.token_hash(token), kind, email, json.dumps(payload), now, now + ttl, now, ip,
    )
    return token


def find_token(kind, token):
    if not token or len(token) > 100:
        return None
    return db.one(
        "SELECT * FROM portal_tokens WHERE token_hash = %s AND kind = %s AND expires_at >= %s",
        sec.token_hash(token), kind, int(time.time()),
    )


def email_html(title, lines, button, url):
    body = "".join(f'<p style="margin:0 0 14px">{line}</p>' for line in lines)
    return f"""<!doctype html><html><body style="margin:0;background:#15130f;padding:24px;font-family:Arial,sans-serif;color:#f2e6c9">
<table role="presentation" width="100%" style="max-width:520px;margin:auto;background:#1f1b14;border:3px solid #d9a441;border-radius:6px">
<tr><td style="padding:24px 28px">
<img src="{BASE_URL}/static/apple-touch-icon.png" width="60" height="60" alt="VinOT" style="image-rendering:pixelated">
<h1 style="color:#f3d27a;font-size:22px;margin:12px 0 16px">{title}</h1>{body}
<p style="margin:22px 0"><a href="{url}" style="background:#d9a441;color:#15130f;padding:12px 20px;text-decoration:none;font-weight:bold;border-radius:4px">{button}</a></p>
<p style="font-size:12px;color:#9a8f7c">Se o botão não funcionar, copie este link no navegador:<br>{url}</p>
<p style="font-size:12px;color:#9a8f7c">Se não foi você, ignore este e-mail.</p>
</td></tr></table></body></html>"""


def send_confirmation(email, token):
    url = f"{BASE_URL}/confirmar?t={token}"
    text = (
        "Falta pouco pra entrar no VinOT!\n\n"
        f"Confirme seu e-mail abrindo o link abaixo (vale por {SIGNUP_HOURS} horas):\n{url}\n\n"
        "Se não foi você que se cadastrou, ignore este e-mail."
    )
    html_body = email_html("Confirme sua conta", ["Falta pouco pra entrar no VinOT!",
                           f"Clique no botão pra confirmar seu e-mail. O link vale por {SIGNUP_HOURS} horas."], "Confirmar e-mail", url)
    mailer.send(email, "Confirme sua conta no VinOT", text, html_body)
    return url


def send_reset(email, token):
    url = f"{BASE_URL}/redefinir?t={token}"
    text = f"Pra criar uma senha nova no VinOT, abra o link abaixo (vale por {RESET_MINUTES} minutos):\n{url}\n\nSe não foi você, ignore este e-mail."
    html_body = email_html("Nova senha", [f"Recebemos um pedido pra trocar a senha da sua conta. O link vale por {RESET_MINUTES} minutos."], "Criar nova senha", url)
    mailer.send(email, "Trocar a senha do VinOT", text, html_body)
    return url


_status = {"at": 0, "up": False}


def game_up():
    now = time.time()
    if now - _status["at"] > 30:
        try:
            with socket.create_connection((GAME_HOST, GAME_PORT), timeout=0.6):
                _status["up"] = True
        except OSError:
            _status["up"] = False
        _status["at"] = now
    return _status["up"]


def stats():
    try:
        online = db.one("SELECT COUNT(*) AS n FROM players_online")["n"]
        record = db.one("SELECT value FROM server_config WHERE config = 'players_record'")
        chars = db.one("SELECT COUNT(*) AS n FROM players WHERE group_id = 1 AND deletion = 0")["n"]
        return {"online": online, "record": int(record["value"]) if record else 0, "chars": chars, "up": game_up()}
    except Exception as exc:
        log.warning("stats unavailable: %s", exc)
        return None


def top_players(limit=5):
    try:
        return db.all(
            "SELECT name, level, vocation FROM players WHERE group_id = 1 AND deletion = 0 AND name NOT LIKE %s "
            "ORDER BY level DESC, experience DESC LIMIT %s", "% Sample", limit,
        )
    except Exception:
        return []


# ---------------------------------------------------------------- public pages


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return page(
        request, "index.html", home=cms.home(), posts=cms.posts(limit=3), promos=cms.promotions(),
        stats=stats(), top=top_players(), vocations=VOCATIONS, blurbs=VOCATION_BLURB, flash=pop_flash(request),
    )


@app.get("/noticias", response_class=HTMLResponse)
def news(request: Request, categoria: str = ""):
    cat = categoria if categoria in cms.CATEGORIES else ""
    return page(request, "news.html", posts=cms.posts(limit=30, category=cat), cat=cat)


@app.get("/noticias/{slug}", response_class=HTMLResponse)
def news_post(request: Request, slug: str):
    post = cms.post(slug[:120])
    if not post:
        return page(request, "404.html", status_code=404)
    return page(request, "post.html", post=post)


@app.get("/ranking", response_class=HTMLResponse)
def ranking(request: Request):
    return page(request, "ranking.html", top=top_players(50))


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return "User-agent: *\nDisallow: /conta\nDisallow: /confirmar\nDisallow: /redefinir\n"


# ---------------------------------------------------------------- sign up


def signup_page(request, errors=None, form=None, status_code=200):
    return page(request, "signup.html", status_code=status_code, errors=errors or {}, form=form or {},
                vocations=VOCATIONS, blurbs=VOCATION_BLURB)


@app.get("/criar-conta", response_class=HTMLResponse)
def signup_form(request: Request):
    if _me(request):
        return redirect("/conta")
    return signup_page(request)


@app.post("/criar-conta", response_class=HTMLResponse)
def signup(
    request: Request, email: str = Form(""), email2: str = Form(""), senha: str = Form(""), senha2: str = Form(""),
    personagem: str = Form(""), sexo: str = Form("1"), vocacao: str = Form("4"), regras: str = Form(""),
    novidades: str = Form(""), site: str = Form(""), csrf: str = Form(""),
    cf_turnstile_response: str = Form("", alias="cf-turnstile-response"),
):
    ip = sec.client_ip(request)
    email, email2 = email.strip().lower(), email2.strip().lower()
    name = clean_name(personagem)
    form = {"email": email, "email2": email2, "personagem": name, "sexo": sexo, "vocacao": vocacao, "novidades": novidades}
    if bad_csrf(request, csrf):
        return signup_page(request, {"geral": "A página expirou. Tente de novo."}, form, 400)
    if site:  # honeypot field, invisible to people
        return page(request, "check_email.html", email=email, dev_link=None)
    if signup_ip.blocked(ip) or signup_all.blocked("all"):
        return signup_page(request, {"geral": "Muitos cadastros agora. Tente de novo mais tarde."}, form, 429)

    errors = {}
    if not EMAIL_RE.match(email) or len(email) > 255:
        errors["email"] = "Digite um e-mail válido."
    elif email != email2:
        errors["email2"] = "Os e-mails não são iguais."
    elif db.one("SELECT 1 AS x FROM accounts WHERE email = %s", email):
        errors["email"] = "Já existe uma conta com esse e-mail. Quer entrar ou recuperar a senha?"
    problem = sec.password_problem(senha, email)
    if problem:
        errors["senha"] = problem
    elif senha != senha2:
        errors["senha2"] = "As senhas não são iguais."
    problem = name_problem(name)
    if problem:
        errors["personagem"] = problem
    try:
        voc = int(vocacao)
    except ValueError:
        voc = 0
    if voc not in VOCATIONS:
        errors["vocacao"] = "Escolha uma vocação."
    if sexo not in ("0", "1"):
        errors["sexo"] = "Escolha o sexo do personagem."
    if not regras:
        errors["regras"] = "Você precisa aceitar as regras pra jogar."
    if not errors and not turnstile_ok(cf_turnstile_response, ip):
        errors["geral"] = "Não consegui confirmar que você é humano. Tente de novo."
    if errors:
        return signup_page(request, errors, form, 422)

    signup_ip.hit(ip)
    signup_all.hit("all")
    payload = {"pw": sec.sha1(senha), "name": name, "sex": int(sexo), "voc": voc, "news": bool(novidades)}
    token = new_token("signup", email, payload, SIGNUP_HOURS * 3600, ip)
    link = send_confirmation(email, token)
    request.session["pending"] = email
    return page(request, "check_email.html", email=email, dev_link=link if DEV else None)


@app.post("/reenviar", response_class=HTMLResponse)
def resend(request: Request, email: str = Form(""), csrf: str = Form("")):
    ip = sec.client_ip(request)
    email = email.strip().lower()
    if bad_csrf(request, csrf) or mail_ip.blocked(ip):
        return page(request, "check_email.html", email=email, dev_link=None, note="Espere um pouco antes de pedir de novo.")
    mail_ip.hit(ip)
    row = db.one("SELECT * FROM portal_tokens WHERE kind = 'signup' AND email = %s AND expires_at >= %s", email, int(time.time()))
    link = None
    if row and row["last_sent"] < time.time() - 60 and row["sent_count"] < 5:
        # New token each time; the old link stops working.
        token = new_token("signup", email, json.loads(row["payload"]), SIGNUP_HOURS * 3600, ip)
        db.run("UPDATE portal_tokens SET sent_count = %s WHERE token_hash = %s", row["sent_count"] + 1, sec.token_hash(token))
        link = send_confirmation(email, token)
    return page(request, "check_email.html", email=email, dev_link=link if DEV else None,
                note="Se o cadastro estiver pendente, mandamos o link de novo. Olhe também o spam.")


@app.get("/confirmar", response_class=HTMLResponse)
def confirm(request: Request, t: str = ""):
    row = find_token("signup", t)
    if not row:
        return page(request, "message.html", status_code=400, title="Link inválido ou vencido",
                    text="Esse link de confirmação não vale mais. Faça o cadastro de novo, é rapidinho.",
                    link=("/criar-conta", "Criar conta"))
    data = json.loads(row["payload"])
    with create_lock:
        db.run("DELETE FROM portal_tokens WHERE token_hash = %s", row["token_hash"])
        if db.one("SELECT 1 AS x FROM accounts WHERE email = %s", row["email"]):
            return page(request, "message.html", title="Conta já confirmada",
                        text="Esse e-mail já tem uma conta. É só entrar.", link=("/entrar", "Entrar"))
        acc_id = db.run(
            "INSERT INTO accounts (name, email, password, type, creation) VALUES (%s, %s, %s, 1, %s)",
            account_name_for(row["email"]), row["email"], data["pw"], int(time.time()),
        )
        char_ok = not name_problem(data["name"])
        if char_ok:
            create_character(acc_id, data["name"], data["sex"], data["voc"])
    log.info("account %s confirmed (%s)", acc_id, row["email"])
    acc = db.one("SELECT id, name, email, password FROM accounts WHERE id = %s", acc_id)
    log_in(request, acc)
    if char_ok:
        flash(request, f"Conta confirmada! {data['name']} já está te esperando em Thais.")
    else:
        flash(request, f"Conta confirmada! Alguém pegou o nome {data['name']} antes, então crie seu personagem aqui embaixo.", "warn")
    return redirect("/conta")


# ---------------------------------------------------------------- log in / out


@app.get("/entrar", response_class=HTMLResponse)
def login_form(request: Request):
    if _me(request):
        return redirect("/conta")
    return page(request, "login.html", error=None, email="", flash=pop_flash(request))


@app.post("/entrar", response_class=HTMLResponse)
def login(request: Request, email: str = Form(""), senha: str = Form(""), csrf: str = Form("")):
    ip = sec.client_ip(request)
    email = email.strip().lower()
    if bad_csrf(request, csrf):
        return page(request, "login.html", status_code=400, error="A página expirou. Tente de novo.", email=email)
    if login_ip.blocked(ip) or login_email.blocked(email):
        return page(request, "login.html", status_code=429, error="Muitas tentativas. Espere 10 minutos.", email=email)
    acc = db.one("SELECT id, name, email, password FROM accounts WHERE email = %s LIMIT 1", email)
    if not acc or not sec.password_ok(acc["password"], senha):
        login_ip.hit(ip)
        login_email.hit(email)
        pending = db.one("SELECT 1 AS x FROM portal_tokens WHERE kind = 'signup' AND email = %s AND expires_at >= %s", email, int(time.time()))
        if pending and not acc:
            return page(request, "check_email.html", email=email, dev_link=None,
                        note="Essa conta ainda não foi confirmada. Abra o link que mandamos pro seu e-mail.")
        return page(request, "login.html", status_code=401, error="E-mail ou senha incorretos.", email=email)
    log_in(request, acc)
    return redirect("/conta")


@app.post("/sair")
def logout(request: Request, csrf: str = Form("")):
    if not bad_csrf(request, csrf):
        request.session.clear()
    return redirect("/")


# ---------------------------------------------------------------- password reset


@app.get("/esqueci", response_class=HTMLResponse)
def forgot_form(request: Request):
    return page(request, "forgot.html", sent=False, dev_link=None)


@app.post("/esqueci", response_class=HTMLResponse)
def forgot(request: Request, email: str = Form(""), csrf: str = Form("")):
    ip = sec.client_ip(request)
    email = email.strip().lower()
    link = None
    if not bad_csrf(request, csrf) and not mail_ip.blocked(ip) and EMAIL_RE.match(email):
        mail_ip.hit(ip)
        acc = db.one("SELECT id FROM accounts WHERE email = %s", email)
        if acc:
            link = send_reset(email, new_token("reset", email, {"acc": acc["id"]}, RESET_MINUTES * 60, ip))
    # Same answer either way, so the page can't be used to find out who has an account.
    return page(request, "forgot.html", sent=True, dev_link=link if DEV else None)


@app.get("/redefinir", response_class=HTMLResponse)
def reset_form(request: Request, t: str = ""):
    if not find_token("reset", t):
        return page(request, "message.html", status_code=400, title="Link inválido ou vencido",
                    text="Peça um link novo pra trocar a senha.", link=("/esqueci", "Pedir outro link"))
    return page(request, "reset.html", token=t, error=None)


@app.post("/redefinir", response_class=HTMLResponse)
def reset(request: Request, t: str = Form(""), senha: str = Form(""), senha2: str = Form(""), csrf: str = Form("")):
    row = find_token("reset", t)
    if not row:
        return page(request, "message.html", status_code=400, title="Link inválido ou vencido",
                    text="Peça um link novo pra trocar a senha.", link=("/esqueci", "Pedir outro link"))
    problem = "A página expirou. Tente de novo." if bad_csrf(request, csrf) else sec.password_problem(senha, row["email"])
    if not problem and senha != senha2:
        problem = "As senhas não são iguais."
    if problem:
        return page(request, "reset.html", status_code=422, token=t, error=problem)
    acc_id = json.loads(row["payload"])["acc"]
    db.run("UPDATE accounts SET password = %s WHERE id = %s", sec.sha1(senha), acc_id)
    db.run("DELETE FROM portal_tokens WHERE kind = 'reset' AND email = %s", row["email"])
    request.session.clear()
    flash(request, "Senha trocada! Entre com a senha nova.")
    return redirect("/entrar")


# ---------------------------------------------------------------- player area


def load_account(acc_id):
    acc = db.one(
        "SELECT id, email, premdays, lastday, coins, coins_transferable, tournament_coins, creation, type FROM accounts WHERE id = %s", acc_id,
    )
    chars = db.all(
        "SELECT p.id, p.name, p.level, p.vocation, p.sex, p.looktype, p.lastlogin, p.onlinetime, p.balance, p.town_id, "
        "t.name AS town, o.player_id IS NOT NULL AS online "
        "FROM players p LEFT JOIN towns t ON t.id = p.town_id LEFT JOIN players_online o ON o.player_id = p.id "
        "WHERE p.account_id = %s AND p.deletion = 0 ORDER BY p.level DESC, p.name", acc_id,
    )
    return acc, chars


@app.get("/conta", response_class=HTMLResponse)
def account(request: Request):
    me = current_account(request)
    if not me:
        return redirect("/entrar")
    acc, chars = load_account(me["id"])
    premium_until = acc["lastday"] if acc["lastday"] and acc["lastday"] > time.time() else 0
    return page(
        request, "account.html", me=me, acc=acc, chars=chars, premium_until=premium_until, vocations=VOCATIONS,
        max_chars=MAX_CHARS, flash=pop_flash(request), errors={}, form={},
    )


@app.post("/conta/personagem", response_class=HTMLResponse)
def account_new_char(request: Request, personagem: str = Form(""), sexo: str = Form("1"), vocacao: str = Form("4"), csrf: str = Form("")):
    me = current_account(request)
    if not me:
        return redirect("/entrar")
    if bad_csrf(request, csrf):
        flash(request, "A página expirou. Tente de novo.", "err")
        return redirect("/conta")
    name = clean_name(personagem)
    count = db.one("SELECT COUNT(*) AS n FROM players WHERE account_id = %s AND deletion = 0", me["id"])["n"]
    try:
        voc = int(vocacao)
    except ValueError:
        voc = 0
    problem = None
    if count >= MAX_CHARS:
        problem = f"Cada conta pode ter até {MAX_CHARS} personagens."
    elif voc not in VOCATIONS or sexo not in ("0", "1"):
        problem = "Escolha a vocação e o sexo."
    else:
        with create_lock:
            problem = name_problem(name)
            if not problem:
                create_character(me["id"], name, int(sexo), voc)
    if problem:
        flash(request, problem, "err")
    else:
        flash(request, f"{name} foi criado e já pode entrar no jogo!")
    return redirect("/conta")


@app.post("/conta/senha", response_class=HTMLResponse)
def account_password(request: Request, atual: str = Form(""), senha: str = Form(""), senha2: str = Form(""), csrf: str = Form("")):
    me = current_account(request)
    if not me:
        return redirect("/entrar")
    ip = sec.client_ip(request)
    problem = None
    if bad_csrf(request, csrf):
        problem = "A página expirou. Tente de novo."
    elif login_ip.blocked(ip):
        problem = "Muitas tentativas. Espere 10 minutos."
    elif not sec.password_ok(me["password"], atual):
        login_ip.hit(ip)
        problem = "A senha atual está errada."
    else:
        problem = sec.password_problem(senha, me["email"]) or (senha != senha2 and "As senhas novas não são iguais.") or None
    if problem:
        flash(request, problem, "err")
        return redirect("/conta#senha")
    db.run("UPDATE accounts SET password = %s WHERE id = %s", sec.sha1(senha), me["id"])
    acc = db.one("SELECT id, name, email, password FROM accounts WHERE id = %s", me["id"])
    log_in(request, acc)  # keeps this browser logged in; every other session ends
    flash(request, "Senha trocada! Use a nova no jogo também.")
    return redirect("/conta")


@app.exception_handler(404)
def not_found(request: Request, exc):
    return page(request, "404.html", status_code=404)
