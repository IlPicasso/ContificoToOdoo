"""Cliente ligero para interactuar con la API de Contífico."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Dict, Iterable, Optional

import httpx


class ContificoClientError(RuntimeError):
    """Errores base del cliente de Contífico."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class ContificoConfigurationError(ContificoClientError):
    """Señala un problema al inicializar el cliente."""


class ContificoTransportError(ContificoClientError):
    """Problema de transporte al comunicarse con la API."""


class ContificoAPIError(ContificoClientError):
    """Respuesta inesperada de la API."""

    def __init__(self, status_code: int, detail: str, payload: Optional[Any] = None):
        super().__init__(detail)
        self.status_code = status_code
        self.payload = payload


class ContificoClient:
    """Cliente HTTP pequeño para la API de Contífico."""

    DEFAULT_BASE_URL = "https://api.contifico.com/sistema/api/v1"

    def __init__(
        self,
        api_key: str,
        api_token: str,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ContificoConfigurationError(
                "La API Key de Contífico es obligatoria para inicializar el cliente."
            )
        if not api_token or not api_token.strip():
            raise ContificoConfigurationError(
                "El API Token de Contífico es obligatorio para inicializar el cliente."
            )
        self.api_key = api_key.strip()
        self.api_token = api_token.strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._transport = transport

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
    ) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": self.api_key,
            "X-Api-Token": self.api_token,
            "Accept": "application/json",
            "Content-Type": "application/json; charset=UTF-8",
        }
        client_kwargs: Dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        try:
            with httpx.Client(**client_kwargs) as client:
                response = client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                )
        except httpx.RequestError as exc:  # pragma: no cover - error path
            raise ContificoTransportError(
                f"No se pudo conectar con Contífico: {exc}".rstrip()
            ) from exc

        if response.status_code >= 400:
            detail = self._extract_error_message(response)
            raise ContificoAPIError(response.status_code, detail, payload=self._safe_json(response))

        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    @staticmethod
    def _safe_json(response: httpx.Response) -> Optional[Any]:
        try:
            return response.json()
        except ValueError:  # pragma: no cover - depende de la respuesta de terceros
            return None

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        payload = ContificoClient._safe_json(response)
        if isinstance(payload, dict):
            for key in ("mensaje", "message", "detail"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        text = response.text.strip()
        if text:
            return text
        return f"Error {response.status_code} al comunicarse con Contífico"

    def list_products(
        self, *, page: int = 1, page_size: int = 100
    ) -> Iterable[Dict[str, Any]]:
        """Devuelve un lote de productos desde Contífico."""

        params = {"result_page": page, "result_size": page_size}
        data = self._request("GET", "producto/", params=params)
        if data is None:
            return []
        if isinstance(data, list):
            return data
        raise ContificoAPIError(
            status_code=200,
            detail="El formato de respuesta para productos no es el esperado.",
            payload=data,
        )

    def list_warehouses(self) -> Iterable[Dict[str, Any]]:
        """Lista las bodegas configuradas en Contífico."""

        data = self._request("GET", "bodega/")
        if data is None:
            return []
        if isinstance(data, list):
            return data
        raise ContificoAPIError(
            status_code=200,
            detail="El formato de respuesta para bodegas no es el esperado.",
            payload=data,
        )

    def list_invoices(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        customer_document: str | None = None,
        document_number: str | None = None,
    ) -> Iterable[Dict[str, Any]]:
        """Obtiene facturas desde Contífico con los filtros disponibles."""

        params: Dict[str, Any] = {
            "result_page": page,
            "result_size": page_size,
            "tipo_registro": "CLI",
            "tipo": "FAC",
        }
        if customer_document:
            params["persona_identificacion"] = customer_document.strip()
        if document_number:
            params["documento"] = document_number.strip()

        data = self._request("GET", "registro/documento/", params=params)
        if data is None:
            return []
        if isinstance(data, list):
            return data
        raise ContificoAPIError(
            status_code=200,
            detail="El formato de respuesta para facturas no es el esperado.",
            payload=data,
        )

    def list_invoices_by_customer_document(
        self,
        document_id: str,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> Iterable[Dict[str, Any]]:
        """Lista facturas usando la identificación del cliente registrado en Contífico."""

        if not document_id or not document_id.strip():
            raise ValueError("El número de documento del cliente es obligatorio.")
        return self.list_invoices(
            page=page,
            page_size=page_size,
            customer_document=document_id.strip(),
        )

    def find_invoice_by_document_number(
        self, document_number: str
    ) -> Optional[Dict[str, Any]]:
        """Busca una factura específica por su número de documento."""

        if not document_number or not document_number.strip():
            raise ValueError("El número de documento de la factura es obligatorio.")

        try:
            invoices = list(
                self.list_invoices(
                    page=1,
                    page_size=1,
                    document_number=document_number.strip(),
                )
            )
        except ContificoAPIError as exc:
            if exc.status_code == HTTPStatus.NOT_FOUND:
                return None
            raise
        if not invoices:
            return None
        return invoices[0]

