"""Apagar dados: tela modular onde o dono escolhe o que zerar, categoria por categoria.

Cada categoria em CATEGORIES tem uma descrição (mostrada na tela) e uma função que apaga só
aquilo. "Apagar tudo" é a mesma coisa que marcar todas as categorias, não um caminho separado.
Contas e personagens da equipe (grupo God ou co-admin em cockpit_admins) nunca são apagados,
senão ninguém entra mais no painel.
"""

from . import db, resets, wheel, world

GOD_GROUP = 6  # same value as main.GOD_GROUP; kept local to avoid importing main here


def _protected_account_ids():
    ids = {r["account_id"] for r in db.all("SELECT DISTINCT account_id FROM players WHERE group_id >= %s", GOD_GROUP)}
    ids |= {r["account_id"] for r in db.all("SELECT account_id FROM cockpit_admins")}
    return ids or {0}


def _wipe_players():
    protected = _protected_account_ids()
    placeholders = ", ".join(["%s"] * len(protected))
    db.run(f"DELETE FROM players WHERE account_id NOT IN ({placeholders})", *protected)
    db.run(f"DELETE FROM accounts WHERE id NOT IN ({placeholders})", *protected)


def _wipe_houses():
    db.run("UPDATE houses SET owner = 0, new_owner = -1, paid = 0, warnings = 0, bid = 0, bid_end = 0, last_bid = 0, highest_bidder = 0")
    db.run("DELETE FROM house_lists")
    db.run("DELETE FROM cockpit_house_rent")
    db.run("DELETE FROM cockpit_auction_bids")
    db.run("DELETE FROM cockpit_auctions")
    db.run("DELETE FROM cockpit_house_log")


def _wipe_mercado():
    db.run("DELETE FROM market_offers")
    db.run("DELETE FROM market_history")
    db.run("DELETE FROM guildwar_kills")
    db.run("DELETE FROM guild_wars")


def _wipe_historico():
    db.run("DELETE FROM cockpit_audit")
    db.run("DELETE FROM cockpit_metrics")
    db.run("DELETE FROM cockpit_host_metrics")
    db.run("DELETE FROM cockpit_economy")
    db.run("DELETE FROM cockpit_wheel_log")
    db.run("DELETE FROM cockpit_metin_damage")
    db.run("DELETE FROM cockpit_signup_players")
    db.run("DELETE FROM cockpit_signups")


def _wipe_config():
    db.run("DELETE FROM cockpit_kits")
    db.run("DELETE FROM cockpit_event_presets")
    db.run("DELETE FROM cockpit_metin_spots")
    db.run("DELETE FROM cockpit_metin_types")
    db.run("DELETE FROM cockpit_dungeon_auto")
    db.run("DELETE FROM cockpit_raid_auto")
    db.run("DELETE FROM cockpit_schedules")
    db.run("DELETE FROM cockpit_quiz")
    db.run("DELETE FROM cockpit_group")
    db.run("DELETE FROM cockpit_wheel_prizes")
    for prefix in ("world.", "wheel.", "reset."):
        db.run("DELETE FROM cockpit_settings WHERE k LIKE %s", prefix + "%")
    world.seed()
    wheel.seed()
    resets.seed()


# key -> (label, description, wipe function)
CATEGORIES = {
    "jogadores": ("🧙 Personagens e contas", "Apaga todo mundo que não é da equipe (personagens, itens, guilds, ofertas no mercado, VIP, bans). Contas do God e dos co-admins nunca são tocadas.", _wipe_players),
    "casas": ("🏘 Casas", "Tira o dono de todas as casas, apaga leilões, lista de convidados e histórico de casas. As casas em si continuam existindo, só ficam vazias.", _wipe_houses),
    "mercado": ("🛒 Mercado e guerras de guild", "Apaga ofertas e histórico do mercado, e o histórico de guerras entre guilds.", _wipe_mercado),
    "historico": ("📜 Histórico do painel", "Apaga o histórico de ações do painel, métricas, giros da roleta, dano em pedras Metin e inscrições de eventos.", _wipe_historico),
    "config": ("⚙ Configurações personalizadas", "Apaga kits, eventos salvos, tipos e pontos de pedra Metin, raids e dungeons automáticas, tarefas da Agenda, perguntas do Quiz, prêmios da Roleta e a Turma. Roleta, Mundo e Reset voltam para as regras padrão de fábrica.", _wipe_config),
}


def run(keys):
    done = []
    for key in keys:
        entry = CATEGORIES.get(key)
        if entry:
            entry[2]()
            done.append(entry[0])
    return done
