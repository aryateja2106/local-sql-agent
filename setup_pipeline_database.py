#!/usr/bin/env python3
"""Build a medallion-style practice database for Southwest DQE interview SQL drills.

Mirrors the interview pipeline in tabular form:
Kafka events -> bronze_events -> quarantine/silver -> gold -> redshift_fact_orders
plus source/target reconciliation tables and an SCD Type 2 customer dimension.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


DEFAULT_DB = Path(__file__).parent / "pipeline_database.db"


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        DROP TABLE IF EXISTS redshift_fact_orders;
        DROP TABLE IF EXISTS gold_daily_booking_metrics;
        DROP TABLE IF EXISTS silver_booking_events;
        DROP TABLE IF EXISTS quarantine_events;
        DROP TABLE IF EXISTS bronze_events;
        DROP TABLE IF EXISTS batch_control;
        DROP TABLE IF EXISTS source_orders;
        DROP TABLE IF EXISTS target_orders;
        DROP TABLE IF EXISTS staged_customer;
        DROP TABLE IF EXISTS dim_customer;
        DROP TABLE IF EXISTS employees;

        CREATE TABLE bronze_events (
            ingestion_id INTEGER PRIMARY KEY,
            event_id TEXT,
            topic TEXT NOT NULL,
            partition_id INTEGER NOT NULL,
            kafka_offset INTEGER NOT NULL,
            event_ts TEXT,
            ingested_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            is_malformed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE quarantine_events (
            quarantine_id INTEGER PRIMARY KEY,
            ingestion_id INTEGER NOT NULL,
            event_id TEXT,
            reason TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            quarantined_at TEXT NOT NULL
        );

        CREATE TABLE silver_booking_events (
            event_id TEXT PRIMARY KEY,
            booking_id TEXT NOT NULL,
            customer_id INTEGER,
            route TEXT,
            fare_amount REAL,
            currency TEXT,
            event_date TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            ingestion_id INTEGER NOT NULL,
            batch_id TEXT NOT NULL
        );

        CREATE TABLE gold_daily_booking_metrics (
            metric_date TEXT NOT NULL,
            route TEXT NOT NULL,
            booking_count INTEGER NOT NULL,
            fare_total REAL NOT NULL,
            null_customer_pct REAL NOT NULL,
            PRIMARY KEY (metric_date, route)
        );

        CREATE TABLE redshift_fact_orders (
            order_id TEXT PRIMARY KEY,
            customer_id INTEGER,
            order_date TEXT NOT NULL,
            amount REAL,
            status TEXT,
            loaded_batch_id TEXT NOT NULL
        );

        CREATE TABLE batch_control (
            batch_id TEXT PRIMARY KEY,
            stage TEXT NOT NULL,
            source_count INTEGER NOT NULL,
            accepted_count INTEGER NOT NULL,
            quarantine_count INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL
        );

        CREATE TABLE source_orders (
            order_id TEXT PRIMARY KEY,
            amount REAL,
            status TEXT,
            updated_at TEXT
        );

        CREATE TABLE target_orders (
            order_id TEXT PRIMARY KEY,
            amount REAL,
            status TEXT,
            updated_at TEXT
        );

        CREATE TABLE staged_customer (
            customer_id INTEGER PRIMARY KEY,
            city TEXT NOT NULL,
            loyalty_tier TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            row_hash TEXT NOT NULL
        );

        CREATE TABLE dim_customer (
            customer_sk INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            city TEXT NOT NULL,
            loyalty_tier TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            is_current INTEGER NOT NULL,
            row_hash TEXT NOT NULL
        );

        CREATE TABLE employees (
            employee_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            salary REAL NOT NULL
        );
        """
    )
    conn.commit()


def seed_data(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    now = datetime(2026, 7, 20, 12, 0, 0)
    batch_id = "batch_2026_07_20_12"

    bronze_rows = []
    silver_rows = []
    quarantine_rows = []

    # Clean booking events, including intentional duplicates for dedup drills.
    bookings = [
        ("evt-100", "bk-100", 101, "DAL-HOU", 129.0, "USD", 0),
        ("evt-101", "bk-101", 102, "AUS-DAL", 89.5, "USD", 0),
        ("evt-102", "bk-102", None, "HOU-AUS", 110.0, "USD", 0),  # null customer
        ("evt-103", "bk-103", 103, "DAL-PHX", 199.0, "USD", 0),
        ("evt-104", "bk-104", 104, "PHX-LAS", 75.0, "USD", 0),
        ("evt-100", "bk-100", 101, "DAL-HOU", 139.0, "USD", 0),  # newer duplicate
        ("evt-105", "bk-105", 105, "LAS-LAX", 155.0, "USD", 0),
        ("evt-106", "bk-106", 106, "LAX-OAK", 98.0, "USD", 0),
        ("evt-107", "bk-107", None, "OAK-SAN", 120.0, "USD", 0),
        ("evt-108", "bk-108", 108, "SAN-DAL", 210.0, "USD", 0),
    ]

    ingestion_id = 1
    for idx, (event_id, booking_id, customer_id, route, fare, currency, malformed) in enumerate(bookings):
        event_ts = (now - timedelta(hours=8 - idx)).isoformat(sep=" ")
        ingested_at = (now - timedelta(hours=7 - idx)).isoformat(sep=" ")
        payload = {
            "event_id": event_id,
            "booking_id": booking_id,
            "customer_id": customer_id,
            "route": route,
            "fare_amount": fare,
            "currency": currency,
            "event_ts": event_ts,
        }
        bronze_rows.append(
            (
                ingestion_id,
                event_id,
                "booking.events",
                0,
                1000 + ingestion_id,
                event_ts,
                ingested_at,
                json.dumps(payload),
                malformed,
            )
        )
        silver_candidate = (
            event_id,
            booking_id,
            customer_id,
            route,
            fare,
            currency,
            event_ts[:10],
            ingested_at,
            ingestion_id,
            batch_id,
        )
        # Keep newest ingestion_id per event_id for silver seed.
        existing = next((i for i, row in enumerate(silver_rows) if row[0] == event_id), None)
        if existing is None:
            silver_rows.append(silver_candidate)
        else:
            silver_rows[existing] = silver_candidate
        ingestion_id += 1

    # Malformed Kafka payloads that should land in quarantine.
    bad_payloads = [
        ('{"event_id":"evt-bad-1","fare_amount":"NaN"}', "invalid_fare_amount"),
        ('{"booking_id":"bk-bad","route":"DAL-HOU"}', "missing_event_id"),
        ("not-json", "json_decode_error"),
    ]
    for raw, reason in bad_payloads:
        bronze_rows.append(
            (
                ingestion_id,
                None if reason != "invalid_fare_amount" else "evt-bad-1",
                "booking.events",
                1,
                1000 + ingestion_id,
                now.isoformat(sep=" "),
                now.isoformat(sep=" "),
                raw,
                1,
            )
        )
        quarantine_rows.append(
            (
                len(quarantine_rows) + 1,
                ingestion_id,
                "evt-bad-1" if reason == "invalid_fare_amount" else None,
                reason,
                raw,
                now.isoformat(sep=" "),
            )
        )
        ingestion_id += 1

    cur.executemany(
        """
        INSERT INTO bronze_events (
            ingestion_id, event_id, topic, partition_id, kafka_offset,
            event_ts, ingested_at, payload_json, is_malformed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        bronze_rows,
    )
    cur.executemany(
        """
        INSERT INTO quarantine_events (
            quarantine_id, ingestion_id, event_id, reason, raw_payload, quarantined_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        quarantine_rows,
    )
    cur.executemany(
        """
        INSERT INTO silver_booking_events (
            event_id, booking_id, customer_id, route, fare_amount, currency,
            event_date, updated_at, ingestion_id, batch_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        silver_rows,
    )

    # Gold aggregates by route/day from silver.
    gold = {}
    for row in silver_rows:
        key = (row[6], row[3])
        booking_count, fare_total, null_customers = gold.get(key, (0, 0.0, 0))
        booking_count += 1
        fare_total += float(row[4] or 0)
        null_customers += 1 if row[2] is None else 0
        gold[key] = (booking_count, fare_total, null_customers)

    gold_rows = []
    for (metric_date, route), (booking_count, fare_total, null_customers) in sorted(gold.items()):
        null_pct = 100.0 * null_customers / booking_count
        gold_rows.append((metric_date, route, booking_count, round(fare_total, 2), round(null_pct, 2)))

    cur.executemany(
        """
        INSERT INTO gold_daily_booking_metrics (
            metric_date, route, booking_count, fare_total, null_customer_pct
        ) VALUES (?, ?, ?, ?, ?)
        """,
        gold_rows,
    )

    # Warehouse fact table intentionally missing one silver booking and one amount mismatch.
    fact_rows = []
    for row in silver_rows:
        order_id = row[1]
        amount = row[4]
        if order_id == "bk-108":
            continue  # dropped in warehouse load
        if order_id == "bk-100":
            amount = 129.0  # stale amount vs latest silver 139.0
        fact_rows.append((order_id, row[2], row[6], amount, "CONFIRMED", batch_id))

    cur.executemany(
        """
        INSERT INTO redshift_fact_orders (
            order_id, customer_id, order_date, amount, status, loaded_batch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        fact_rows,
    )

    cur.execute(
        """
        INSERT INTO batch_control (
            batch_id, stage, source_count, accepted_count, quarantine_count,
            started_at, finished_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            "bronze_to_silver",
            len(bronze_rows),
            len(silver_rows),
            len(quarantine_rows),
            (now - timedelta(minutes=30)).isoformat(sep=" "),
            now.isoformat(sep=" "),
            "SUCCESS",
        ),
    )

    source_orders = [
        ("bk-100", 139.0, "CONFIRMED", now.isoformat(sep=" ")),
        ("bk-101", 89.5, "CONFIRMED", now.isoformat(sep=" ")),
        ("bk-102", 110.0, "CONFIRMED", now.isoformat(sep=" ")),
        ("bk-108", 210.0, "CONFIRMED", now.isoformat(sep=" ")),
        ("bk-109", 50.0, "CANCELLED", now.isoformat(sep=" ")),
    ]
    target_orders = [
        ("bk-100", 129.0, "CONFIRMED", now.isoformat(sep=" ")),
        ("bk-101", 89.5, "CONFIRMED", now.isoformat(sep=" ")),
        ("bk-102", 110.0, "CONFIRMED", now.isoformat(sep=" ")),
        ("bk-110", 40.0, "CONFIRMED", now.isoformat(sep=" ")),
    ]
    cur.executemany("INSERT INTO source_orders VALUES (?, ?, ?, ?)", source_orders)
    cur.executemany("INSERT INTO target_orders VALUES (?, ?, ?, ?)", target_orders)

    # SCD Type 2 dimension with one historical and one current row for customer 101.
    dim_rows = [
        (1, 101, "Dallas", "SILVER", "2025-01-01", "2026-03-01", 0, "hash-dal-silver"),
        (2, 101, "Austin", "GOLD", "2026-03-01", None, 1, "hash-aus-gold"),
        (3, 102, "Houston", "SILVER", "2025-06-01", None, 1, "hash-hou-silver"),
        (4, 103, "Phoenix", "GOLD", "2025-08-01", None, 1, "hash-phx-gold"),
    ]
    staged_rows = [
        (101, "Austin", "PLATINUM", "2026-07-20", "hash-aus-plat"),  # change
        (102, "Houston", "SILVER", "2026-07-20", "hash-hou-silver"),  # no change
        (104, "Las Vegas", "SILVER", "2026-07-20", "hash-las-silver"),  # new
    ]
    cur.executemany(
        """
        INSERT INTO dim_customer (
            customer_sk, customer_id, city, loyalty_tier, effective_from,
            effective_to, is_current, row_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        dim_rows,
    )
    cur.executemany(
        "INSERT INTO staged_customer VALUES (?, ?, ?, ?, ?)",
        staged_rows,
    )

    employees = [
        (1, "Ava", "Data Quality", 120000),
        (2, "Noah", "Data Engineering", 125000),
        (3, "Mia", "Analytics", 115000),
        (4, "Liam", "Data Engineering", 125000),
        (5, "Olivia", "Platform", 140000),
        (6, "Ethan", "Analytics", 110000),
        (7, "Sophia", "Data Quality", 118000),
    ]
    cur.executemany("INSERT INTO employees VALUES (?, ?, ?, ?)", employees)
    conn.commit()


def print_counts(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    for table in (
        "bronze_events",
        "quarantine_events",
        "silver_booking_events",
        "gold_daily_booking_metrics",
        "redshift_fact_orders",
        "source_orders",
        "target_orders",
        "dim_customer",
        "staged_customer",
        "employees",
        "batch_control",
    ):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"{table}: {cur.fetchone()[0]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    args.db_path.parent.mkdir(parents=True, exist_ok=True)
    if args.db_path.exists():
        args.db_path.unlink()

    conn = connect(args.db_path)
    try:
        create_schema(conn)
        seed_data(conn)
        print_counts(conn)
        print(f"Pipeline database ready: {args.db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
