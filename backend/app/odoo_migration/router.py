import json
import xmlrpc.client
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse

from ..contifico import ContificoClient
from ..dependencies import get_contifico_client
from ..config import get_settings
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
        "templates_with_existing_attributes_csv": f"/odoo-migration/runs/{run_id}/files/01_product_templates_with_existing_attributes.csv",
        "variant_update_map_csv": f"/odoo-migration/runs/{run_id}/files/02_variant_update_map.csv",
        "stock_quant_by_variant_csv": f"/odoo-migration/runs/{run_id}/files/03_stock_quant_by_variant.csv",
        "missing_attribute_values_csv": f"/odoo-migration/runs/{run_id}/files/04_missing_attribute_values_report.csv",
        "products_variants_report_md": f"/odoo-migration/runs/{run_id}/files/import_products_and_variants_report.md",
        "debug_log": f"/odoo-migration/runs/{run_id}/files/debug.log",
        "raw_log": f"/odoo-migration/runs/{run_id}/files/raw.log",
    }


def _build_service(contifico_client: ContificoClient) -> OdooMigrationService:
    settings = get_settings()
    return OdooMigrationService(
        contifico_client,
        page_delay_seconds=settings.contifico_products_page_delay_seconds,
        page_retry_attempts=settings.contifico_products_page_retry_attempts,
        page_retry_backoff_base_seconds=settings.contifico_products_page_retry_backoff_base_seconds,
        page_retry_jitter_seconds=settings.contifico_products_page_retry_jitter_seconds,
    )


def _snapshot_path() -> Path:
    return Path(__file__).resolve().parents[3] / 'config/odoo_catalog_snapshot.json'


def _extract_attribute_name(raw: str) -> str:
    value = (raw or '').strip().strip('"')
    if not value:
        return ''
    parts = [p.strip() for p in value.split(',')]
    if len(parts) >= 2 and parts[0].isdigit():
        return parts[1]
    if value.lower() in {'secuencia,atributo,tipo de visualizacion,creacion de variantes', 'secuencia,atributo,tipo de visualización,creación de variantes'}:
        return ''
    return value


def _category_present(expected: str, current_categories: set[str]) -> bool:
    if expected in current_categories:
        return True
    if expected in {'Ropa / Camisas', 'Ropa / Corbatas', 'Ropa / Ternos'}:
        leaf = expected.split('/')[-1].strip()
        return any(c.endswith(f'/ {leaf}') for c in current_categories)
    return False


@router.post('/odoo-attributes/snapshot/upload')
async def upload_odoo_snapshot_csv(kind: str = Query(..., pattern='^(attributes|categories)$'), file: UploadFile = File(...)):
    raw = await file.read()
    text = raw.decode('utf-8-sig', errors='ignore')
    values: list[str] = []
    for line in text.splitlines():
        value = line.strip().strip('"')
        if not value:
            continue
        lowered = value.lower()
        if lowered in {'name', 'nombre', 'attribute', 'categoria', 'category'}:
            continue
        values.append(value)
    if not values:
        raise HTTPException(status_code=400, detail='CSV vacío o sin valores válidos.')

    snapshot_path = _snapshot_path()
    snapshot = {'attributes': [], 'categories': []}
    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    snapshot[kind] = sorted(list(dict.fromkeys(values)))
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'ok': True, 'kind': kind, 'count': len(snapshot[kind]), 'snapshot_path': str(snapshot_path)}


@router.get('/odoo-attributes/precheck-offline')
def precheck_odoo_attributes_offline():
    snapshot_path = _snapshot_path()
    if not snapshot_path.exists():
        raise HTTPException(status_code=404, detail='No existe config/odoo_catalog_snapshot.json')
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    current_attrs = {_extract_attribute_name(str(a)) for a in snapshot.get('attributes', []) if _extract_attribute_name(str(a))}
    current_cats = {str(c).strip() for c in snapshot.get('categories', []) if str(c).strip()}

    expected_attrs = {'Talla', 'Manga de Camisa', 'Ancho Corbata', 'Marca', 'Color'}
    alias_attr = {'Ancho de Corbata': 'Ancho Corbata'}
    normalized_current_attrs = {alias_attr.get(a, a) for a in current_attrs}
    missing_attrs = sorted(list(expected_attrs - normalized_current_attrs))

    expected_categories = sorted(set(CATEGORY_ALIASES.values()) | {
        'Ropa / Ternos', 'Ropa / Camisas', 'Ropa / Corbatas', 'Ropa / Hombres / Zapatos', 'Ropa / Mujeres / Zapatos'
    })
    missing_categories = [c for c in expected_categories if not _category_present(c, current_cats)]
    recommendations = []
    if missing_attrs:
        recommendations.append('Crear atributos faltantes en Odoo según attributes_missing.')
    if missing_categories:
        recommendations.append('Crear categorías faltantes en Odoo según categories_missing.')
    if not missing_attrs and not missing_categories:
        recommendations.append('Catálogo local completo. Puedes exportar con include_additional_attributes=true.')
    return {
        'mode': 'offline_catalog_snapshot',
        'snapshot_path': str(snapshot_path),
        'attributes_current_total': len(current_attrs),
        'categories_current_total': len(current_cats),
        'attributes_missing': missing_attrs,
        'categories_missing': missing_categories,
        'can_enable_brand_color_export': all(a not in missing_attrs for a in ('Marca', 'Color')),
        'ready_for_product_import': len(missing_categories) == 0,
        'recommendations': recommendations,
    }


@router.post("/products-stock/export")
def export_products_stock(
    page_size: int = Query(default=100, ge=1, le=500),
    max_pages: int = Query(default=300, ge=1, le=1000),
    export_stock: bool = Query(default=False),
    include_additional_attributes: bool = Query(default=False),
    include_brand_color_attributes: bool = Query(default=False),
    contifico_client: ContificoClient = Depends(get_contifico_client),
):
    service = _build_service(contifico_client)
    output = service.generate_products_and_stock_csv(
        page_size=page_size,
        max_pages=max_pages,
        export_stock=export_stock,
        include_additional_attributes=(include_additional_attributes or include_brand_color_attributes),
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


@router.post("/products-stock/process-raw-upload")
async def process_raw_upload(
    file: UploadFile = File(...),
    include_additional_attributes: bool = Query(default=False),
    export_stock: bool = Query(default=False),
    contifico_client: ContificoClient = Depends(get_contifico_client),
):
    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="ignore")
    products: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("response"), list):
            products.extend([x for x in payload["response"] if isinstance(x, dict)])
        elif isinstance(payload, list):
            products.extend([x for x in payload if isinstance(x, dict)])
        elif isinstance(payload, dict) and "codigo" in payload:
            products.append(payload)
    if not products:
        raise HTTPException(status_code=400, detail="No se detectaron productos válidos en el archivo.")
    service = _build_service(contifico_client)
    output = service.generate_products_and_stock_csv_from_items(
        products=products,
        export_stock=export_stock,
        include_additional_attributes=include_additional_attributes,
    )
    run_id = output.folder.name
    return {
        "run_id": run_id,
        "source": "uploaded_raw_json",
        "detected_products": len(products),
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
    page_size: int = Query(default=100, ge=1, le=500),
    max_pages: int = Query(default=300, ge=1, le=1000),
    export_stock: bool = Query(default=False),
    include_additional_attributes: bool = Query(default=False),
    include_brand_color_attributes: bool = Query(default=False),
    contifico_client: ContificoClient = Depends(get_contifico_client),
):
    job_id = str(uuid4())
    _set_job(job_id, {"status": "running", "stage": "queued", "found_items": 0, "processed_items": 0})

    def worker() -> None:
        try:
            service = _build_service(contifico_client)
            output = service.generate_products_and_stock_csv(
                page_size=page_size,
                max_pages=max_pages,
                export_stock=export_stock,
                include_additional_attributes=(include_additional_attributes or include_brand_color_attributes),
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
        "01_product_templates_with_existing_attributes.csv",
        "02_variant_update_map.csv",
        "03_stock_quant_by_variant.csv",
        "04_missing_attribute_values_report.csv",
        "import_products_and_variants_report.md",
    }
    if filename not in allowed:
        raise HTTPException(status_code=400, detail="Archivo no permitido")
    file_path = _output_root() / run_id / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    media_type = "text/plain" if filename.endswith(('.log', '.md')) else "text/csv"
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
