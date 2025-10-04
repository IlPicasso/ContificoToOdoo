import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-secret-key-value-32-chars!!")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import auth, main, models  # noqa: E402
from app.database import Base  # noqa: E402
from app.integrations import ContificoClient, ContificoError  # noqa: E402


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


def create_user(session, username: str, role: models.UserRole) -> models.User:
    user = models.User(
        username=username,
        full_name=username.title(),
        role=role,
        password_hash=auth.get_password_hash("secret"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_customer(session) -> models.Customer:
    customer = models.Customer(
        full_name="Cliente Factura",
        document_id="0991234567",
        phone="0991231234",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


def create_order(session, invoice_number: str | None = "INV-001") -> models.Order:
    customer = create_customer(session)
    order = models.Order(
        order_number="ORD-900",
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


class DummyContificoClient:
    def __init__(self, payload=None, error: Exception | None = None):
        self.payload = payload or {}
        self.error = error
        self.requested_invoice = None

    def get_invoice(self, invoice_id: str):
        self.requested_invoice = invoice_id
        if self.error:
            raise self.error
        return self.payload


def test_get_order_invoice_requires_invoice_number(db_session):
    admin = create_user(db_session, "admin", models.UserRole.ADMIN)
    order = create_order(db_session, invoice_number=None)

    client = DummyContificoClient()
    with pytest.raises(HTTPException) as exc_info:
        main.get_order_invoice_endpoint(order.id, db_session, admin, contifico_client=client)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "La orden no tiene número de factura registrado."
    assert client.requested_invoice is None


def test_get_order_invoice_returns_summary(db_session):
    admin = create_user(db_session, "admin", models.UserRole.ADMIN)
    order = create_order(db_session, invoice_number="INV-500")

    payload = {
        "estado": "AUTORIZADO",
        "estado_pago": "PAGADO",
        "totales": {
            "subtotal": "100",
            "impuestos": "12",
            "total": "112",
            "pagado": "112",
        },
        "fecha_pago": "2024-02-05T10:15:00",
        "links": {
            "pdf": "https://contifico.example/pdf/INV-500",
            "publico": "https://contifico.example/share/INV-500",
        },
    }
    client = DummyContificoClient(payload=payload)

    summary = main.get_order_invoice_endpoint(order.id, db_session, admin, contifico_client=client)

    assert summary.invoice_number == "INV-500"
    assert summary.status == "AUTORIZADO"
    assert summary.payment_status == "PAGADO"
    assert summary.total == 112.0
    assert summary.subtotal == 100.0
    assert summary.tax_total == 12.0
    assert summary.pending_total == 0.0
    assert summary.has_pending_balance is False
    assert summary.payment_date == "2024-02-05T10:15:00"
    assert summary.download_url == "https://contifico.example/pdf/INV-500"
    assert summary.share_url == "https://contifico.example/share/INV-500"
    assert client.requested_invoice == "INV-500"


def test_get_order_invoice_handles_contifico_errors(db_session):
    admin = create_user(db_session, "admin", models.UserRole.ADMIN)
    order = create_order(db_session, invoice_number="INV-404")

    client = DummyContificoClient(error=ContificoError("fallo"))

    with pytest.raises(HTTPException) as exc_info:
        main.get_order_invoice_endpoint(order.id, db_session, admin, contifico_client=client)

    assert exc_info.value.status_code == 502
    assert "Contifico" in exc_info.value.detail


def test_get_order_invoice_forwards_company_param(db_session):
    admin = create_user(db_session, "admin", models.UserRole.ADMIN)
    order = create_order(db_session, invoice_number="INV-600")

    payload = {
        "estado": "AUTORIZADO",
        "estado_pago": "PAGADO",
        "totales": {
            "subtotal": "100",
            "impuestos": "12",
            "total": "112",
            "pagado": "112",
        },
        "fecha_pago": "2024-02-05T10:15:00",
        "links": {
            "pdf": "https://contifico.example/pdf/INV-600",
            "publico": "https://contifico.example/share/INV-600",
        },
    }
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, json=payload)

    contifico_client = ContificoClient(
        base_url="https://api.example.com/sistema/api/v1",
        api_key="key-123",
        api_token="token-abc",
        rate_limit_per_minute=100,
        max_retries=0,
        sleep_func=lambda _seconds: None,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        company_id="EMP-ORDER",
    )

    try:
        summary = main.get_order_invoice_endpoint(
            order.id,
            db_session,
            admin,
            contifico_client=contifico_client,
        )
    finally:
        contifico_client.close()

    assert captured["empresa"] == "EMP-ORDER"
    assert captured["empresa_id"] == "EMP-ORDER"
    assert summary.download_url == "https://contifico.example/pdf/INV-600"
    assert summary.share_url == "https://contifico.example/share/INV-600"


def test_get_contifico_client_dependency_includes_company_id(monkeypatch):
    monkeypatch.setattr(main.settings, "contifico_api_key", "key-123")
    monkeypatch.setattr(main.settings, "contifico_api_token", "token-456")
    monkeypatch.setattr(main.settings, "contifico_company_id", "EMP-XYZ")

    created_clients = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
            created_clients.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(main, "ContificoClient", FakeClient)

    dependency = main.get_contifico_client_dependency()
    client = next(dependency)

    assert created_clients[0].kwargs["company_id"] == "EMP-XYZ"
    assert client is created_clients[0]

    with pytest.raises(StopIteration):
        next(dependency)

    assert created_clients[0].closed is True
