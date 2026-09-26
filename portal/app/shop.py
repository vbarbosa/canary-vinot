"""Tibia Coin shop paid by Pix, checked by hand for now.

The price per coin and the Pix key come from `cockpit_settings` (`shop.*`, set in the Cockpit's
Economia > Loja de coins screen), with env fallbacks for when the Cockpit never saved a row yet.
A purchase is a row in `portal_orders`; the Cockpit lists the pending ones, the admin checks the
Pix and credits the coins.
"""

import os
import secrets
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from . import db

PACKS = (25, 50, 100, 250, 500, 1000)
MIN_COINS, MAX_COINS = 10, 5000
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

SCHEMA = """
CREATE TABLE IF NOT EXISTS portal_orders (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(16) NOT NULL UNIQUE,
  account_id INT UNSIGNED NOT NULL,
  email VARCHAR(255) NOT NULL,
  player_name VARCHAR(255) NOT NULL DEFAULT '',
  coins INT UNSIGNED NOT NULL,
  amount_cents INT UNSIGNED NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'pending',
  created_at INT UNSIGNED NOT NULL,
  paid_at INT UNSIGNED NULL,
  handled_by VARCHAR(64) NULL,
  note VARCHAR(255) NULL,
  ip VARCHAR(45) NOT NULL DEFAULT '',
  KEY account_idx (account_id),
  KEY status_idx (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

STATUS = {"pending": "Aguardando o Pix", "paid": "Coins entregues", "cancelled": "Cancelado"}

_cache = {"t": 0, "v": None}


def init_schema():
    db.run(SCHEMA)


def config():
    """{'price': Decimal per coin, 'pix_key', 'pix_name', 'pix_city', 'pix_note', 'open', 'min_coins'}; cached 10 s."""
    now = time.time()
    if _cache["v"] and now - _cache["t"] < 10:
        return _cache["v"]
    saved = {}
    try:
        saved = {r["k"]: r["v"] for r in db.all("SELECT k, v FROM cockpit_settings WHERE k LIKE 'shop.%%'")}
    except Exception:
        pass  # table missing when the Cockpit never saved a row: env/defaults only
    cents = saved.get("shop.coin_cents")
    price = (_price_from_cents(cents) if cents is not None else None) or _price(os.environ.get("PORTAL_COIN_PRICE")) or Decimal("1.00")
    min_coins = int(saved["shop.min_coins"]) if str(saved.get("shop.min_coins", "")).isdigit() else MIN_COINS
    cfg = {
        "price": price,
        "min_coins": min_coins,
        "pix_key": (saved.get("shop.pix_key") or os.environ.get("PORTAL_PIX_KEY", "")).strip(),
        "pix_name": (saved.get("shop.pix_name") or os.environ.get("PORTAL_PIX_NAME") or "VINOT")[:25],
        "pix_city": (os.environ.get("PORTAL_PIX_CITY") or "CURITIBA")[:15],
        "pix_note": saved.get("shop.pix_note") or "Escreva no Pix o seu e-mail da conta do VinOT e a quantidade de coins.",
    }
    cfg["open"] = bool(cfg["pix_key"]) and saved.get("shop.enabled", "1") != "0"
    _cache.update(t=now, v=cfg)
    return cfg


def _price_from_cents(value):
    try:
        return (Decimal(int(value)) / 100).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _price(value):
    try:
        p = Decimal(str(value).replace(",", ".")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    return p if Decimal("0.01") <= p <= Decimal("1000") else None


def total_cents(coins, price):
    return int((Decimal(coins) * price * 100).quantize(Decimal("1"), ROUND_HALF_UP))


def brl(cents):
    return "R$ " + f"{cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def new_code():
    return "VNT" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


def create(acc, player, coins, ip):
    cfg = config()
    cents = total_cents(coins, cfg["price"])
    for _ in range(5):
        code = new_code()
        if not db.one("SELECT 1 AS x FROM portal_orders WHERE code = %s", code):
            break
    db.run(
        "INSERT INTO portal_orders (code, account_id, email, player_name, coins, amount_cents, created_at, ip) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        code, acc["id"], acc["email"], player, coins, cents, int(time.time()), ip,
    )
    return code


def order(code, account_id):
    return db.one("SELECT * FROM portal_orders WHERE code = %s AND account_id = %s", code, account_id)


def orders(account_id, limit=20):
    return db.all("SELECT * FROM portal_orders WHERE account_id = %s ORDER BY id DESC LIMIT %s", account_id, limit)


def pending_count(account_id):
    return db.one("SELECT COUNT(*) AS n FROM portal_orders WHERE account_id = %s AND status = 'pending'", account_id)["n"]


def cancel(code, account_id):
    db.run("UPDATE portal_orders SET status = 'cancelled', note = 'cancelado pelo jogador' "
           "WHERE code = %s AND account_id = %s AND status = 'pending'", code, account_id)


# ------------------------------------------------------------------ Pix "copia e cola" (static BR Code)

def _tlv(tag, value):
    return f"{tag}{len(value):02d}{value}"


def _crc16(data):
    crc = 0xFFFF
    for byte in data.encode():
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def _ascii(text):
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c for c in text.upper() if c.isalnum() or c == " ").strip()


def brcode(key, amount_cents, txid, name, city):
    payload = (
        _tlv("00", "01")
        + _tlv("26", _tlv("00", "br.gov.bcb.pix") + _tlv("01", key))
        + _tlv("52", "0000")
        + _tlv("53", "986")
        + _tlv("54", f"{amount_cents / 100:.2f}")
        + _tlv("58", "BR")
        + _tlv("59", _ascii(name)[:25] or "VINOT")
        + _tlv("60", _ascii(city)[:15] or "BRASIL")
        + _tlv("62", _tlv("05", txid[:25]))
        + "6304"
    )
    return payload + _crc16(payload)


def qr_svg(data):
    import io

    import segno
    out = io.BytesIO()
    segno.make(data, error="m").save(out, kind="svg", scale=6, border=2, dark="#0b0d12", light="#ffffff", xmldecl=False, svgns=True)
    return out.getvalue().decode()
