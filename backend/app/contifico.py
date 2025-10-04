"""Cliente ligero para interactuar con la API de Contífico."""

from __future__ import annotations

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

