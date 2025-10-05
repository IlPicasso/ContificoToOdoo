"""Cliente ligero para interactuar con la API de Contífico."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import json
import logging
import time

import httpx


logger = logging.getLogger(__name__)

if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
    )
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


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
    INVOICE_LOOKUP_PAGE_SIZE = 100
    INVOICE_LOOKUP_FALLBACK_PAGE_SIZES = (50, 25, 10, 5, 1)
    INVOICE_LOOKUP_MAX_PAGES = 50
    INVOICE_LOOKUP_SERVER_RETRIES = 2
    INVOICE_LOOKUP_RETRY_BACKOFF_BASE = 0.5
    INVOICE_LOOKUP_SERVER_FAILURE_ATTEMPTS = 2
    INVOICE_LOOKUP_SERVER_COOLDOWN_BASE = 2.0
    INVOICE_LOOKUP_CATALOG_PAGE_SIZE = 200
    INVOICE_LOOKUP_CATALOG_MAX_PAGES = 400
    INVOICE_LOOKUP_CATALOG_SERVER_RETRIES = 2
    INVOICE_LOOKUP_CATALOG_BACKOFF_BASE = 1.0
    INVOICE_LOOKUP_DIRECT_FALLBACK_STATUSES = {
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.METHOD_NOT_ALLOWED,
    }

    def __init__(
        self,
        api_key: str,
        api_token: str,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        invoice_cache_path: str | Path | None = None,
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
        self._cache_path: Path | None = (
            Path(invoice_cache_path).expanduser().resolve()
            if invoice_cache_path
            else None
        )
        self._invoice_cache: Dict[str, Dict[str, Any]] = {}
        self._invoice_catalog_complete = False
        self._cache_loaded = False
        self._cache_dirty = False

        self._load_persistent_cache()

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
        logger.info(
            "Contifico request %s %s params=%r json=%r",
            method,
            url,
            params,
            json,
        )
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
            logger.exception(
                "Contifico transport error %s %s params=%r json=%r",
                method,
                url,
                params,
                json,
            )
            raise ContificoTransportError(
                f"No se pudo conectar con Contífico: {exc}".rstrip()
            ) from exc

        logger.info(
            "Contifico response %s %s status=%s headers=%r body=%r",
            method,
            url,
            response.status_code,
            dict(response.headers),
            response.text,
        )

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

    @staticmethod
    def _normalize_invoice_number(value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return ""
        if normalized.upper().startswith("FAC"):
            normalized = normalized[3:]
        normalized = normalized.strip().lstrip("-:")
        normalized = normalized.replace(" ", "")
        return normalized

    @staticmethod
    def _sleep(seconds: float) -> None:
        if seconds <= 0:
            return
        time.sleep(seconds)

    @classmethod
    def _extract_invoice_number(cls, payload: Dict[str, Any]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        keys = (
            "numero",
            "numero_documento",
            "numero_comprobante",
            "documento",
            "NUMERO",
            "NUMERO_DOCUMENTO",
            "NUMERO_COMPROBANTE",
            "DOCUMENTO",
        )
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, (int, float)):
                candidate = str(value)
            elif isinstance(value, str):
                candidate = value.strip()
            else:
                continue
            if candidate:
                return candidate
        return None

    @classmethod
    def _match_invoice_by_number(
        cls, invoices: Iterable[Dict[str, Any]], normalized_target: str
    ) -> Optional[Dict[str, Any]]:
        for invoice in invoices:
            candidate = cls._extract_invoice_number(invoice)
            if not candidate:
                continue
            normalized_candidate = cls._normalize_invoice_number(candidate)
            if normalized_candidate and normalized_candidate == normalized_target:
                return invoice
        return None

    def _invoice_lookup_page_sizes(self) -> Iterable[int]:
        """Yield the preferred page sizes to use while looking up invoices."""

        seen: set[int] = set()
        for size in (self.INVOICE_LOOKUP_PAGE_SIZE, *self.INVOICE_LOOKUP_FALLBACK_PAGE_SIZES):
            if not isinstance(size, int):
                try:
                    size = int(size)
                except (TypeError, ValueError):  # pragma: no cover - defensive guard
                    continue
            if size <= 0 or size in seen:
                continue
            seen.add(size)
            yield size

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
            trimmed_number = document_number.strip()
            params["documento"] = trimmed_number
            normalized_number = self._normalize_invoice_number(trimmed_number)
            if normalized_number:
                params["numero"] = normalized_number

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

        self._load_persistent_cache()
        if not document_number or not document_number.strip():
            raise ValueError("El número de documento de la factura es obligatorio.")

        normalized_target = self._normalize_invoice_number(document_number)
        if not normalized_target:
            raise ValueError("El número de documento de la factura es obligatorio.")

        trimmed_input = document_number.strip()
        canonical_input = " ".join(trimmed_input.split())
        compact_target = (
            normalized_target.replace("-", "") if "-" in normalized_target else None
        )

        logger.info(
            "Starting invoice lookup document_number=%r normalized=%s compact=%s",
            document_number,
            normalized_target,
            compact_target,
        )

        try:
            cached_invoice = self._get_cached_invoice(normalized_target, compact_target)
            if cached_invoice is not None:
                logger.info(
                    "Invoice %s resolved from local cache", normalized_target
                )
                return cached_invoice

            logger.info(
                "Attempting direct Contifico lookup for invoice %s", normalized_target
            )
            direct_invoice = self._lookup_invoice_direct(normalized_target)
            if direct_invoice is not None:
                self._cache_invoice(direct_invoice)
                logger.info(
                    "Invoice %s retrieved via direct Contifico lookup", normalized_target
                )
                return direct_invoice

            logger.info(
                "Direct lookup returned no invoice for %s; switching to paged search",
                normalized_target,
            )

            search_candidates: list[str] = []
            seen_candidates: set[str] = set()
            for candidate in (canonical_input, normalized_target, compact_target):
                if not candidate:
                    continue
                if candidate in seen_candidates:
                    continue
                seen_candidates.add(candidate)
                search_candidates.append(candidate)

            last_server_error: ContificoAPIError | None = None

            for search_attempt in range(
                self.INVOICE_LOOKUP_SERVER_FAILURE_ATTEMPTS + 1
            ):
                logger.info(
                    "Invoice search attempt %d/%d with candidates=%s",
                    search_attempt + 1,
                    self.INVOICE_LOOKUP_SERVER_FAILURE_ATTEMPTS + 1,
                    search_candidates,
                )
                last_server_error = None

                for candidate in search_candidates:
                    logger.info(
                        "Searching invoice candidate=%s normalized_target=%s",
                        candidate,
                        normalized_target,
                    )
                    for page_size in self._invoice_lookup_page_sizes():
                        logger.info(
                            "Requesting invoices candidate=%s page_size=%d",
                            candidate,
                            page_size,
                        )
                        seen_numbers: set[str] = set()
                        encountered_server_error = False

                        for page in range(1, self.INVOICE_LOOKUP_MAX_PAGES + 1):
                            retry_attempt = 0
                            should_stop_paging = False
                            while True:
                                try:
                                    invoices = list(
                                        self.list_invoices(
                                            page=page,
                                            page_size=page_size,
                                            document_number=candidate,
                                        )
                                    )
                                    break
                                except ContificoAPIError as exc:
                                    if exc.status_code == HTTPStatus.NOT_FOUND:
                                        should_stop_paging = True
                                        invoices = []
                                        break
                                    if HTTPStatus.BAD_GATEWAY <= exc.status_code < 600:
                                        last_server_error = exc
                                        if (
                                            retry_attempt
                                            < self.INVOICE_LOOKUP_SERVER_RETRIES
                                        ):
                                            logger.warning(
                                                "Server error %s while paging candidate=%s page=%d; retry=%d",
                                                exc.status_code,
                                                candidate,
                                                page,
                                                retry_attempt + 1,
                                            )
                                            backoff = (
                                                self.INVOICE_LOOKUP_RETRY_BACKOFF_BASE
                                                * (2**retry_attempt)
                                            )
                                            retry_attempt += 1
                                            self._sleep(backoff)
                                            continue
                                        logger.error(
                                            "Server error %s while paging candidate=%s page=%d; aborting page size",
                                            exc.status_code,
                                            candidate,
                                            page,
                                        )
                                        encountered_server_error = True
                                        break
                                    raise

                            if encountered_server_error:
                                logger.info(
                                    "Encountered server error; moving to next candidate"
                                )
                                break

                            if should_stop_paging or not invoices:
                                logger.info(
                                    "No invoices returned for candidate=%s page=%d; stopping pagination",
                                    candidate,
                                    page,
                                )
                                break

                            for invoice in invoices:
                                self._cache_invoice(invoice)

                            match = self._match_invoice_by_number(
                                invoices, normalized_target
                            )
                            if match is not None:
                                self._cache_invoice(match)
                                logger.info(
                                    "Invoice %s found in paged search candidate=%s page=%d",
                                    normalized_target,
                                    candidate,
                                    page,
                                )
                                return match

                            if len(invoices) < page_size:
                                logger.info(
                                    "Last page reached for candidate=%s page_size=%d", candidate, page_size
                                )
                                break

                            page_numbers = set()
                            for invoice in invoices:
                                candidate_number = self._extract_invoice_number(invoice)
                                if not candidate_number:
                                    continue
                                normalized_candidate = self._normalize_invoice_number(
                                    candidate_number
                                )
                                if normalized_candidate:
                                    page_numbers.add(normalized_candidate)

                            if page_numbers and page_numbers.issubset(seen_numbers):
                                logger.info(
                                    "All invoice numbers already seen for candidate=%s; breaking pagination",
                                    candidate,
                                )
                                break

                            seen_numbers.update(page_numbers)

                        if encountered_server_error:
                            continue

                        last_server_error = None
                        break

                if last_server_error is None:
                    logger.info(
                        "Paged search completed; returning cached invoice if available"
                    )
                    return self._get_cached_invoice(normalized_target, compact_target)

                if (
                    search_attempt
                    < self.INVOICE_LOOKUP_SERVER_FAILURE_ATTEMPTS
                ):
                    cooldown = self.INVOICE_LOOKUP_SERVER_COOLDOWN_BASE * (
                        2**search_attempt
                    )
                    logger.info(
                        "Cooling down for %.2f seconds before retrying invoice search",
                        cooldown,
                    )
                    self._sleep(cooldown)
                    continue
                break

            if last_server_error is not None or self._invoice_catalog_complete:
                try:
                    catalog_match = self._lookup_invoice_from_catalog(
                        normalized_target, compact_target
                    )
                except ContificoClientError:
                    if last_server_error is not None:
                        raise last_server_error
                else:
                    if catalog_match is not None:
                        last_server_error = None
                        logger.info(
                            "Invoice %s resolved from catalog cache", normalized_target
                        )
                        return catalog_match
                if last_server_error is not None:
                    raise last_server_error

            return self._get_cached_invoice(normalized_target, compact_target)

        finally:
            self._flush_persistent_cache()

    def _lookup_invoice_direct(self, normalized_target: str) -> Optional[Dict[str, Any]]:
        """Try to retrieve an invoice directly using the document number."""

        if not normalized_target:
            return None

        compact_target = normalized_target.replace("-", "") if "-" in normalized_target else None

        try:
            payload = self._request(
                "GET", f"registro/documento/{normalized_target}/"
            )
        except ContificoClientError as exc:
            if self._should_fallback_from_direct_lookup(exc):
                logger.warning(
                    "Direct lookup failed for invoice %s with recoverable error: %s",
                    normalized_target,
                    exc,
                )
                return None
            raise

        if payload is None:
            logger.info(
                "Direct lookup returned empty response for invoice %s",
                normalized_target,
            )
            return None

        if isinstance(payload, dict):
            candidate = self._extract_invoice_number(payload)
            if not candidate:
                return payload
            normalized_candidate = self._normalize_invoice_number(candidate)
            if normalized_candidate == normalized_target:
                return payload
            if compact_target and normalized_candidate == compact_target:
                return payload
            logger.info(
                "Direct lookup payload did not match invoice %s", normalized_target
            )
            return None

        if isinstance(payload, list):
            match = self._match_invoice_by_number(payload, normalized_target)
            if match is not None:
                return match
            if compact_target:
                for invoice in payload:
                    candidate = self._extract_invoice_number(invoice)
                    if not candidate:
                        continue
                    normalized_candidate = self._normalize_invoice_number(candidate)
                    if normalized_candidate == compact_target:
                        return invoice
            if len(payload) == 1 and isinstance(payload[0], dict):
                return payload[0]

        return None

    def _should_fallback_from_direct_lookup(self, exc: ContificoClientError) -> bool:
        if isinstance(exc, ContificoTransportError):
            return True
        if isinstance(exc, ContificoAPIError):
            status_code = exc.status_code
            if status_code in self.INVOICE_LOOKUP_DIRECT_FALLBACK_STATUSES:
                return True
            if HTTPStatus.INTERNAL_SERVER_ERROR <= status_code < 600:
                return True
        return False

    def _cache_invoice(self, invoice: Dict[str, Any]) -> None:
        if not isinstance(invoice, dict):
            return
        candidate = self._extract_invoice_number(invoice)
        if not candidate:
            return
        normalized_candidate = self._normalize_invoice_number(candidate)
        if not normalized_candidate:
            return
        self._invoice_cache[normalized_candidate] = invoice
        self._cache_dirty = True
        logger.info("Cached invoice %s", normalized_candidate)
        if "-" in normalized_candidate:
            compact_candidate = normalized_candidate.replace("-", "")
            if compact_candidate and compact_candidate not in self._invoice_cache:
                self._invoice_cache[compact_candidate] = invoice
                self._cache_dirty = True
                logger.info(
                    "Cached compact invoice key %s for %s",
                    compact_candidate,
                    normalized_candidate,
                )

    def _get_cached_invoice(
        self, normalized_target: str, compact_target: str | None
    ) -> Optional[Dict[str, Any]]:
        for key in (normalized_target, compact_target):
            if not key:
                continue
            cached = self._invoice_cache.get(key)
            if cached is not None:
                logger.info("Cache hit for invoice key %s", key)
                return cached
        logger.info(
            "Cache miss for invoice normalized=%s compact=%s",
            normalized_target,
            compact_target,
        )
        return None

    def _lookup_invoice_from_catalog(
        self, normalized_target: str, compact_target: str | None
    ) -> Optional[Dict[str, Any]]:
        self._ensure_invoice_catalog()
        return self._get_cached_invoice(normalized_target, compact_target)

    def _ensure_invoice_catalog(self) -> None:
        if self._invoice_catalog_complete:
            logger.info("Invoice catalog already cached locally")
            return
        logger.info("Downloading invoice catalog for local cache")
        self._download_invoice_catalog()
        self._invoice_catalog_complete = True

    def _download_invoice_catalog(self) -> None:
        for page in range(1, self.INVOICE_LOOKUP_CATALOG_MAX_PAGES + 1):
            retry_attempt = 0
            while True:
                try:
                    logger.info(
                        "Requesting invoice catalog page=%d page_size=%d",
                        page,
                        self.INVOICE_LOOKUP_CATALOG_PAGE_SIZE,
                    )
                    invoices = list(
                        self.list_invoices(
                            page=page,
                            page_size=self.INVOICE_LOOKUP_CATALOG_PAGE_SIZE,
                        )
                    )
                    break
                except ContificoAPIError as exc:
                    if (
                        HTTPStatus.BAD_GATEWAY <= exc.status_code < 600
                        and retry_attempt < self.INVOICE_LOOKUP_CATALOG_SERVER_RETRIES
                    ):
                        logger.warning(
                            "Server error %s while downloading catalog page=%d; retry=%d",
                            exc.status_code,
                            page,
                            retry_attempt + 1,
                        )
                        backoff = self.INVOICE_LOOKUP_CATALOG_BACKOFF_BASE * (
                            2**retry_attempt
                        )
                        retry_attempt += 1
                        self._sleep(backoff)
                        continue
                    raise

            if not invoices:
                logger.info("Catalog download finished early at page=%d", page)
                self._flush_persistent_cache()
                return

            for invoice in invoices:
                self._cache_invoice(invoice)

            if len(invoices) < self.INVOICE_LOOKUP_CATALOG_PAGE_SIZE:
                logger.info("Catalog download completed after page=%d", page)
                self._flush_persistent_cache()
                return

        self._flush_persistent_cache()

    def _load_persistent_cache(self) -> None:
        if self._cache_loaded:
            return
        self._cache_loaded = True
        if self._cache_path is None:
            return

        try:
            if not self._cache_path.exists():
                return
        except OSError as exc:  # pragma: no cover - filesystem edge case
            logger.warning(
                "Unable to access invoice cache file %s: %s",
                self._cache_path,
                exc,
            )
            return

        try:
            with self._cache_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Failed to load invoice cache from %s: %s",
                self._cache_path,
                exc,
            )
            return

        if not isinstance(payload, dict):
            logger.warning(
                "Invoice cache in %s is not a JSON object; ignoring",
                self._cache_path,
            )
            return

        loaded = 0
        for key, invoice in payload.items():
            if not isinstance(key, str) or not isinstance(invoice, dict):
                continue
            normalized_key = self._normalize_invoice_number(key)
            if not normalized_key:
                continue
            self._invoice_cache[normalized_key] = invoice
            if "-" in normalized_key:
                compact_key = normalized_key.replace("-", "")
                if compact_key:
                    self._invoice_cache.setdefault(compact_key, invoice)
            loaded += 1

        if loaded:
            logger.info(
                "Loaded %d invoices from persistent cache %s",
                loaded,
                self._cache_path,
            )

    def _flush_persistent_cache(self) -> None:
        if not self._cache_dirty or self._cache_path is None:
            return

        data: Dict[str, Dict[str, Any]] = {}
        for key, invoice in self._invoice_cache.items():
            if not isinstance(invoice, dict):
                continue
            normalized_key = self._normalize_invoice_number(key)
            if not normalized_key:
                continue
            canonical_key = normalized_key
            if "-" not in canonical_key:
                candidate = self._extract_invoice_number(invoice)
                if candidate:
                    normalized_candidate = self._normalize_invoice_number(candidate)
                    if normalized_candidate:
                        canonical_key = normalized_candidate
            data[canonical_key] = invoice

        if not data:
            return

        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._cache_path.with_suffix(".tmp")
            with temp_path.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            temp_path.replace(self._cache_path)
            logger.info(
                "Persisted %d invoices to %s",
                len(data),
                self._cache_path,
            )
            self._cache_dirty = False
        except OSError as exc:
            logger.warning(
                "Failed to persist invoice cache to %s: %s",
                self._cache_path,
                exc,
            )

