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
    """CREATE TABLE IF NOT EXISTS `cockpit_audit` (
        `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        `at` INT UNSIGNED NOT NULL,
        `actor` VARCHAR(255) NOT NULL,
        `action` VARCHAR(64) NOT NULL,
        `target` VARCHAR(255) NOT NULL DEFAULT '',
        `detail` VARCHAR(1024) NOT NULL DEFAULT '',
        PRIMARY KEY (`id`)
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


def init_schema():
    for sql in SCHEMA:
        run(sql)


def enqueue(actor, action, target="", arg1=0, arg2=0, arg3=0, arg4=0, text=""):
    """Queue one command for the Lua bridge and record it in the audit log."""
    run(
        "INSERT INTO cockpit_commands (action, target, arg1, arg2, arg3, arg4, text, created_by, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        action, target, int(arg1), int(arg2), int(arg3), int(arg4), text[:1024], actor, int(time.time()),
    )
    audit(actor, action, target, " ".join(str(a) for a in (arg1, arg2, arg3, arg4) if a) + (f" {text}" if text else ""))


def audit(actor, action, target="", detail=""):
    run("INSERT INTO cockpit_audit (at, actor, action, target, detail) VALUES (%s,%s,%s,%s,%s)", int(time.time()), actor, action, target, detail[:1024])
