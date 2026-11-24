# -*- coding: utf-8 -*-
"""SQLite 持久化层：文档类型、稽核规则、标准版本、稽核记录、稽核批次。"""
import os
import sqlite3
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "audit.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS doc_types (
    code            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    filename_keywords TEXT NOT NULL DEFAULT '[]',
    sort_order      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type    TEXT NOT NULL,
    dimension   TEXT NOT NULL,
    name        TEXT NOT NULL,
    checker     TEXT NOT NULL,
    params      TEXT NOT NULL DEFAULT '{}',
    severity    TEXT NOT NULL DEFAULT 'medium',
    enabled     INTEGER NOT NULL DEFAULT 1,
    description TEXT DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS standard_versions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type   TEXT NOT NULL,
    version_no INTEGER NOT NULL,
    note       TEXT DEFAULT '',
    snapshot   TEXT NOT NULL,
    rule_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT DEFAULT '',
    source_dir  TEXT DEFAULT '',
    doc_total   INTEGER NOT NULL DEFAULT 0,
    doc_passed  INTEGER NOT NULL DEFAULT 0,
    avg_score   REAL NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id            INTEGER,
    project_name        TEXT DEFAULT '',
    doc_type            TEXT NOT NULL,
    file_name           TEXT NOT NULL,
    file_path           TEXT DEFAULT '',
    file_hash           TEXT DEFAULT '',
    file_size           INTEGER NOT NULL DEFAULT 0,
    standard_version_id INTEGER,
    standard_snapshot   TEXT NOT NULL DEFAULT '[]',
    doc_meta            TEXT NOT NULL DEFAULT '{}',
    total_rules         INTEGER NOT NULL DEFAULT 0,
    passed_rules        INTEGER NOT NULL DEFAULT 0,
    failed_rules        INTEGER NOT NULL DEFAULT 0,
    skipped_rules       INTEGER NOT NULL DEFAULT 0,
    score               REAL NOT NULL DEFAULT 0,
    grade               TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'done',
    error               TEXT DEFAULT '',
    created_at          TEXT NOT NULL,
    duration_ms         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit_findings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL,
    rule_id    INTEGER,
    dimension  TEXT NOT NULL,
    rule_name  TEXT NOT NULL,
    severity   TEXT NOT NULL DEFAULT 'medium',
    status     TEXT NOT NULL,
    message    TEXT DEFAULT '',
    evidence   TEXT DEFAULT '',
    location   TEXT DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_rules_doc_type ON rules(doc_type);
CREATE INDEX IF NOT EXISTS idx_runs_created ON audit_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_runs_doc_type ON audit_runs(doc_type);
CREATE INDEX IF NOT EXISTS idx_findings_run ON audit_findings(run_id);
CREATE INDEX IF NOT EXISTS idx_versions_doc_type ON standard_versions(doc_type);
"""


def now_str():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def get_conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


# 旧版本数据库升级：CREATE TABLE IF NOT EXISTS 不会为已存在的表补列。
MIGRATIONS = {
    "audit_runs": [("doc_meta", "TEXT NOT NULL DEFAULT '{}'")],
}


def _migrate(conn):
    for table, columns in MIGRATIONS.items():
        existing = {row[1] for row in conn.execute("PRAGMA table_info(%s)" % table).fetchall()}
        for name, ddl in columns:
            if name not in existing:
                conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, ddl))


def query(sql, args=()):
    conn = get_conn()
    try:
        return [dict(row) for row in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def query_one(sql, args=()):
    conn = get_conn()
    try:
        row = conn.execute(sql, args).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def execute(sql, args=()):
    conn = get_conn()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def execute_many(sql, seq):
    conn = get_conn()
    try:
        cur = conn.executemany(sql, seq)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
