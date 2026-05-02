from pathlib import Path
from uuid import uuid4
from threading import Lock, Thread

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from ..dependencies import get_contifico_client
from ..contifico import ContificoClient
from .service import OdooMigrationService

router = APIRouter(prefix="/odoo-migration", tags=["Odoo Migration"])

EXPORT_JOBS: dict[str, dict] = {}
EXPORT_LOCK = Lock()


def _output_root() -> Path:
    return Path("backend/data/odoo_migration")


def _set_job(job_id: str, payload: dict):
    with EXPORT_LOCK:
        EXPORT_JOBS[job_id] = {**EXPORT_JOBS.get(job_id, {}), **payload}


@router.post("/products-stock/export")
def export_products_stock(
    page_size: int = Query(default=200, ge=1, le=500),
    max_pages: int = Query(default=50, ge=1, le=500),
    contifico_client: ContificoClient = Depends(get_contifico_client),
):
    service = OdooMigrationService(contifico_client)
    output = service.generate_products_and_stock_csv(page_size=page_size, max_pages=max_pages)
    run_id = output.folder.name
    return {
        "run_id": run_id,
        "folder": str(output.folder),
        "files": {
            "product_product_csv": f"/odoo-migration/runs/{run_id}/files/product_product.csv",
            "initial_stock_csv": f"/odoo-migration/runs/{run_id}/files/initial_stock.csv",
            "migration_errors_csv": f"/odoo-migration/runs/{run_id}/files/migration_errors.csv",
            "mapping_report_csv": f"/odoo-migration/runs/{run_id}/files/mapping_report.csv",
        },
        "total_products": output.total_products,
        "total_errors": output.total_errors,
    }


@router.post("/products-stock/export-jobs")
def start_export_job(
    page_size: int = Query(default=200, ge=1, le=500),
    max_pages: int = Query(default=50, ge=1, le=500),
    contifico_client: ContificoClient = Depends(get_contifico_client),
):
    job_id = str(uuid4())
    _set_job(job_id, {"status": "running", "stage": "queued", "found_items": 0, "processed_items": 0})

    def worker():
        try:
            service = OdooMigrationService(contifico_client)
            output = service.generate_products_and_stock_csv(
                page_size=page_size,
                max_pages=max_pages,
                progress_callback=lambda p: _set_job(job_id, p),
            )
            run_id = output.folder.name
            _set_job(job_id, {
                "status": "completed",
                "run_id": run_id,
                "files": {
                    "product_product_csv": f"/odoo-migration/runs/{run_id}/files/product_product.csv",
                    "initial_stock_csv": f"/odoo-migration/runs/{run_id}/files/initial_stock.csv",
                    "migration_errors_csv": f"/odoo-migration/runs/{run_id}/files/migration_errors.csv",
                    "mapping_report_csv": f"/odoo-migration/runs/{run_id}/files/mapping_report.csv",
                },
                "total_products": output.total_products,
                "total_errors": output.total_errors,
            })
        except Exception as exc:  # pragma: no cover
            _set_job(job_id, {"status": "failed", "error": str(exc)})

    Thread(target=worker, daemon=True).start()
    return {"job_id": job_id, "status": "running"}


@router.get("/products-stock/export-jobs/{job_id}")
def get_export_job(job_id: str):
    with EXPORT_LOCK:
        payload = EXPORT_JOBS.get(job_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return payload


@router.get("/runs")
def list_runs(limit: int = Query(default=10, ge=1, le=100)):
    root = _output_root()
    if not root.exists():
        return {"runs": []}
    runs = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)[:limit]
    return {"runs": [r.name for r in runs]}


@router.get("/runs/{run_id}/files/{filename}")
def download_file(run_id: str, filename: str):
    allowed = {"product_product.csv", "initial_stock.csv", "migration_errors.csv", "mapping_report.csv"}
    if filename not in allowed:
        raise HTTPException(status_code=400, detail="Archivo no permitido")
    file_path = _output_root() / run_id / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(path=file_path, filename=filename, media_type="text/csv")
