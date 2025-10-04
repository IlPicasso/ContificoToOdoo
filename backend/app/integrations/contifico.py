"""Helper utilities for interacting with the Contifico API."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class ContificoError(RuntimeError):
    """Base class for Contifico integration errors."""


class ContificoTransientError(ContificoError):
    """Raised when a transient Contifico error is detected and the request can be retried."""


class ContificoPermanentError(ContificoError):
    """Raised when the request failed definitively and should not be retried automatically."""


class ContificoClient:
    """Thin HTTP client for the Contifico REST API described at https://contifico.github.io/."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        api_token: str,
        timeout: float = 30.0,
        rate_limit_per_minute: int = 50,
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
        client: Optional[httpx.Client] = None,
        sleep_func: Callable[[float], None] = time.sleep,
        monotonic_func: Callable[[], float] = time.monotonic,
        company_id: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if not api_key or not api_token:
            raise ValueError("Contifico API key and token must be provided")

        self.api_key = api_key
        self.api_token = api_token
        self.timeout = timeout
        self.rate_limit_per_minute = max(1, rate_limit_per_minute)
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._client = client or httpx.Client(timeout=timeout)
        self._sleep = sleep_func
        self._monotonic = monotonic_func
        self._request_timestamps: Deque[float] = deque()
        self.company_id = company_id

    def close(self) -> None:
        """Close the underlying HTTP client."""

        self._client.close()

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _respect_rate_limit(self) -> None:
        """Block until a request can be made within the configured limit."""

        if self.rate_limit_per_minute <= 0:
            return

        window = 60.0
        while True:
            now = self._monotonic()
            while self._request_timestamps and now - self._request_timestamps[0] >= window:
                self._request_timestamps.popleft()

            if len(self._request_timestamps) < self.rate_limit_per_minute:
                self._request_timestamps.append(now)
                return

            wait_seconds = window - (now - self._request_timestamps[0])
            wait_seconds = max(wait_seconds, 0)
            logger.info(
                "Contifico rate limit reached (%s/min). Sleeping for %.2f seconds.",
                self.rate_limit_per_minute,
                wait_seconds,
            )
            self._sleep(wait_seconds)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        url = self._build_url(path)
        headers = {
            "Authorization": self.api_key,
            "api-token": self.api_token,
            "Accept": "application/json",
            "Content-Type": "application/json; charset=UTF-8",
        }

        request_params = dict(params) if params else {}

        attempt = 0
        allowed_retries = self.max_retries if max_retries is None else max(0, max_retries)
        while True:
            self._respect_rate_limit()
            try:
                logger.debug("Sending Contifico request %s %s", method.upper(), url)
                response = self._client.request(
                    method,
                    url,
                    params=request_params or None,
                    json=json,
                    headers=headers,
                    timeout=self.timeout,
                )
            except httpx.RequestError as exc:  # pragma: no cover - httpx RequestError holds detail
                logger.warning("Transient network error contacting Contifico: %s", exc)
                if attempt >= allowed_retries:
                    raise ContificoTransientError("Network error contacting Contifico") from exc
            else:
                if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                    logger.warning("Contifico rate limit exceeded: %s", response.text)
                    error: ContificoError = ContificoTransientError("Contifico rate limit exceeded")
                elif 500 <= response.status_code < 600:
                    logger.warning(
                        "Contifico server error (%s): %s",
                        response.status_code,
                        response.text,
                    )
                    error = ContificoTransientError("Contifico service unavailable")
                elif response.status_code >= 400:
                    logger.error(
                        "Contifico request failed permanently (%s): %s",
                        response.status_code,
                        response.text,
                    )
                    raise ContificoPermanentError("Contifico request failed")
                else:
                    logger.debug("Contifico response %s %s", response.status_code, response.text)
                    try:
                        return response.json()
                    except ValueError as exc:  # pragma: no cover - unexpected payload
                        logger.error("Invalid JSON from Contifico: %s", exc)
                        raise ContificoPermanentError("Invalid JSON response from Contifico") from exc

                if attempt >= allowed_retries:
                    raise error

            attempt += 1
            backoff = self.retry_backoff_seconds * (2 ** (attempt - 1))
            logger.info("Retrying Contifico request in %.2f seconds (attempt %s)", backoff, attempt)
            self._sleep(backoff)

    def create_invoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new sales document (factura) in Contifico."""

        return self._request("POST", "documento/", json=payload)

    def update_invoice(self, invoice_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing Contifico document using the documented endpoint."""

        body = dict(payload)
        body["id"] = invoice_id
        return self._request("PUT", "documento/", json=body)

    def get_invoice(
        self,
        invoice_id: str,
        *,
        customer_document: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch a Contifico document by its identifier."""

        if "-" in invoice_id and invoice_id.replace("-", "").isdigit():
            parts = invoice_id.split("-")
            params: Dict[str, Any] = {"numero": invoice_id}
            if len(parts) == 3:
                establecimiento, pto_emision, secuencial = parts
                params.update(
                    {
                        "establecimiento": establecimiento,
                        "pto_emision": pto_emision,
                        "secuencial": secuencial,
                    }
                )
            if self.company_id:
                params["empresa"] = self.company_id
            try:
                return self._request("GET", "documento/", params=params)
            except ContificoTransientError:
                if not customer_document:
                    raise
                logger.info(
                    "Falling back to Contifico persona lookup for invoice %s", invoice_id
                )
                fallback_invoice = self._lookup_invoice_by_customer_document(
                    invoice_number=invoice_id,
                    customer_document=customer_document,
                )
                if fallback_invoice is not None:
                    return fallback_invoice
                raise

        params = self._build_company_detail_params()

        return self._request("GET", f"documento/{invoice_id}/", params=params)

    def _build_company_detail_params(self) -> Optional[Dict[str, Any]]:
        if not self.company_id:
            return None
        return {"empresa": self.company_id, "empresa_id": self.company_id}

    def _lookup_invoice_by_customer_document(
        self,
        *,
        invoice_number: str,
        customer_document: str,
    ) -> Optional[Dict[str, Any]]:
        params: Dict[str, Any] = {"persona_identificacion": customer_document}
        if self.company_id:
            params["empresa"] = self.company_id

        listing = self._request("GET", "registro/documento/", params=params)
        documents = self._extract_document_listing(listing)
        for document in documents:
            if not isinstance(document, dict):
                continue
            numero = document.get("numero") or document.get("documento_numero")
            if numero != invoice_number:
                continue
            document_id = (
                document.get("documento")
                or document.get("documento_id")
                or document.get("id")
            )
            if not document_id:
                return document
            return self._request(
                "GET",
                f"documento/{document_id}/",
                params=self._build_company_detail_params(),
            )
        return None

    @staticmethod
    def _extract_document_listing(payload: Any) -> list[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("results", "items", "data", "documentos"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def get_customer_by_document(self, document: str) -> Dict[str, Any]:
        """Fetch Contifico personas (clientes) filtered by identification number."""

        params = {"identificacion": document}
        if self.company_id:
            params.setdefault("empresa", self.company_id)
        return self._request("GET", "persona/", params=params)

    def __enter__(self) -> "ContificoClient":  # pragma: no cover - convenience
        return self

    def __exit__(self, *_args: Any) -> None:  # pragma: no cover - convenience
        self.close()
