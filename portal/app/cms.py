"""Content from the VinOT Sanity Studio (portal/cms): site settings, landing page and posts.

Published content is public, so the portal reads it from Sanity's CDN with no token. Answers are
cached for CACHE_SECONDS and the last good copy is kept when Sanity is unreachable. Without a
project configured, the built-in DEFAULTS keep the site looking finished.
"""

import html
import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request

from markupsafe import Markup

log = logging.getLogger("portal.cms")

PROJECT = os.environ.get("SANITY_PROJECT_ID", "").strip()
DATASET = os.environ.get("SANITY_DATASET", "production").strip()
API_VERSION = "2024-01-01"
CACHE_SECONDS = int(os.environ.get("SANITY_CACHE_SECONDS", "60"))

CATEGORIES = {
    "noticia": "Notícia",
    "atualizacao": "Atualização",
    "evento": "Evento",
    "promocao": "Promoção",
}

DEFAULTS = {
    "settings": {
        "serverName": "VinOT",
        "tagline": "O servidor de Tibia pra jogar com a turma",
        "notice": "Por enquanto o VinOT é só pra convidados. Crie sua conta e peça o seu convite pra administração.",
        "clientAndroidUrl": "",
        "clientWindowsUrl": "",
        "whatsappUrl": "",
        "instagramUrl": "",
        "howToPlay": [
            "Crie sua conta aqui no site e confirme o e-mail.",
            "Baixe o cliente do VinOT pro Android ou pro Windows.",
            "Entre com o seu e-mail e a sua senha. Pronto, é só jogar.",
        ],
    },
    "home": {
        "heroTitle": "Bem-vindo ao VinOT",
        "heroText": "Um Tibia feito pra jogar com os amigos: sem pay-to-win, com eventos surpresa, raids e um mestre do jogo que adora aprontar.",
        "ctaText": "Criar minha conta",
        "features": [
            {"icon": "chest", "title": "Loot que vale a pena", "text": "Autoloot, stamina camarada e rates pensadas pra diversão."},
            {"icon": "skull", "title": "Raids e eventos", "text": "Invasões e mini-games na arena quando você menos espera."},
            {"icon": "gift", "title": "Presentes do mestre", "text": "O GM distribui itens, outfits e surpresas pra turma."},
            {"icon": "heart", "title": "Sem pay-to-win", "text": "Aqui ninguém compra poder. É todo mundo no mesmo barco."},
        ],
    },
    "posts": [
        {
            "title": "O VinOT abriu as portas!",
            "slug": "o-vinot-abriu-as-portas",
            "category": "noticia",
            "publishedAt": "2026-09-25T12:00:00Z",
            "featured": True,
            "excerpt": "O servidor está no ar pra turma. Crie sua conta, escolha a vocação e venha pra Thais.",
            "body": [
                {"_type": "block", "style": "normal", "children": [{"_type": "span", "text": "O VinOT está no ar! Crie sua conta aqui no site, confirme o e-mail e baixe o cliente."}], "markDefs": []},
            ],
        },
    ],
}

_cache = {}
_lock = threading.Lock()


def enabled():
    return bool(PROJECT)


def _query(groq, **params):
    key = (groq, tuple(sorted(params.items())))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    qs = {"query": groq}
    qs.update({f"${k}": json.dumps(v) for k, v in params.items()})
    url = f"https://{PROJECT}.apicdn.sanity.io/v{API_VERSION}/data/query/{DATASET}?" + urllib.parse.urlencode(qs)
    try:
        with urllib.request.urlopen(url, timeout=4) as resp:
            result = json.loads(resp.read().decode())["result"]
    except Exception as exc:  # keep serving the last good copy
        log.warning("sanity query failed: %s", exc)
        if hit:
            with _lock:
                _cache[key] = (now + 15, hit[1])
            return hit[1]
        raise
    with _lock:
        _cache[key] = (now + CACHE_SECONDS, result)
    return result


def _safe(fn, default):
    if not enabled():
        return default
    try:
        return fn() or default
    except Exception:
        return default


POST_FIELDS = "title, 'slug': slug.current, category, publishedAt, endsAt, featured, excerpt, cover, cta"


def settings():
    got = _safe(lambda: _query("*[_id == 'siteSettings'][0]"), {})
    return {**DEFAULTS["settings"], **{k: v for k, v in got.items() if v not in (None, "", [])}}


def home():
    got = _safe(lambda: _query("*[_id == 'homePage'][0]"), {})
    return {**DEFAULTS["home"], **{k: v for k, v in got.items() if v not in (None, "", [])}}


def posts(limit=12, category=""):
    if not enabled():
        items = [p for p in DEFAULTS["posts"] if not category or p["category"] == category]
        return items[:limit]
    filt = "_type == 'post' && defined(slug.current) && publishedAt <= now()"
    if category:
        filt += " && category == $cat"
        q = f"*[{filt}] | order(featured desc, publishedAt desc)[0...$n]{{{POST_FIELDS}}}"
        return _safe(lambda: _query(q, cat=category, n=limit), [])
    q = f"*[{filt}] | order(featured desc, publishedAt desc)[0...$n]{{{POST_FIELDS}}}"
    return _safe(lambda: _query(q, n=limit), DEFAULTS["posts"][:limit])


def promotions(limit=3):
    """Promotions and events still running (no end date, or ending in the future)."""
    if not enabled():
        return []
    q = (
        "*[_type == 'post' && category in ['promocao', 'evento'] && publishedAt <= now() "
        "&& (!defined(endsAt) || endsAt > now())] | order(endsAt asc)[0...$n]{" + POST_FIELDS + "}"
    )
    return _safe(lambda: _query(q, n=limit), [])


def post(slug):
    if not enabled():
        return next((p for p in DEFAULTS["posts"] if p["slug"] == slug), None)
    q = "*[_type == 'post' && slug.current == $slug && publishedAt <= now()][0]{" + POST_FIELDS + ", body}"
    return _safe(lambda: _query(q, slug=slug), None)


# ---------------------------------------------------------------- images

_REF = re.compile(r"^image-([A-Za-z0-9]+)-(\d+x\d+)-([a-z0-9]+)$")


def image_url(img, width=1200):
    """Sanity image object -> CDN URL (https://www.sanity.io/docs/image-urls)."""
    if not img or not PROJECT:
        return ""
    ref = (img.get("asset") or {}).get("_ref", "") if isinstance(img, dict) else ""
    m = _REF.match(ref)
    if not m:
        return ""
    ident, dims, ext = m.groups()
    return f"https://cdn.sanity.io/images/{PROJECT}/{DATASET}/{ident}-{dims}.{ext}?w={int(width)}&auto=format&fit=max"


# ---------------------------------------------------------------- Portable Text -> HTML

_BLOCK_TAGS = {"normal": "p", "h2": "h2", "h3": "h3", "blockquote": "blockquote"}
_DECORATORS = {"strong": "strong", "em": "em", "code": "code", "underline": "u", "strike-through": "s"}
_YOUTUBE = re.compile(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})")


def _safe_href(href):
    href = (href or "").strip()
    return href if re.match(r"^(https?://|mailto:|/)", href, re.I) else ""


def _spans(block):
    defs = {d.get("_key"): d for d in block.get("markDefs") or []}
    out = []
    for span in block.get("children") or []:
        text = html.escape(span.get("text", "")).replace("\n", "<br>")
        for mark in reversed(span.get("marks") or []):
            if mark in _DECORATORS:
                tag = _DECORATORS[mark]
                text = f"<{tag}>{text}</{tag}>"
            elif mark in defs and defs[mark].get("_type") == "link":
                href = _safe_href(defs[mark].get("href"))
                if href:
                    ext = ' rel="noopener nofollow" target="_blank"' if href.startswith("http") else ""
                    text = f'<a href="{html.escape(href)}"{ext}>{text}</a>'
        out.append(text)
    return "".join(out)


def render(blocks):
    """Only known block types and marks are emitted; every string is escaped."""
    out, list_tag = [], None
    for b in blocks or []:
        kind = b.get("_type")
        item = kind == "block" and b.get("listItem")
        if list_tag and (not item or ("ol" if item == "number" else "ul") != list_tag):
            out.append(f"</{list_tag}>")
            list_tag = None
        if kind == "block":
            if item:
                tag = "ol" if item == "number" else "ul"
                if not list_tag:
                    out.append(f"<{tag}>")
                    list_tag = tag
                out.append(f"<li>{_spans(b)}</li>")
            else:
                tag = _BLOCK_TAGS.get(b.get("style"), "p")
                out.append(f"<{tag}>{_spans(b)}</{tag}>")
        elif kind == "image":
            url = image_url(b, 1000)
            if url:
                cap = html.escape(b.get("caption") or "")
                alt = html.escape(b.get("alt") or b.get("caption") or "")
                fig = f'<figure><img src="{url}" alt="{alt}" loading="lazy">'
                out.append(fig + (f"<figcaption>{cap}</figcaption>" if cap else "") + "</figure>")
        elif kind == "videoEmbed":
            m = _YOUTUBE.search(b.get("url") or "")
            if m:
                out.append(
                    f'<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/{m.group(1)}" '
                    'title="Vídeo" allow="encrypted-media; picture-in-picture" allowfullscreen loading="lazy"></iframe></div>'
                )
    if list_tag:
        out.append(f"</{list_tag}>")
    return Markup("".join(out))
