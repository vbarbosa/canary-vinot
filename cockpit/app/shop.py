"""Loja de Tibia coins: price in reais and the Pix key, set in Economia; the Pix orders the portal creates.

The public portal (portal/app/shop.py) reads these `cockpit_settings` keys every 10 s:
  economy.shopOpen   "1" or "0"  the portal shows the shop (it also stays closed while there is no Pix key)
  economy.coinPrice  "1.00"      price of ONE Tibia coin in reais (1.00 = the 1 para 1 start)
  economy.pixKey     text        static Pix key; the buyer pays by hand and the staff checks it here
  economy.pixName    text        receiver name for the Pix code (max 25), optional

A purchase is a row in `portal_orders` (created by the portal). Confirming it credits the coins exactly like
/conta/{aid}/coins does and marks it paid; only pending orders change, so a double click never pays twice.
"""

import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from . import db

DEFAULTS = {"shopOpen": "1", "coinPrice": "1.00", "pixKey": "", "pixName": ""}
# first version of this screen stored shop.*; moved once to the names the portal reads
LEGACY = {"shop.enabled": "shopOpen", "shop.pix_key": "pixKey", "shop.pix_name": "pixName"}

ORDERS_SCHEMA = """
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


def _put(k, v):
    db.run("INSERT INTO cockpit_settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)", f"economy.{k}", v)


def _migrate():
    old = {r["k"]: r["v"] for r in db.all("SELECT k, v FROM cockpit_settings WHERE k LIKE 'shop.%%'")}
    if not old:
        return
    have = {r["k"][8:] for r in db.all("SELECT k FROM cockpit_settings WHERE k LIKE 'economy.%%'")}
    for k, new in LEGACY.items():
        if k in old and new not in have:
            _put(new, old[k])
    if "shop.coin_cents" in old and "coinPrice" not in have and old["shop.coin_cents"].isdigit():
        _put("coinPrice", f"{int(old['shop.coin_cents']) / 100:.2f}")
    db.run("DELETE FROM cockpit_settings WHERE k LIKE 'shop.%%'")


def settings():
    _migrate()
    s = dict(DEFAULTS)
    s.update({r["k"][8:]: r["v"] for r in db.all("SELECT k, v FROM cockpit_settings WHERE k LIKE 'economy.%%'")})
    s["price"] = _price(s["coinPrice"]) or Decimal("1.00")
    s["open"] = s["shopOpen"] != "0" and bool(s["pixKey"])
    return s


def _price(value):
    try:
        p = Decimal(str(value).replace(",", ".")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    return p if Decimal("0.01") <= p <= Decimal("1000") else None


def save(f):
    price = _price(f.get("coinPrice", ""))
    if not price:
        return "Preço de 1 coin: de R$ 0,01 a R$ 1.000."
    key = " ".join(str(f.get("pixKey", "")).split())[:120]
    is_open = bool(f.get("shopOpen"))
    if is_open and not key:
        return "Com a loja aberta, informe a chave Pix."
    _put("shopOpen", "1" if is_open else "0")
    _put("coinPrice", str(price))
    _put("pixKey", key)
    _put("pixName", " ".join(str(f.get("pixName", "")).split())[:25])
    return ""


def brl(cents):
    return "R$ " + f"{cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- orders

def init_schema():
    db.run(ORDERS_SCHEMA)


def orders(status="pending", limit=100):
    if status == "pending":
        return db.all("SELECT * FROM portal_orders WHERE status = 'pending' ORDER BY id LIMIT %s", limit)
    return db.all("SELECT * FROM portal_orders WHERE status <> 'pending' ORDER BY COALESCE(paid_at, created_at) DESC LIMIT %s", limit)


def counts():
    row = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(amount_cents), 0) AS cents FROM portal_orders WHERE status = 'pending'")
    month = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(amount_cents), 0) AS cents, COALESCE(SUM(coins), 0) AS coins "
                   "FROM portal_orders WHERE status = 'paid' AND paid_at >= %s", int(time.time()) - 30 * 86400)
    return {"pending": row["n"], "pending_cents": row["cents"], "paid": month["n"], "paid_cents": month["cents"], "paid_coins": month["coins"]}


def get(oid):
    return db.one("SELECT * FROM portal_orders WHERE id = %s", oid)


def confirm(oid, admin):
    """Pay a pending order: mark it first (only one click wins), then credit the coins. Returns the order or None."""
    o = get(oid)
    if not o or not db.one("SELECT 1 AS x FROM accounts WHERE id = %s", o["account_id"]):
        return None
    if not db.changed("UPDATE portal_orders SET status = 'paid', paid_at = UNIX_TIMESTAMP(), handled_by = %s "
                      "WHERE id = %s AND status = 'pending'", admin[:64], oid):
        return None
    o = get(oid)
    db.run("UPDATE accounts SET coins = coins + %s WHERE id = %s", o["coins"], o["account_id"])
    db.run("INSERT INTO coins_transactions (account_id, type, coin_type, amount, description) VALUES (%s, 1, 1, %s, %s)",
           o["account_id"], o["coins"], f"Pix {o['code']} (Cockpit: {admin})"[:255])
    return o


def cancel(oid, admin, note):
    note = " ".join(str(note or "").split())[:255] or "cancelado pela equipe"
    if not db.changed("UPDATE portal_orders SET status = 'cancelled', handled_by = %s, note = %s WHERE id = %s AND status = 'pending'",
                      admin[:64], note, oid):
        return None
    return get(oid)
