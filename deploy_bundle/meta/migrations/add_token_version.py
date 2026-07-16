# -*- coding: utf-8 -*-
import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')


def ensure_token_version(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    col_exists = False
    try:
        cur.execute("SELECT token_version FROM users LIMIT 1")
        col_exists = True
    except sqlite3.OperationalError:
        pass

    if not col_exists:
        cur.execute("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0")
        logger.info("[Migration] Added token_version column to users table")

    conn.commit()
    conn.close()


def migrate():
    ensure_token_version()


if __name__ == '__main__':
    migrate()
