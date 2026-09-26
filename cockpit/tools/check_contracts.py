"""Checks that the panel's lists agree with each other, so a new screen or bridge action is not half wired.

Run from cockpit/: python tools/check_contracts.py (CI runs it). Exits 1 and lists every mismatch.
- every menu screen has a how-to in the Manual;
- every panel route is inside a menu area, owner-only, or on the short list of pages open to the whole staff;
- every action the panel queues for the game exists in the Lua bridge and has a label in the history;
- every menu screen is a real route.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("COCKPIT_SECRET", "check")

from app import main, manual  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE = os.path.join(HERE, "..", "data", "scripts", "globalevents", "cockpit.lua")
# pages every staff member may open: login, the overview parts, shared helpers (item icons, map tiles) and the manual
OPEN = {"/static", "/login", "/logout", "/", "/manual", "/itens", "/icone/{item_id}.png", "/mapa/{x}/{y}/{z}.png"}

problems = []
menu = main.MENU + [main.OWNER_MENU]
routes = {getattr(r, "path", "") for r in main.app.routes}

for _, _, title, links in menu:
    for href, _, label in links:
        if href not in manual.HOWTO:
            problems.append(f"Manual: a tela {label} ({href}) não tem explicação em manual.HOWTO")
        if href not in routes:
            problems.append(f"Menu: {label} aponta para {href}, que não é uma rota")

for path in sorted(routes):
    if not path or path in OPEN or path.startswith("/parts/") or path.startswith(main.OWNER_ONLY):
        continue
    if main.section_of(path) is None:
        problems.append(f"Acesso: a rota {path} não está em nenhuma área do menu (co-admins veriam sem permissão)")

src = "\n".join(open(os.path.join(HERE, "app", f), encoding="utf-8").read() for f in os.listdir(os.path.join(HERE, "app")) if f.endswith(".py"))
queued = set(re.findall(r'enqueue\([^,]+,\s*"([a-z_]+)"', src)) | set(main.ACTIONS) | set(main.GLOBAL_ACTIONS)
lua = open(BRIDGE, encoding="utf-8").read()
in_bridge = set(re.findall(r"(?:globalActions|actions)\.([a-z_]+)\s*=", lua))
for action in sorted(queued):
    if action not in in_bridge:
        problems.append(f"Ponte: o painel manda '{action}', mas cockpit.lua não tem essa ação")
    if action not in main.ACTION_LABELS:
        problems.append(f"Histórico: a ação '{action}' não tem nome em ACTION_LABELS")

if problems:
    print("\n".join(problems))
    sys.exit(1)
print(f"ok: {sum(len(links) for *_, links in menu)} telas, {len(routes)} rotas, {len(queued)} ações da ponte")
