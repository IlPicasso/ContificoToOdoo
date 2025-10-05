"""Administración de trabajos asíncronos para búsquedas de facturas de Contífico."""

from __future__ import annotations

import asyncio
import dataclasses
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from .config import get_settings
from .contifico import ContificoClient, ContificoClientError, ContificoConfigurationError


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
    ) -> None:
        self._jobs: Dict[str, InvoiceLookupJob] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client_factory = client_factory or _default_client_factory

    async def start_job(self, document_number: str) -> InvoiceLookupJob:
        """Inicia un trabajo en segundo plano para buscar la factura."""

        normalized_number = document_number.strip()
        job = InvoiceLookupJob(id=uuid4().hex, document_number=normalized_number)
        async with self._lock:
            self._jobs[job.id] = job
        loop = asyncio.get_running_loop()
        self._loop = loop
        loop.create_task(self._run_job(job.id, normalized_number))
        return dataclasses.replace(job)

    async def get_job(self, job_id: str) -> Optional[InvoiceLookupJob]:
        """Obtiene una copia del trabajo solicitado."""

        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return dataclasses.replace(job)

    async def _run_job(self, job_id: str, document_number: str) -> None:
        await self._update_job(
            job_id,
            status=InvoiceLookupJobStatus.RUNNING,
            stage="starting",
            progress=5,
        )
        loop = self._loop or asyncio.get_running_loop()
        progress_callback = self._create_progress_callback(job_id, loop)

        try:
            result = await asyncio.to_thread(
                self._execute_lookup,
                document_number,
                progress_callback,
            )
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
        else:
            await self._update_job(
                job_id,
                status=InvoiceLookupJobStatus.COMPLETED,
                stage="completed",
                progress=100,
                result=result,
            )

    def _execute_lookup(
        self,
        document_number: str,
        progress_callback: Callable[[str, Dict[str, Any]], None],
    ) -> Dict[str, Any]:
        client = self._client_factory()
        invoice = client.find_invoice_by_document_number(
            document_number,
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

    async def _update_job(self, job_id: str, **changes: Any) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for field_name, value in changes.items():
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
