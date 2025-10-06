import os
import sys
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key-value-32-chars!!")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import auth, crud, main, models, schemas
from app.database import Base


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


def create_staff_user(
    session,
    username: str = "staff",
    *,
    role: models.UserRole = models.UserRole.SASTRE,
) -> models.User:
    user = models.User(
        username=username,
        full_name=f"{username.title()} User",
        role=role,
        password_hash=auth.get_password_hash("secret"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_customer(session, *, document_id: str = "0912345678") -> models.Customer:
    customer = models.Customer(
        full_name="Cliente de Prueba",
        document_id=document_id,
        phone="0990000000",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


def create_order(
    session,
    customer: models.Customer,
    *,
    order_number: str,
    invoice_number: str,
) -> models.Order:
    order = models.Order(
        order_number=order_number,
        customer_id=customer.id,
        customer_name=customer.full_name,
        customer_document=customer.document_id,
        customer_contact=customer.phone,
        status=models.OrderStatus.EN_TIENDA_BATAN,
        measurements=[],
        origin_branch=models.Establishment.BATAN,
        invoice_number=invoice_number,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def test_get_orders_for_customer_by_invoice_numbers_matches_variants(db_session):
    customer = create_customer(db_session, document_id="0999999999")
    first_order = create_order(
        db_session,
        customer,
        order_number="ORD-100",
        invoice_number="FAC 001-001-000123",
    )
    second_order = create_order(
        db_session,
        customer,
        order_number="ORD-101",
        invoice_number="001-001-000124",
    )
    third_order = create_order(
        db_session,
        customer,
        order_number="ORD-102",
        invoice_number="FAC: 001-001-000125",
    )

    mapping = crud.get_orders_for_customer_by_invoice_numbers(
        db_session,
        customer.id,
        [
            " 001-001-000123  ",
            "fac001-001-000124",
            "fac:001-001-000125",
            None,
            "",
        ],
    )

    assert set(mapping.keys()) == {"001-001-000123", "001-001-000124", "001-001-000125"}
    assert [order.id for order in mapping["001-001-000123"]] == [first_order.id]
    assert [order.id for order in mapping["001-001-000124"]] == [second_order.id]
    assert [order.id for order in mapping["001-001-000125"]] == [third_order.id]


def test_get_customer_contifico_invoices_links_orders(monkeypatch, db_session):
    staff_user = create_staff_user(db_session)
    customer = create_customer(db_session, document_id="0911223344")
    linked_order = create_order(
        db_session,
        customer,
        order_number="ORD-200",
        invoice_number="FAC 001-002-000999",
    )
    _ = create_order(
        db_session,
        customer,
        order_number="ORD-201",
        invoice_number="999-999-999999",
    )

    invoice_match = schemas.ContificoInvoice(
        id=1,
        numero="001-002-000999",
        cliente="Cliente de Prueba",
        identificacion=customer.document_id,
        fecha_emision="2024-01-01",
        estado="AUTORIZADO",
        total=150.5,
    )
    invoice_other = schemas.ContificoInvoice(
        id=2,
        numero="000-123-456789",
        cliente="Otro Cliente",
        identificacion="0000000000",
        fecha_emision="2024-02-01",
        estado="AUTORIZADO",
        total=50.0,
    )

    def fake_build_invoice_page(contifico_client, *, page, page_size, document_id):
        assert document_id == customer.document_id
        return schemas.ContificoInvoicePage(
            items=[invoice_match, invoice_other],
            page=page,
            page_size=page_size,
        )

    monkeypatch.setattr(main, "build_invoice_page", fake_build_invoice_page)

    result = main.get_customer_contifico_invoices(
        customer.id,
        page=2,
        page_size=10,
        db=db_session,
        contifico_client=object(),
        current_user=staff_user,
    )

    assert result.document_id == customer.document_id
    assert result.page == 2
    assert result.page_size == 10
    assert [item.invoice.numero for item in result.items] == [
        "001-002-000999",
        "000-123-456789",
    ]
    linked_numbers = {
        item.invoice.numero: [link.order_id for link in item.linked_orders]
        for item in result.items
    }
    assert linked_numbers["001-002-000999"] == [linked_order.id]
    assert linked_numbers["000-123-456789"] == []
