import json
import xmlrpc.client
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from ..contifico import ContificoClient
from ..dependencies import get_contifico_client
from .rules import CATEGORY_ALIASES
from .service import OdooMigrationService
from .stock_worker import StockWorker

router = APIRouter(prefix="/odoo-migration", tags=["Odoo Migration"])

EXPORT_JOBS: dict[str, dict] = {}
EXPORT_LOCK = Lock()

STOCK_JOBS: dict[str, dict] = {}
STOCK_WORKERS: dict[str, StockWorker] = {}


def _stock_status(run_id: str) -> dict:
    return STOCK_JOBS.get(run_id, {"status": "idle", "run_id": run_id})



def _output_root() -> Path:
    return Path("backend/data/odoo_migration")


def _set_job(job_id: str, payload: dict) -> None:
    with EXPORT_LOCK:
        EXPORT_JOBS[job_id] = {**EXPORT_JOBS.get(job_id, {}), **payload}


def _build_files(run_id: str) -> dict[str, str]:
    return {
        "product_product_csv": f"/odoo-migration/runs/{run_id}/files/product_product.csv",
        "initial_stock_csv": f"/odoo-migration/runs/{run_id}/files/initial_stock.csv",
        "stock_quant_csv": f"/odoo-migration/runs/{run_id}/files/stock_quant.csv",
        "migration_errors_csv": f"/odoo-migration/runs/{run_id}/files/migration_errors.csv",
        "mapping_report_csv": f"/odoo-migration/runs/{run_id}/files/mapping_report.csv",
        "excluded_zero_stock_csv": f"/odoo-migration/runs/{run_id}/files/excluded_zero_stock.csv",
        "debug_log": f"/odoo-migration/runs/{run_id}/files/debug.log",
        "raw_log": f"/odoo-migration/runs/{run_id}/files/raw.log",
    }


@router.get('/odoo-attributes/precheck')
def precheck_odoo_attributes(
    odoo_url: str = Query(..., description='Base URL Odoo, e.g. https://mycompany.odoo.com'),
    odoo_db: str = Query(...),
    odoo_username: str = Query(...),
    odoo_api_key: str = Query(...),
):
    base_url = odoo_url.rstrip('/')
    common = xmlrpc.client.ServerProxy(f"{base_url}/xmlrpc/2/common")
    uid = common.authenticate(odoo_db, odoo_username, odoo_api_key, {})
    if not uid:
        raise HTTPException(status_code=400, detail='No fue posible autenticar en Odoo (db/usuario/api key).')
    models = xmlrpc.client.ServerProxy(f"{base_url}/xmlrpc/2/object")

    attr_names = ['Talla', 'Manga de Camisa', 'Ancho de Corbata', 'Marca', 'Color']
    attrs = models.execute_kw(
        odoo_db, uid, odoo_api_key,
        'product.attribute', 'search_read',
        [[('name', 'in', attr_names)]],
        {'fields': ['id', 'name']}
    )
    by_name = {a.get('name'): a for a in attrs}
    missing = [n for n in attr_names if n not in by_name]

    expected_categories = sorted(set(CATEGORY_ALIASES.values()) | {
        'Ropa / Ternos', 'Ropa / Camisas', 'Ropa / Corbatas', 'Ropa / Hombres / Zapatos', 'Ropa / Mujeres / Zapatos'
    })
    cat_rows = models.execute_kw(
        odoo_db, uid, odoo_api_key,
        'product.category', 'search_read',
        [[]],
        {'fields': ['name', 'complete_name'], 'limit': 2000}
    )
    existing_categories = {str(c.get('name') or '').strip() for c in cat_rows if c.get('name')}
    existing_complete = {str(c.get('complete_name') or '').strip() for c in cat_rows if c.get('complete_name')}
    missing_categories = [c for c in expected_categories if c not in existing_categories and c not in existing_complete]
    recommendations = []
    if missing:
        recommendations.append('Crear atributos faltantes en Odoo > Inventario > Configuración > Atributos.')
    if missing_categories:
        recommendations.append('Crear categorías faltantes en Odoo > Inventario > Configuración > Categorías de producto.')
    if missing:
        recommendations.append('Mientras no existan atributos, exportar con include_brand_color_attributes=false.')
    if not missing and not missing_categories:
        recommendations.append('Atributos listos. Puedes exportar con include_brand_color_attributes=true.')
    return {
        'connected': True,
        'odoo_url': base_url,
        'odoo_db': odoo_db,
        'attributes_found': sorted(list(by_name.keys())),
        'attributes_missing': missing,
        'categories_missing': missing_categories,
        'total_categories_expected': len(expected_categories),
        'can_enable_brand_color_export': len([a for a in ['Marca', 'Color'] if a in missing]) == 0,
        'ready_for_product_import': len(missing_categories) == 0,
        'recommended_include_brand_color_attributes': len([a for a in ['Marca', 'Color'] if a in missing]) == 0,
        'recommendations': recommendations,
    }


@router.post("/products-stock/export")
def export_products_stock(
    page_size: int = Query(default=200, ge=1, le=500),
    max_pages: int = Query(default=200, ge=1, le=1000),
    export_stock: bool = Query(default=False),
    include_brand_color_attributes: bool = Query(default=False),
    contifico_client: ContificoClient = Depends(get_contifico_client),
):
    service = OdooMigrationService(contifico_client)
    output = service.generate_products_and_stock_csv(
        page_size=page_size,
        max_pages=max_pages,
        export_stock=export_stock,
        include_brand_color_attributes=include_brand_color_attributes,
    )
    run_id = output.folder.name
    return {
        "run_id": run_id,
        "folder": str(output.folder),
        "files": _build_files(run_id),
        "total_products": output.total_products,
        "total_errors": output.total_errors,
        "summary": output.summary,
        "pages_fetched": output.pages_fetched,
        "hit_max_pages": output.hit_max_pages,
    }


@router.post("/products-stock/export-jobs")
def start_export_job(
    page_size: int = Query(default=200, ge=1, le=500),
    max_pages: int = Query(default=200, ge=1, le=1000),
    export_stock: bool = Query(default=False),
    include_brand_color_attributes: bool = Query(default=False),
    contifico_client: ContificoClient = Depends(get_contifico_client),
):
    job_id = str(uuid4())
    _set_job(job_id, {"status": "running", "stage": "queued", "found_items": 0, "processed_items": 0})

    def worker() -> None:
        try:
            service = OdooMigrationService(contifico_client)
            output = service.generate_products_and_stock_csv(
                page_size=page_size,
                max_pages=max_pages,
                export_stock=export_stock,
                include_brand_color_attributes=include_brand_color_attributes,
                progress_callback=lambda p: _set_job(job_id, p),
            )
            run_id = output.folder.name
            _set_job(
                job_id,
                {
                    "status": "completed",
                    "run_id": run_id,
                    "files": _build_files(run_id),
                    "total_products": output.total_products,
                    "total_errors": output.total_errors,
                    "summary": output.summary,
                    "pages_fetched": output.pages_fetched,
                    "hit_max_pages": output.hit_max_pages,
                },
            )
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
    allowed = {
        "product_product.csv",
        "initial_stock.csv",
        "stock_quant.csv",
        "migration_errors.csv",
        "mapping_report.csv",
        "excluded_zero_stock.csv",
        "debug.log",
        "raw.log",
        "stock_errors.csv",
    }
    if filename not in allowed:
        raise HTTPException(status_code=400, detail="Archivo no permitido")
    file_path = _output_root() / run_id / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    media_type = "text/plain" if filename.endswith('.log') else "text/csv"
    return FileResponse(path=file_path, filename=filename, media_type=media_type)


@router.post('/runs/{run_id}/stock/start')
def start_stock_worker(run_id: str, contifico_client: ContificoClient = Depends(get_contifico_client)):
    root = _output_root(); run_folder = root / run_id
    if not run_folder.exists():
        raise HTTPException(status_code=404, detail='Run no encontrado')
    if _stock_status(run_id).get('status') == 'running':
        return _stock_status(run_id)

    worker = StockWorker(run_id, contifico_client, root)
    STOCK_WORKERS[run_id] = worker
    STOCK_JOBS[run_id] = {"status": "running", "run_id": run_id, "started_at": datetime.utcnow().isoformat()+'Z'}

    def _run() -> None:
        try:
            metrics = worker.run(retry_failed=False)
            STOCK_JOBS[run_id] = {**STOCK_JOBS.get(run_id, {}), **metrics, "status": "completed", "updated_at": datetime.utcnow().isoformat()+'Z'}
        except Exception as exc:  # pragma: no cover
            STOCK_JOBS[run_id] = {**STOCK_JOBS.get(run_id, {}), "status": "failed", "error": str(exc), "updated_at": datetime.utcnow().isoformat()+'Z'}

    Thread(target=_run, daemon=True).start()
    return STOCK_JOBS[run_id]


@router.get('/runs/{run_id}/stock/status')
def stock_status(run_id: str):
    root = _output_root(); state_path = root / run_id / 'stock_state.json'
    if not state_path.exists():
        raise HTTPException(status_code=404, detail='Run sin estado de stock')
    data = json.loads(state_path.read_text(encoding='utf-8'))
    total = len(data); done = len([r for r in data if r.get('status')=='done']); failed = len([r for r in data if r.get('status')=='error']); pending = len([r for r in data if r.get('status')=='pending'])
    pct = (done/total*100) if total else 0.0
    payload = {"run_id": run_id, "total": total, "done": done, "failed": failed, "pending": pending, "percent": round(pct,2)}
    return {**payload, **_stock_status(run_id)}


@router.post('/runs/{run_id}/stock/retry-failed')
def retry_failed_stock(run_id: str, contifico_client: ContificoClient = Depends(get_contifico_client)):
    root = _output_root(); run_folder = root / run_id
    if not run_folder.exists():
        raise HTTPException(status_code=404, detail='Run no encontrado')
    worker = StockWorker(run_id, contifico_client, root)
    STOCK_WORKERS[run_id] = worker
    STOCK_JOBS[run_id] = {"status": "running", "run_id": run_id, "mode": "retry_failed", "started_at": datetime.utcnow().isoformat()+'Z'}

    def _run() -> None:
        try:
            metrics = worker.run(retry_failed=True)
            STOCK_JOBS[run_id] = {**STOCK_JOBS.get(run_id, {}), **metrics, "status": "completed", "updated_at": datetime.utcnow().isoformat()+'Z'}
        except Exception as exc:  # pragma: no cover
            STOCK_JOBS[run_id] = {**STOCK_JOBS.get(run_id, {}), "status": "failed", "error": str(exc), "updated_at": datetime.utcnow().isoformat()+'Z'}

    Thread(target=_run, daemon=True).start()
    return STOCK_JOBS[run_id]


@router.post('/runs/{run_id}/stock/pause')
def pause_stock(run_id: str):
    w = STOCK_WORKERS.get(run_id)
    if not w:
        raise HTTPException(status_code=404, detail='Worker no encontrado')
    w.pause(); STOCK_JOBS[run_id] = {**STOCK_JOBS.get(run_id, {}), 'status': 'paused'}
    return STOCK_JOBS[run_id]


@router.post('/runs/{run_id}/stock/resume')
def resume_stock(run_id: str):
    w = STOCK_WORKERS.get(run_id)
    if not w:
        raise HTTPException(status_code=404, detail='Worker no encontrado')
    w.resume(); STOCK_JOBS[run_id] = {**STOCK_JOBS.get(run_id, {}), 'status': 'running'}
    return STOCK_JOBS[run_id]
