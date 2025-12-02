"""Administración de trabajos asíncronos para búsquedas de facturas de Contífico."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from .config import get_settings
from .contifico import ContificoClient, ContificoClientError, ContificoConfigurationError


logger = logging.getLogger(__name__)


class InvoiceLookupJobStatus(str, Enum):
    """Estados posibles para un trabajo de búsqueda de factura."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class InvoiceLookupJob:
    """Representa la ejecución en segundo plano de una búsqueda puntual."""

    id: str
    document_number: str
    customer_document: Optional[str] = None
    status: InvoiceLookupJobStatus = InvoiceLookupJobStatus.PENDING
    progress: int = 0
    stage: str = "pending"
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())


class InvoiceNotFoundError(ContificoClientError):
    """Error específico para señalar que no se halló la factura solicitada."""


def _default_client_factory() -> ContificoClient:
    """Construye un cliente de Contífico usando la configuración actual."""

    settings = get_settings()
    if not settings.contifico_api_key or not settings.contifico_api_token:
        raise ContificoConfigurationError(
            "La integración con Contífico no está configurada. Define CONTIFICO_API_KEY y CONTIFICO_API_TOKEN."
        )
    return ContificoClient(
        settings.contifico_api_key,
        settings.contifico_api_token,
        base_url=settings.contifico_api_base_url,
        timeout=settings.contifico_timeout_seconds,
        invoice_cache_path=settings.contifico_invoice_cache_path,
        invoice_catalog_page_size=settings.contifico_invoice_catalog_page_size,
        invoice_catalog_max_pages=settings.contifico_invoice_catalog_max_pages,
        invoice_catalog_max_records=settings.contifico_invoice_catalog_max_records,
        invoice_catalog_stop_on_first_match=(
            settings.contifico_invoice_catalog_stop_on_first_match
        ),
    )


def _sanitize_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce la información de progreso a tipos serializables para la API."""

    sanitized: Dict[str, Any] = {}
    for key, value in payload.items():
        if key == "progress":
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
        else:
            sanitized[key] = str(value)
    return sanitized


class InvoiceLookupJobManager:
    """Controlador concurrente de trabajos de búsqueda de facturas."""

    POLL_INTERVAL_SECONDS = 1.0

    def __init__(
        self,
        *,
        client_factory: Callable[[], ContificoClient] | None = None,
        max_job_duration: float | None = None,
    ) -> None:
        self._jobs: Dict[str, InvoiceLookupJob] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client_factory = client_factory or _default_client_factory
        self._max_job_duration: float | None
        if max_job_duration is not None:
            self._max_job_duration = (
                max_job_duration if max_job_duration > 0 else None
            )
        else:
            settings = get_settings()
            default_timeout = getattr(
                settings, "contifico_invoice_lookup_job_timeout_seconds", None
            )
            if default_timeout is None or default_timeout <= 0:
                self._max_job_duration = None
            else:
                self._max_job_duration = float(default_timeout)

    async def start_job(
        self, document_number: str, *, customer_document: str
    ) -> InvoiceLookupJob:
        """Inicia un trabajo en segundo plano para buscar la factura."""

        normalized_number = document_number.strip()
        normalized_customer = customer_document.strip()
        if not normalized_customer:
            raise ValueError("El documento del cliente es obligatorio para la búsqueda.")
        job = InvoiceLookupJob(
            id=uuid4().hex,
            document_number=normalized_number,
            customer_document=normalized_customer,
        )
        async with self._lock:
            self._jobs[job.id] = job
        loop = asyncio.get_running_loop()
        self._loop = loop
        loop.create_task(self._run_job(job.id, normalized_number, normalized_customer))
        return dataclasses.replace(job)

    async def get_job(self, job_id: str) -> Optional[InvoiceLookupJob]:
        """Obtiene una copia del trabajo solicitado."""

        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return dataclasses.replace(job)

    async def _run_job(
        self, job_id: str, document_number: str, customer_document: str
    ) -> None:
        await self._update_job(
            job_id,
            status=InvoiceLookupJobStatus.RUNNING,
            stage="starting",
            progress=5,
        )
        loop = self._loop or asyncio.get_running_loop()
        progress_callback = self._create_progress_callback(job_id, loop)

        lookup_task = asyncio.create_task(
            asyncio.to_thread(
                self._execute_lookup,
                document_number,
                customer_document,
                progress_callback,
            )
        )
        finalize_task = asyncio.create_task(
            self._finalize_lookup(job_id, lookup_task)
        )

        try:
            if self._max_job_duration is not None and self._max_job_duration > 0:
                await asyncio.wait_for(
                    asyncio.shield(finalize_task), timeout=self._max_job_duration
                )
            else:
                await finalize_task
        except asyncio.TimeoutError:
            await self._update_job(
                job_id,
                stage="waiting",
                metadata={
                    "timeout_exceeded": True,
                    "message": (
                        "La búsqueda está tardando más de lo esperado. "
                        "Seguiremos intentando en segundo plano."
                    ),
                },
            )
        except asyncio.CancelledError:
            if not lookup_task.done():
                lookup_task.cancel()
                self._detach_lookup_task(lookup_task)
            if not finalize_task.done():
                finalize_task.cancel()
                self._detach_lookup_task(finalize_task)
            raise

    def _execute_lookup(
        self,
        document_number: str,
        customer_document: str,
        progress_callback: Callable[[str, Dict[str, Any]], None],
    ) -> Dict[str, Any]:
        client = self._client_factory()
        invoice = client.find_invoice_by_document_number(
            document_number,
            customer_document=customer_document,
            progress_callback=progress_callback,
        )
        if invoice is None:
            raise InvoiceNotFoundError(
                "No se encontró una factura con ese número de documento."
            )
        return invoice

    def _create_progress_callback(
        self,
        job_id: str,
        loop: asyncio.AbstractEventLoop,
    ) -> Callable[[str, Dict[str, Any]], None]:
        def callback(stage: str, payload: Dict[str, Any]) -> None:
            progress = payload.get("progress")
            metadata = _sanitize_metadata(payload)
            if progress is not None:
                try:
                    progress_int = int(progress)
                except (TypeError, ValueError):
                    progress_int = None
            else:
                progress_int = None

            async def _update() -> None:
                update_kwargs: Dict[str, Any] = {
                    "stage": stage,
                    "metadata": metadata,
                }
                if progress_int is not None:
                    update_kwargs["progress"] = progress_int
                await self._update_job(job_id, **update_kwargs)

            asyncio.run_coroutine_threadsafe(_update(), loop)

        return callback

    async def _finalize_lookup(
        self, job_id: str, lookup_task: asyncio.Task[Any]
    ) -> None:
        try:
            result = await lookup_task
        except asyncio.CancelledError:
            raise
        except InvoiceNotFoundError as exc:
            await self._update_job(
                job_id,
                status=InvoiceLookupJobStatus.FAILED,
                stage="not_found",
                progress=100,
                error=str(exc),
            )
        except ContificoClientError as exc:
            await self._update_job(
                job_id,
                status=InvoiceLookupJobStatus.FAILED,
                stage="error",
                progress=100,
                error=exc.detail,
            )
        except Exception as exc:  # pragma: no cover - defensivo
            await self._update_job(
                job_id,
                status=InvoiceLookupJobStatus.FAILED,
                stage="error",
                progress=100,
                error=str(exc) or "Error desconocido al consultar Contífico.",
            )
            logger.exception(
                "La tarea de búsqueda de Contífico falló mientras se esperaba su finalización.",
            )
        else:
            await self._update_job(
                job_id,
                status=InvoiceLookupJobStatus.COMPLETED,
                stage="completed",
                progress=100,
                result=result,
            )

    def _detach_lookup_task(self, task: asyncio.Task[Any]) -> None:
        async def _await_task() -> None:
            with contextlib.suppress(asyncio.CancelledError):
                try:
                    await task
                except Exception:  # pragma: no cover - defensivo
                    logger.exception(
                        "La tarea de búsqueda de Contífico falló tras la cancelación.",
                    )

        asyncio.create_task(_await_task())

    async def _update_job(self, job_id: str, **changes: Any) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            new_status = changes.pop("status", None)
            status_was_updated = new_status is not None
            if status_was_updated:
                job.status = new_status
            is_terminal = job.status in (
                InvoiceLookupJobStatus.COMPLETED,
                InvoiceLookupJobStatus.FAILED,
            )
            for field_name, value in changes.items():
                if (
                    is_terminal
                    and not status_was_updated
                    and field_name in {"stage", "progress", "metadata"}
                ):
                    continue
                if field_name == "progress":
                    coerced = max(0, min(int(value), 100))
                    job.progress = max(job.progress, coerced)
                elif field_name == "metadata" and isinstance(value, dict):
                    job.metadata.update(value)
                else:
                    setattr(job, field_name, value)
            job.updated_at = time.time()


_invoice_lookup_job_manager = InvoiceLookupJobManager()


def get_invoice_lookup_job_manager() -> InvoiceLookupJobManager:
    """Dependencia para obtener el administrador global de trabajos."""

    return _invoice_lookup_job_manager


__all__ = [
    "InvoiceLookupJob",
    "InvoiceLookupJobManager",
    "InvoiceLookupJobStatus",
    "InvoiceNotFoundError",
    "get_invoice_lookup_job_manager",
]
