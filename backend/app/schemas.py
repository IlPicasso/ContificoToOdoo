from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from .models import Establishment, OrderStatus, OrderTaskStatus, UserRole


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None


class MeasurementItem(BaseModel):
    nombre: str = Field(..., description="Nombre de la medida, por ejemplo 'Pecho'")
    valor: str = Field(..., description="Valor de la medida")


class CustomerMeasurementBase(BaseModel):
    name: str = Field(..., description="Nombre del conjunto de medidas")
    measurements: List[MeasurementItem] = Field(default_factory=list)


class CustomerMeasurementCreate(CustomerMeasurementBase):
    pass


class CustomerMeasurementUpdate(CustomerMeasurementBase):
    pass


class CustomerMeasurementRead(CustomerMeasurementBase):
    id: int
    name: str = Field(..., validation_alias=AliasChoices("title", "name"))

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CustomerBase(BaseModel):
    full_name: str
    document_id: str
    phone: Optional[str] = None


class CustomerCreate(CustomerBase):
    measurements: List[CustomerMeasurementCreate] = Field(default_factory=list)


class CustomerUpdate(BaseModel):
    full_name: Optional[str] = None
    document_id: Optional[str] = None
    phone: Optional[str] = None
    measurements: Optional[List[CustomerMeasurementCreate]] = None


class CustomerSummary(CustomerBase):
    id: int
    order_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CustomerRead(CustomerSummary):
    measurements: List[CustomerMeasurementRead] = Field(default_factory=list)


class UserBase(BaseModel):
    username: str
    full_name: str
    role: UserRole


class UserCreate(BaseModel):
    username: str
    full_name: str
    role: UserRole
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str]
    role: Optional[UserRole]
    password: Optional[str]


class UserOut(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class OrderBase(BaseModel):
    order_number: str
    customer_id: int
    customer_name: Optional[str] = None
    customer_document: Optional[str] = None
    customer_contact: Optional[str] = None
    status: OrderStatus = OrderStatus.EN_TIENDA_BATAN
    measurements: List[MeasurementItem] = Field(default_factory=list)
    notes: Optional[str] = None
    assigned_tailor_id: Optional[int] = None
    assigned_vendor_id: Optional[int] = None
    delivery_date: Optional[datetime] = None
    invoice_number: Optional[str] = None
    origin_branch: Optional[Establishment] = None


class OrderCreate(OrderBase):
    origin_branch: Establishment
    tasks: List[OrderTaskCreate] = Field(
        ...,
        min_length=1,

        description="Listado de trabajos que se realizarán para completar la orden.",
    )


class OrderUpdate(BaseModel):
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_document: Optional[str] = None
    customer_contact: Optional[str] = None
    status: Optional[OrderStatus] = None
    measurements: Optional[List[MeasurementItem]] = None
    notes: Optional[str] = None
    assigned_tailor_id: Optional[int] = None
    assigned_vendor_id: Optional[int] = None
    delivery_date: Optional[datetime] = None
    invoice_number: Optional[str] = None
    origin_branch: Optional[Establishment] = None


class OrderPublic(BaseModel):
    order_number: str
    customer_name: str
    customer_document: Optional[str]
    status: OrderStatus
    notes: Optional[str]
    updated_at: datetime
    delivery_date: Optional[datetime] = None
    measurements: List[MeasurementItem] = Field(default_factory=list)
    invoice_number: Optional[str] = None
    origin_branch: Optional[Establishment] = None

    model_config = ConfigDict(from_attributes=True)


class OrderRead(OrderPublic):
    id: int
    customer_id: int
    customer_contact: Optional[str]
    customer: Optional[CustomerSummary]
    assigned_tailor: Optional[UserOut]
    assigned_vendor: Optional[UserOut]
    created_at: datetime


class InvoiceSummary(BaseModel):
    invoice_number: str
    status: Optional[str] = None
    payment_status: Optional[str] = None
    subtotal: Optional[float] = None
    tax_total: Optional[float] = None
    total: Optional[float] = None
    paid_total: Optional[float] = None
    pending_total: Optional[float] = None
    has_pending_balance: bool = False
    currency: Optional[str] = None
    payment_date: Optional[str] = None
    download_url: Optional[str] = None
    share_url: Optional[str] = None


class OrderTaskBase(BaseModel):
    description: str = Field(..., max_length=255)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("La descripción de la tarea es obligatoria")
        return trimmed



class OrderTaskCreate(OrderTaskBase):
    status: OrderTaskStatus = OrderTaskStatus.PENDING
    responsible_id: Optional[int] = Field(default=None, ge=1)


class OrderTaskUpdate(BaseModel):
    description: Optional[str] = Field(default=None, max_length=255)
    status: Optional[OrderTaskStatus] = None
    responsible_id: Optional[int] = Field(default=None, ge=1)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("La descripción de la tarea es obligatoria")
        return trimmed



class OrderTaskRead(BaseModel):
    id: int
    order_id: int
    description: str
    status: OrderTaskStatus
    responsible_id: Optional[int] = None
    responsible: Optional[UserOut] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedCustomers(BaseModel):
    items: List[CustomerRead] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class PaginatedOrders(BaseModel):
    items: List[OrderRead] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class LoginRequest(BaseModel):
    username: str
    password: str


class AuditLogRead(BaseModel):
    id: int
    timestamp: datetime
    action: str
    entity_type: str
    entity_id: Optional[int]
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    actor: Optional[UserOut]

    model_config = ConfigDict(from_attributes=True)
