from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

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


class ContificoProduct(BaseModel):
    id: Optional[Union[int, str]] = None
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    pvp1: Optional[float] = None
    pvp2: Optional[float] = None
    pvp3: Optional[float] = None
    raw: Dict[str, Any] = Field(default_factory=dict, description="Respuesta original de Contífico.")

    @classmethod
    def from_api(cls, payload: Dict[str, Any]) -> "ContificoProduct":
        if not isinstance(payload, dict):
            raise TypeError("El producto devuelto por Contífico debe ser un diccionario")
        return cls(
            id=payload.get("id"),
            codigo=payload.get("codigo"),
            nombre=payload.get("nombre") or payload.get("descripcion"),
            descripcion=payload.get("descripcion"),
            pvp1=payload.get("pvp1"),
            pvp2=payload.get("pvp2"),
            pvp3=payload.get("pvp3"),
            raw=payload,
        )


class ContificoProductPage(BaseModel):
    items: List[ContificoProduct] = Field(default_factory=list)
    page: int
    page_size: int


class ContificoWarehouse(BaseModel):
    id: Optional[Union[int, str]] = None
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    direccion: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict, description="Respuesta original de Contífico.")

    @classmethod
    def from_api(cls, payload: Dict[str, Any]) -> "ContificoWarehouse":
        if not isinstance(payload, dict):
            raise TypeError("La bodega devuelta por Contífico debe ser un diccionario")
        return cls(
            id=payload.get("id"),
            codigo=payload.get("codigo"),
            nombre=payload.get("nombre") or payload.get("descripcion"),
            direccion=payload.get("direccion"),
            raw=payload,
        )


class ContificoInvoice(BaseModel):
    id: Optional[Union[int, str]] = None
    numero: Optional[str] = None
    cliente: Optional[str] = None
    identificacion: Optional[str] = None
    fecha_emision: Optional[str] = None
    estado: Optional[str] = None
    total: Optional[float] = None
    raw: Dict[str, Any] = Field(default_factory=dict, description="Respuesta original de Contífico.")

    @classmethod
    def from_api(cls, payload: Dict[str, Any]) -> "ContificoInvoice":
        if not isinstance(payload, dict):
            raise TypeError("La factura devuelta por Contífico debe ser un diccionario")

        def _normalize_string(value: Any) -> Optional[str]:
            if isinstance(value, str):
                candidate = value.strip()
                return candidate or None
            if isinstance(value, float):
                if math.isnan(value):
                    return None
                return str(value)
            if isinstance(value, int):
                return str(value)
            return None

        def _extract_string(data: Dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
            for key in keys:
                if key not in data:
                    continue
                value = data.get(key)
                if isinstance(value, dict):
                    nombres = _normalize_string(
                        value.get("nombre")
                        or value.get("NOMBRE")
                        or value.get("nombres")
                        or value.get("NOMBRES")
                    )
                    apellidos = _normalize_string(value.get("apellidos") or value.get("APELLIDOS"))
                    if nombres and apellidos:
                        return f"{nombres} {apellidos}".strip()
                    if nombres:
                        return nombres
                    if apellidos:
                        return apellidos
                    # Algunos payloads anidan los datos del cliente bajo un objeto.
                    nested_value = _extract_string(
                        value,
                        (
                            "nombre",
                            "nombre_completo",
                            "nombreCompleto",
                            "nombre_comercial",
                            "nombreComercial",
                            "razon_social",
                            "razonSocial",
                            "full_name",
                            "FULL_NAME",
                            "cliente",
                            "CLIENTE",
                        ),
                    )
                    if nested_value:
                        return nested_value
                normalized = _normalize_string(value)
                if normalized:
                    return normalized
            return None

        numero = (
            payload.get("numero")
            or payload.get("numero_documento")
            or payload.get("numero_comprobante")
            or payload.get("documento")
            or payload.get("NUMERO")
            or payload.get("NUMERO_DOCUMENTO")
            or payload.get("NUMERO_COMPROBANTE")
            or payload.get("DOCUMENTO")
        )
        cliente = _extract_string(
            payload,
            (
                "cliente",
                "cliente_nombre",
                "CLIENTE",
                "CLIENTE_NOMBRE",
                "cliente_nombre_comercial",
                "CLIENTE_NOMBRE_COMERCIAL",
                "cliente_razon_social",
                "CLIENTE_RAZON_SOCIAL",
                "razon_social",
                "RAZON_SOCIAL",
                "persona_nombre",
                "PERSONA_NOMBRE",
                "persona_razon_social",
                "PERSONA_RAZON_SOCIAL",
            ),
        )
        if not cliente:
            cliente = _extract_string(
                payload,
                (
                    "persona",
                    "cliente_detalle",
                    "datos_cliente",
                    "cliente_info",
                ),
            )
        identificacion = (
            payload.get("cliente_identificacion")
            or payload.get("identificacion_cliente")
            or payload.get("cliente_documento")
            or payload.get("identificacion")
            or payload.get("CLIENTE_IDENTIFICACION")
            or payload.get("IDENTIFICACION_CLIENTE")
            or payload.get("CLIENTE_DOCUMENTO")
            or payload.get("IDENTIFICACION")
            or payload.get("documento")
            or payload.get("DOCUMENTO")
            or payload.get("persona_identificacion")
            or payload.get("PERSONA_IDENTIFICACION")
        )
        fecha = (
            payload.get("fecha_emision")
            or payload.get("fecha")
            or payload.get("fecha_autorizacion")
            or payload.get("FECHA_EMISION")
            or payload.get("FECHA")
            or payload.get("FECHA_AUTORIZACION")
        )
        estado = (
            payload.get("estado")
            or payload.get("estado_sri")
            or payload.get("ESTADO")
            or payload.get("ESTADO_SRI")
        )
        total = (
            payload.get("total")
            or payload.get("total_con_impuestos")
            or payload.get("total_sin_impuestos")
            or payload.get("TOTAL")
            or payload.get("TOTAL_CON_IMPUESTOS")
            or payload.get("TOTAL_SIN_IMPUESTOS")
        )

        try:
            normalized_total = float(total) if total is not None else None
        except (TypeError, ValueError):
            normalized_total = None

        return cls(
            id=payload.get("id"),
            numero=numero,
            cliente=cliente,
            identificacion=identificacion,
            fecha_emision=fecha,
            estado=estado,
            total=normalized_total,
            raw=payload,
        )


class ContificoInvoicePage(BaseModel):
    items: List[ContificoInvoice] = Field(default_factory=list)
    page: int
    page_size: int
