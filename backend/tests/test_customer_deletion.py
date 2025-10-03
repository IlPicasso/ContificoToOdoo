import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-secret-key-value-32-chars!!")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import auth, main, models  # noqa: E402
from app.database import Base  # noqa: E402


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def create_admin(session) -> models.User:
    admin = models.User(
        username="admin",
        full_name="Administrador",
        role=models.UserRole.ADMIN,
        password_hash=auth.get_password_hash("secret"),
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    return admin


def create_customer(session, *, document_suffix: str = "1") -> models.Customer:
    customer = models.Customer(
        full_name=f"Cliente {document_suffix}",
        document_id=f"123456789{document_suffix}",
        phone="0990000000",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


def create_order(session, customer: models.Customer, *, order_number: str = "ORD-1") -> models.Order:
    order = models.Order(
        order_number=order_number,
        customer_id=customer.id,
        customer_name=customer.full_name,
        customer_document=customer.document_id,
        customer_contact=customer.phone,
        status=models.OrderStatus.EN_TIENDA_BATAN,
        measurements=[],
        origin_branch=models.Establishment.BATAN,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def test_admin_cannot_delete_customer_with_orders(db_session):
    admin = create_admin(db_session)
    customer = create_customer(db_session)
    create_order(db_session, customer)

    with pytest.raises(HTTPException) as exc_info:
        main.delete_customer_endpoint(customer.id, db_session, admin)

    assert exc_info.value.status_code == 400
    assert "órdenes" in exc_info.value.detail.lower()
    assert db_session.query(models.Customer).count() == 1


def test_admin_can_delete_customer_without_orders(db_session):
    admin = create_admin(db_session)
    customer = create_customer(db_session, document_suffix="2")

    response = main.delete_customer_endpoint(customer.id, db_session, admin)

    assert response is None
    assert db_session.query(models.Customer).count() == 0
    assert db_session.query(models.Order).count() == 0
    audit_logs = db_session.query(models.AuditLog).filter_by(entity_type="customer").all()
    assert any(log.action == "delete" for log in audit_logs)
