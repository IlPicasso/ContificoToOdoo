import asyncio
import time
from typing import Callable

from app.contifico import ContificoTransportError
from app.invoice_jobs import (
    InvoiceLookupJobManager,
    InvoiceLookupJobStatus,
)


class FakeClient:
    def __init__(
        self,
        *,
        invoice: dict | None = None,
        exception_factory: Callable[[], Exception] | None = None,
    ) -> None:
        self._invoice = invoice
        self._exception_factory = exception_factory

    def find_invoice_by_document_number(self, document_number: str, *, progress_callback=None):
        if progress_callback:
            progress_callback("start", {"progress": 5, "document_number": document_number})
        if self._exception_factory is not None:
            raise self._exception_factory()
        if self._invoice is None:
            if progress_callback:
                progress_callback("not_found", {"progress": 100})
            return None
        if progress_callback:
            progress_callback("direct_lookup_success", {"progress": 100})
        return dict(self._invoice)


async def wait_for_completion(manager: InvoiceLookupJobManager, job_id: str) -> object:
    for _ in range(100):
        job = await manager.get_job(job_id)
        if job and job.status in (
            InvoiceLookupJobStatus.COMPLETED,
            InvoiceLookupJobStatus.FAILED,
        ):
            return job
        await asyncio.sleep(0.01)
    raise AssertionError("El trabajo no finalizó a tiempo")


def test_invoice_lookup_job_manager_completes_successfully() -> None:
    manager = InvoiceLookupJobManager(
        client_factory=lambda: FakeClient(
            invoice={"id": 1, "numero": "001-001-0000009"}
        )
    )

    async def scenario() -> object:
        job = await manager.start_job("001-001-0000009")
        return await wait_for_completion(manager, job.id)

    final_job = asyncio.run(scenario())

    assert final_job.status == InvoiceLookupJobStatus.COMPLETED
    assert final_job.progress == 100
    assert final_job.stage == "completed"
    assert final_job.result == {"id": 1, "numero": "001-001-0000009"}
    assert final_job.metadata.get("document_number") == "001-001-0000009"


def test_invoice_lookup_job_manager_marks_not_found() -> None:
    manager = InvoiceLookupJobManager(client_factory=lambda: FakeClient(invoice=None))

    async def scenario() -> object:
        job = await manager.start_job("001-001-0000999")
        return await wait_for_completion(manager, job.id)

    final_job = asyncio.run(scenario())

    assert final_job.status == InvoiceLookupJobStatus.FAILED
    assert final_job.stage == "not_found"
    assert "No se encontró" in (final_job.error or "")
    assert final_job.progress == 100


def test_invoice_lookup_job_manager_reports_transport_error() -> None:
    manager = InvoiceLookupJobManager(
        client_factory=lambda: FakeClient(
            exception_factory=lambda: ContificoTransportError("falló")
        )
    )

    async def scenario() -> object:
        job = await manager.start_job("001-001-0000123")
        return await wait_for_completion(manager, job.id)

    final_job = asyncio.run(scenario())

    assert final_job.status == InvoiceLookupJobStatus.FAILED
    assert final_job.stage == "error"
    assert final_job.error == "falló"


def test_invoice_lookup_job_manager_times_out_long_running_job() -> None:
    class SlowClient:
        def find_invoice_by_document_number(self, document_number: str, *, progress_callback=None):
            if progress_callback:
                progress_callback("start", {"progress": 5, "document_number": document_number})
            time.sleep(0.05)
            if progress_callback:
                progress_callback("direct_lookup_success", {"progress": 100})
            return {"numero": document_number}

    manager = InvoiceLookupJobManager(
        client_factory=lambda: SlowClient(),
        max_job_duration=0.01,
    )

    async def scenario() -> object:
        job = await manager.start_job("001-001-0000001")
        return await wait_for_completion(manager, job.id)

    final_job = asyncio.run(scenario())

    assert final_job.status == InvoiceLookupJobStatus.FAILED
    assert final_job.stage == "timeout"
    assert "tiempo" in (final_job.error or "").lower()
