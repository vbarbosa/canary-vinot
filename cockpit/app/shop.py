"""Loja de Tibia coins: the price in reais and how to pay, set in Economia and read by the public portal.

Stored in `cockpit_settings` under shop.* so the portal (same database) reads the current values on every page:
  shop.enabled       "1" or "0"  the portal shows the shop
  shop.coin_cents    int         price of ONE Tibia coin in centavos (100 = R$ 1,00, the 1 para 1 start)
  shop.min_coins     int         smallest order
  shop.pix_key       text        Pix key shown to the buyer (static Pix, checked by hand)
  shop.pix_name      text        who receives, as the bank app shows it
  shop.pix_note      text        what the buyer must write in the Pix description
"""

from . import db

DEFAULTS = {"enabled": "1", "coin_cents": "100", "min_coins": "10", "pix_key": "", "pix_name": "",
            "pix_note": "Escreva no Pix o seu e-mail da conta do VinOT e a quantidade de coins."}
LIMITS = {"coin_cents": (1, 1_000_000), "min_coins": (1, 100_000)}


def settings():
    s = dict(DEFAULTS)
    s.update({r["k"][5:]: r["v"] for r in db.all("SELECT k, v FROM cockpit_settings WHERE k LIKE 'shop.%%'")})
    s["coin_reais"] = int(s["coin_cents"]) / 100
    return s


def save(f):
    values = {"enabled": "1" if f.get("enabled") else "0"}
    try:
        reais = float(str(f.get("coin_reais", "")).replace(",", "."))
        values["coin_cents"] = str(round(reais * 100))
        values["min_coins"] = str(int(f.get("min_coins") or 1))
    except ValueError:
        return "Preço e mínimo são números."
    for k, (lo, hi) in LIMITS.items():
        if not lo <= int(values[k]) <= hi:
            return "Preço entre R$ 0,01 e R$ 10.000 por coin; mínimo de 1 coin."
    for k, limit in (("pix_key", 120), ("pix_name", 80), ("pix_note", 200)):
        values[k] = " ".join(str(f.get(k, "")).split())[:limit]
    if values["enabled"] == "1" and not values["pix_key"]:
        return "Com a loja aberta, informe a chave Pix."
    for k, v in values.items():
        db.run("INSERT INTO cockpit_settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)", f"shop.{k}", v)
    return ""
