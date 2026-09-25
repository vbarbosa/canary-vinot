"""MySQL access. Every query goes through here with bound parameters."""

import os

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
    # One-time links sent by e-mail: account confirmation ("signup") and password reset ("reset").
    # Only the SHA-256 of the token is stored, so a database leak does not leak working links.
    """CREATE TABLE IF NOT EXISTS `portal_tokens` (
        `token_hash` CHAR(64) NOT NULL,
        `kind` VARCHAR(16) NOT NULL,
        `email` VARCHAR(255) NOT NULL,
        `payload` VARCHAR(1024) NOT NULL DEFAULT '',
        `created_at` INT UNSIGNED NOT NULL,
        `expires_at` INT UNSIGNED NOT NULL,
        `sent_count` INT NOT NULL DEFAULT 1,
        `last_sent` INT UNSIGNED NOT NULL DEFAULT 0,
        `ip` VARCHAR(64) NOT NULL DEFAULT '',
        PRIMARY KEY (`token_hash`),
        KEY `portal_tokens_email` (`email`)
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
