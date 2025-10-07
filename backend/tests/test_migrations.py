import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

os.environ.setdefault("SECRET_KEY", "test-secret-key-value-32-chars!!")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import migrations


def create_legacy_schema(engine):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                """
                CREATE TABLE customers (
                    id INTEGER PRIMARY KEY,
                    full_name VARCHAR(100) NOT NULL,
                    document_id VARCHAR(50) NOT NULL,
                    phone VARCHAR(50)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    order_number VARCHAR(50) NOT NULL,
                    customer_id INTEGER NOT NULL,
                    customer_name VARCHAR(100) NOT NULL,
                    customer_document VARCHAR(50),
                    customer_contact VARCHAR(255),
                    status VARCHAR(50) NOT NULL,
                    measurements TEXT NOT NULL,
                    notes TEXT,
                    assigned_tailor_id INTEGER,
                    delivery_date DATE,
                    origin_branch VARCHAR(50),
                    invoice_number VARCHAR(50),
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )


def test_apply_schema_upgrades_adds_vendor_column(tmp_path):
    database_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{database_path}")
    create_legacy_schema(engine)

    inspector = inspect(engine)
    column_names = {column["name"] for column in inspector.get_columns("orders")}
    assert "assigned_vendor_id" not in column_names

    migrations.apply_schema_upgrades(engine)

    inspector = inspect(engine)
    column_names = {column["name"] for column in inspector.get_columns("orders")}
    assert "assigned_vendor_id" in column_names

    # Running the upgrade again should be a no-op
    migrations.apply_schema_upgrades(engine)
    inspector = inspect(engine)
    column_names = {column["name"] for column in inspector.get_columns("orders")}
    assert "assigned_vendor_id" in column_names


def test_apply_schema_upgrades_adds_customer_contact_columns(tmp_path):
    database_path = tmp_path / "legacy_customers.db"
    engine = create_engine(f"sqlite:///{database_path}")
    create_legacy_schema(engine)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("customers")}
    assert "email" not in columns
    assert "address" not in columns

    migrations.apply_schema_upgrades(engine)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("customers")}
    assert "email" in columns
    assert "address" in columns

    migrations.apply_schema_upgrades(engine)
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("customers")}
    assert "email" in columns
    assert "address" in columns


def test_apply_schema_upgrades_handles_missing_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    # Should not raise even if the orders table is absent
    migrations.apply_schema_upgrades(engine)
