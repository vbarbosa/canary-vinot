"""MySQL access. Every query goes through here with bound parameters."""

import os
import time

import pymysql
import pymysql.cursors

CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "database"),
    "port": int(os.environ.get("MYSQL_PORT", "3306")),
    "user": os.environ.get("MYSQL_USER", "canary"),
    "password": os.environ.get("MYSQL_PASSWORD", os.environ.get("MYSQL_PASS", "canary")),
    "database": os.environ.get("MYSQL_DATABASE", os.environ.get("MYSQL_DBNAME", "otservbr-global")),
}

SCHEMA = [
    # Same definitions the Lua bridge creates on server start; whichever runs first wins.
    """CREATE TABLE IF NOT EXISTS `cockpit_commands` (
        `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        `action` VARCHAR(32) NOT NULL,
        `target` VARCHAR(255) NOT NULL DEFAULT '',
        `arg1` BIGINT NOT NULL DEFAULT 0,
        `arg2` BIGINT NOT NULL DEFAULT 0,
        `arg3` BIGINT NOT NULL DEFAULT 0,
        `arg4` BIGINT NOT NULL DEFAULT 0,
        `text` VARCHAR(1024) NOT NULL DEFAULT '',
        `status` VARCHAR(16) NOT NULL DEFAULT 'pending',
        `result` VARCHAR(255) NOT NULL DEFAULT '',
        `created_by` VARCHAR(255) NOT NULL DEFAULT '',
        `created_at` INT UNSIGNED NOT NULL DEFAULT 0,
        `done_at` INT UNSIGNED NOT NULL DEFAULT 0,
        PRIMARY KEY (`id`),
        KEY `cockpit_commands_status` (`status`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_online` (
        `player_id` INT NOT NULL,
        `name` VARCHAR(255) NOT NULL,
        `level` INT NOT NULL DEFAULT 0,
        `vocation` VARCHAR(64) NOT NULL DEFAULT '',
        `health` INT NOT NULL DEFAULT 0,
        `healthmax` INT NOT NULL DEFAULT 0,
        `posx` INT NOT NULL DEFAULT 0,
        `posy` INT NOT NULL DEFAULT 0,
        `posz` INT NOT NULL DEFAULT 0,
        `updated_at` INT UNSIGNED NOT NULL DEFAULT 0,
        PRIMARY KEY (`player_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_metrics` (
        `ts` INT UNSIGNED NOT NULL,
        `players` INT NOT NULL DEFAULT 0,
        `monsters` INT NOT NULL DEFAULT 0,
        `npcs` INT NOT NULL DEFAULT 0,
        `lua_kb` INT NOT NULL DEFAULT 0,
        `started_at` INT UNSIGNED NOT NULL DEFAULT 0,
        PRIMARY KEY (`ts`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_audit` (
        `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        `at` INT UNSIGNED NOT NULL,
        `actor` VARCHAR(255) NOT NULL,
        `action` VARCHAR(64) NOT NULL,
        `target` VARCHAR(255) NOT NULL DEFAULT '',
        `detail` VARCHAR(1024) NOT NULL DEFAULT '',
        PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_admins` (
        `account_id` INT NOT NULL,
        `sections` VARCHAR(255) NOT NULL DEFAULT '',
        `active` TINYINT NOT NULL DEFAULT 1,
        `created_by` VARCHAR(255) NOT NULL DEFAULT '',
        `created_at` INT UNSIGNED NOT NULL DEFAULT 0,
        PRIMARY KEY (`account_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_group` (
        `player_id` INT NOT NULL,
        PRIMARY KEY (`player_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_kits` (
        `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
        `name` VARCHAR(64) NOT NULL,
        `items` VARCHAR(2048) NOT NULL DEFAULT '',
        PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    # One row per minute, written by the panel itself (scheduler.py); kept 7 days.
    """CREATE TABLE IF NOT EXISTS `cockpit_host_metrics` (
        `ts` INT UNSIGNED NOT NULL,
        `cpu` FLOAT NULL,
        `mem` FLOAT NULL,
        `load1` FLOAT NULL,
        `disk` FLOAT NULL,
        `game_ms` INT NULL,
        `login_ms` INT NULL,
        PRIMARY KEY (`ts`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_places` (
        `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
        `name` VARCHAR(64) NOT NULL,
        `note` VARCHAR(255) NOT NULL DEFAULT '',
        `x` INT NOT NULL,
        `y` INT NOT NULL,
        `z` INT NOT NULL,
        `created_by` VARCHAR(255) NOT NULL DEFAULT '',
        PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_economy` (
        `ts` INT UNSIGNED NOT NULL,
        `gold` BIGINT NOT NULL DEFAULT 0,
        `bank` BIGINT NOT NULL DEFAULT 0,
        `coins` BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (`ts`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_schedules` (
        `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
        `name` VARCHAR(64) NOT NULL,
        `action` VARCHAR(32) NOT NULL,
        `alvo` VARCHAR(16) NOT NULL DEFAULT '',
        `arg1` BIGINT NOT NULL DEFAULT 0,
        `arg2` BIGINT NOT NULL DEFAULT 0,
        `text` VARCHAR(500) NOT NULL DEFAULT '',
        `kind` VARCHAR(16) NOT NULL,
        `every_min` INT NOT NULL DEFAULT 0,
        `at_time` VARCHAR(5) NOT NULL DEFAULT '',
        `weekdays` VARCHAR(7) NOT NULL DEFAULT '',
        `enabled` TINYINT NOT NULL DEFAULT 1,
        `created_by` VARCHAR(255) NOT NULL DEFAULT '',
        `last_run` INT UNSIGNED NOT NULL DEFAULT 0,
        `next_run` INT UNSIGNED NOT NULL DEFAULT 0,
        `last_result` VARCHAR(255) NOT NULL DEFAULT '',
        PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]


SCHEMA += [
    """CREATE TABLE IF NOT EXISTS `cockpit_settings` (
        `k` VARCHAR(64) NOT NULL,
        `v` VARCHAR(255) NOT NULL DEFAULT '',
        PRIMARY KEY (`k`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_house_rent` (
        `house_id` INT NOT NULL,
        `owner` INT NOT NULL DEFAULT 0,
        `rent` BIGINT NULL DEFAULT NULL,
        `paid_until` INT UNSIGNED NOT NULL DEFAULT 0,
        `warnings` INT NOT NULL DEFAULT 0,
        `next_try` INT UNSIGNED NOT NULL DEFAULT 0,
        `cmd_id` BIGINT UNSIGNED NOT NULL DEFAULT 0,
        PRIMARY KEY (`house_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_events` (
        `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
        `kind` VARCHAR(16) NOT NULL,
        `name` VARCHAR(64) NOT NULL DEFAULT '',
        `started_at` INT UNSIGNED NOT NULL DEFAULT 0,
        `ended_at` INT UNSIGNED NOT NULL DEFAULT 0,
        `status` VARCHAR(16) NOT NULL DEFAULT 'queued',
        `players` VARCHAR(2000) NOT NULL DEFAULT '',
        `winners` VARCHAR(1000) NOT NULL DEFAULT '',
        `details` VARCHAR(2000) NOT NULL DEFAULT '',
        `created_by` VARCHAR(255) NOT NULL DEFAULT '',
        PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_event_presets` (
        `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
        `name` VARCHAR(64) NOT NULL,
        `kind` VARCHAR(16) NOT NULL,
        `x` INT NOT NULL, `y` INT NOT NULL, `z` INT NOT NULL,
        `radius` INT NOT NULL DEFAULT 8,
        `alvo` VARCHAR(16) NOT NULL DEFAULT 'turma',
        `minutes` INT NOT NULL DEFAULT 5,
        `first` INT NOT NULL DEFAULT 2,
        `every` INT NOT NULL DEFAULT 30,
        `speed` INT NOT NULL DEFAULT 100,
        `kit_id` INT NOT NULL DEFAULT 0,
        `gold` BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_signups` (
        `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
        `preset_id` INT UNSIGNED NOT NULL,
        `name` VARCHAR(64) NOT NULL,
        `opened_at` INT UNSIGNED NOT NULL,
        `closes_at` INT UNSIGNED NOT NULL,
        `status` VARCHAR(12) NOT NULL DEFAULT 'open',
        `reminded` TINYINT NOT NULL DEFAULT 0,
        `result` VARCHAR(255) NOT NULL DEFAULT '',
        `created_by` VARCHAR(255) NOT NULL DEFAULT '',
        PRIMARY KEY (`id`), KEY `status` (`status`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_signup_players` (
        `signup_id` INT UNSIGNED NOT NULL,
        `player_id` INT NOT NULL,
        `name` VARCHAR(255) NOT NULL,
        `at` INT UNSIGNED NOT NULL,
        PRIMARY KEY (`signup_id`, `player_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_raid_auto` (
        `name` VARCHAR(64) NOT NULL,
        `enabled` TINYINT NOT NULL DEFAULT 1,
        `chance` DECIMAL(7,3) NULL,
        `min_players` INT NULL,
        PRIMARY KEY (`name`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_auctions` (
        `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
        `house_id` INT NOT NULL,
        `house` VARCHAR(255) NOT NULL,
        `town` VARCHAR(64) NOT NULL DEFAULT '',
        `min_bid` BIGINT NOT NULL,
        `ends_at` INT UNSIGNED NOT NULL,
        `status` VARCHAR(12) NOT NULL DEFAULT 'open',
        `top_bid` BIGINT NOT NULL DEFAULT 0,
        `top_player_id` INT NOT NULL DEFAULT 0,
        `top_name` VARCHAR(255) NOT NULL DEFAULT '',
        `cmd_id` BIGINT NOT NULL DEFAULT 0,
        `result` VARCHAR(255) NOT NULL DEFAULT '',
        `created_by` VARCHAR(255) NOT NULL DEFAULT '',
        `created_at` INT UNSIGNED NOT NULL DEFAULT 0,
        PRIMARY KEY (`id`), KEY `status` (`status`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_auction_bids` (
        `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        `auction_id` INT UNSIGNED NOT NULL,
        `player_id` INT NOT NULL,
        `name` VARCHAR(255) NOT NULL,
        `amount` BIGINT NOT NULL,
        `at` INT UNSIGNED NOT NULL,
        PRIMARY KEY (`id`), KEY `auction` (`auction_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_quiz` (
        `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
        `question` VARCHAR(255) NOT NULL,
        `answers` VARCHAR(255) NOT NULL,
        `topic` VARCHAR(32) NOT NULL DEFAULT '',
        `active` TINYINT NOT NULL DEFAULT 1,
        PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_wheel_prizes` (
        `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
        `label` VARCHAR(64) NOT NULL,
        `kind` VARCHAR(8) NOT NULL,
        `item_id` INT NOT NULL DEFAULT 0,
        `amount` BIGINT NOT NULL DEFAULT 0,
        `weight` INT NOT NULL DEFAULT 1,
        `active` TINYINT NOT NULL DEFAULT 1,
        PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_wheel_log` (
        `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        `at` INT UNSIGNED NOT NULL,
        `player` VARCHAR(255) NOT NULL,
        `prize_id` INT NOT NULL DEFAULT 0,
        `label` VARCHAR(64) NOT NULL DEFAULT '',
        `paid` VARCHAR(32) NOT NULL DEFAULT '',
        PRIMARY KEY (`id`),
        KEY `at` (`at`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS `cockpit_house_log` (
        `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        `ts` INT UNSIGNED NOT NULL,
        `house_id` INT NOT NULL,
        `house` VARCHAR(255) NOT NULL DEFAULT '',
        `player` VARCHAR(255) NOT NULL DEFAULT '',
        `kind` VARCHAR(16) NOT NULL,
        `amount` BIGINT NOT NULL DEFAULT 0,
        `note` VARCHAR(255) NOT NULL DEFAULT '',
        `actor` VARCHAR(255) NOT NULL DEFAULT '',
        PRIMARY KEY (`id`),
        KEY `cockpit_house_log_house` (`house_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]


def connect():
    return pymysql.connect(**CONFIG, charset="utf8mb4", autocommit=True, cursorclass=pymysql.cursors.DictCursor)


def all(sql, *args):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def one(sql, *args):
    rows = all(sql, *args)
    return rows[0] if rows else None


def run(sql, *args):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.lastrowid


def changed(sql, *args):
    """Run an UPDATE/DELETE and return how many rows it touched (guards against double clicks)."""
    with connect() as conn, conn.cursor() as cur:
        return cur.execute(sql, args)


# Columns added after a table first shipped; each runs once and is skipped when the column is already there.
MIGRATIONS = [
    ("cockpit_event_presets", "extra", "ALTER TABLE `cockpit_event_presets` ADD COLUMN `extra` VARCHAR(1000) NOT NULL DEFAULT ''"),
    ("cockpit_event_presets", "signup_min", "ALTER TABLE `cockpit_event_presets` ADD COLUMN `signup_min` INT NOT NULL DEFAULT 5"),
]


def init_schema():
    for sql in SCHEMA:
        run(sql)
    for table, column, sql in MIGRATIONS:
        if not one("SELECT 1 AS x FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
                   table, column):
            run(sql)


def enqueue(actor, action, target="", arg1=0, arg2=0, arg3=0, arg4=0, text=""):
    """Queue one command for the Lua bridge, record it in the audit log and return its id."""
    cid = run(
        "INSERT INTO cockpit_commands (action, target, arg1, arg2, arg3, arg4, text, created_by, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        action, target, int(arg1), int(arg2), int(arg3), int(arg4), text[:1024], actor, int(time.time()),
    )
    audit(actor, action, target, " ".join(str(a) for a in (arg1, arg2, arg3, arg4) if a) + (f" {text}" if text else ""))
    return cid


def audit(actor, action, target="", detail=""):
    run("INSERT INTO cockpit_audit (at, actor, action, target, detail) VALUES (%s,%s,%s,%s,%s)", int(time.time()), actor, action, target, detail[:1024])
