from __future__ import annotations
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..contifico import ContificoClient
from .parser import parse_adams_sku, make_external_id

WAREHOUSE_TO_LOCATION = {
    "BPU": "BPU/Existencias",
    "TUR": "TUR/Existencias",
    "BAT": "BAT/Existencias",
}

PRODUCT_COLUMNS = [
    "External ID","Name","Product Type","Internal Reference","Barcode","Sales Price",
    "Cost","Weight","Sales Description","Product Values"
]
STOCK_COLUMNS = ["sku","ubicacion_odoo","cantidad","costo_unitario"]
ERROR_COLUMNS = ["sku","nombre_contifico","problema","sugerencia"]
TEMPLATE_PRODUCT_PATH = Path(__file__).resolve().parents[3] / "docs/odoo_import_templates/adams_product_template.csv"
TEMPLATE_STOCK_PATH = Path(__file__).resolve().parents[3] / "docs/odoo_import_templates/adams_stock_template.csv"

MAP_COLUMNS = ["sku","nombre_contifico","producto_madre_detectado","categoria_odoo_detectada","talla_detectada","manga_detectada","marca_detectada","color_detectado","barcode","precio","costo","stock_bpu","stock_tur","stock_bat","estado"]

@dataclass
class MigrationOutput:
    folder: Path
    product_csv: Path
    stock_csv: Path
    errors_csv: Path
    mapping_csv: Path
    total_products: int
    total_errors: int


class OdooMigrationService:
    def __init__(self, client: ContificoClient, output_root: str | Path = "backend/data/odoo_migration"):
        self.client = client
        self.output_root = Path(output_root)

    def generate_products_and_stock_csv(self, *, page_size: int = 200, max_pages: int = 50, progress_callback: Callable[[dict[str, Any]], None] | None = None) -> MigrationOutput:
        self._validate_templates()
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        folder = self.output_root / timestamp
        folder.mkdir(parents=True, exist_ok=True)
        product_csv = folder / "product_product.csv"
        stock_csv = folder / "initial_stock.csv"
        errors_csv = folder / "migration_errors.csv"
        mapping_csv = folder / "mapping_report.csv"

        products = self._fetch_products(page_size=page_size, max_pages=max_pages, progress_callback=progress_callback)

        product_rows, stock_rows, error_rows, map_rows = [], [], [], []
        seen_skus, seen_barcodes = set(), set()
        total = len(products)
        for idx, item in enumerate(products, start=1):
            sku = str(item.get("codigo") or item.get("sku") or "").strip()
            name = str(item.get("nombre") or item.get("name") or "")
            barcode = str(item.get("codigo_barra") or item.get("barcode") or "").strip()
            price = float(item.get("pvp1") or item.get("precio") or 0)
            cost = float(item.get("costo_promedio") or item.get("costo") or 0)
            brand = str(item.get("marca") or "BRUNO CASSINI").strip() or "BRUNO CASSINI"
            color = str(item.get("color") or "").strip()
            stock_map = self._extract_stock_by_warehouse(item)
            try:
                parsed = parse_adams_sku(sku)
                if sku in seen_skus:
                    raise ValueError("SKU duplicado")
                if barcode and barcode in seen_barcodes:
                    raise ValueError("Código de barras duplicado")
                seen_skus.add(sku)
                if barcode:
                    seen_barcodes.add(barcode)
                pvalues = [f"Talla:{parsed.talla}"]
                if parsed.manga:
                    pvalues.append(f"Manga de Camisa:{parsed.manga}")
                pvalues += [f"Marca:{brand}", f"Color:{color}"]
                product_rows.append({
                    "External ID": make_external_id(parsed),
                    "Name": parsed.product_name,
                    "Product Type": "Goods",
                    "Internal Reference": sku,
                    "Barcode": barcode,
                    "Sales Price": f"{price:.2f}",
                    "Cost": f"{cost:.2f}",
                    "Weight": "0.0",
                    "Sales Description": "",
                    "Product Values": ",".join(pvalues),
                })
                for wh, location in WAREHOUSE_TO_LOCATION.items():
                    qty = float(stock_map.get(wh, 0) or 0)
                    stock_rows.append({"sku": sku, "ubicacion_odoo": location, "cantidad": f"{qty:.2f}", "costo_unitario": f"{cost:.2f}"})
                status = "ok"
            except ValueError as exc:
                error_rows.append({"sku": sku, "nombre_contifico": name, "problema": str(exc), "sugerencia": "Revisar formato SKU/código de barras/categoría"})
                parsed = None
                status = "error"
            map_rows.append({
                "sku": sku,
                "nombre_contifico": name,
                "producto_madre_detectado": parsed.product_name if parsed else "",
                "categoria_odoo_detectada": parsed.category_odoo if parsed else "",
                "talla_detectada": parsed.talla if parsed else "",
                "manga_detectada": parsed.manga if parsed else "",
                "marca_detectada": brand,
                "color_detectado": color,
                "barcode": barcode,
                "precio": f"{price:.2f}",
                "costo": f"{cost:.2f}",
                "stock_bpu": f"{float(stock_map.get('BPU',0)):.2f}",
                "stock_tur": f"{float(stock_map.get('TUR',0)):.2f}",
                "stock_bat": f"{float(stock_map.get('BAT',0)):.2f}",
                "estado": status,
            })
            if progress_callback and (idx == 1 or idx % 25 == 0 or idx == total):
                progress_callback({"stage": "processing", "processed_items": idx, "total_items": total})

        self._write_csv(product_csv, PRODUCT_COLUMNS, product_rows)
        self._write_csv(stock_csv, STOCK_COLUMNS, stock_rows)
        self._write_csv(errors_csv, ERROR_COLUMNS, error_rows)
        self._write_csv(mapping_csv, MAP_COLUMNS, map_rows)
        if progress_callback:
            progress_callback({"stage": "completed", "processed_items": total, "total_items": total})
        return MigrationOutput(folder, product_csv, stock_csv, errors_csv, mapping_csv, len(product_rows), len(error_rows))


    @staticmethod
    def _read_header(path: Path) -> list[str]:
        if not path.exists():
            raise FileNotFoundError(f"No existe plantilla: {path}")
        with path.open("r", encoding="utf-8") as f:
            line = f.readline().strip()
        return [c.strip() for c in line.split(",") if c.strip()]

    def _validate_templates(self) -> None:
        expected = self._read_header(TEMPLATE_PRODUCT_PATH)
        if expected != PRODUCT_COLUMNS:
            raise ValueError(
                "Las columnas de product_product.csv no coinciden con la plantilla Odoo. "
                f"Esperado={expected} Actual={PRODUCT_COLUMNS}"
            )
        expected_stock = self._read_header(TEMPLATE_STOCK_PATH)
        if expected_stock != STOCK_COLUMNS:
            raise ValueError(
                "Las columnas de initial_stock.csv no coinciden con la plantilla Odoo. "
                f"Esperado={expected_stock} Actual={STOCK_COLUMNS}"
            )

    def _fetch_products(self, *, page_size: int, max_pages: int, progress_callback: Callable[[dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
        all_items = []
        for page in range(1, max_pages + 1):
            if progress_callback:
                progress_callback({"stage": "fetching", "page": page, "max_pages": max_pages, "found_items": len(all_items)})
            batch = list(self.client.list_products(page=page, page_size=page_size))
            if not batch:
                break
            all_items.extend([b for b in batch if isinstance(b, dict)])
            if progress_callback:
                progress_callback({"stage": "fetched_page", "page": page, "fetched": len(batch), "found_items": len(all_items)})
            if len(batch) < page_size:
                break
        return all_items

    @staticmethod
    def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    @staticmethod
    def _extract_stock_by_warehouse(item: dict[str, Any]) -> dict[str, float]:
        result = {"BPU": 0.0, "TUR": 0.0, "BAT": 0.0}
        raw = item.get("bodegas") or item.get("stock_por_bodega") or []
        if isinstance(raw, dict):
            for key in result:
                if key in raw:
                    result[key] = float(raw.get(key) or 0)
            return result
        if isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                code = str(entry.get("codigo") or entry.get("siglas") or entry.get("bodega") or "").upper()
                qty = float(entry.get("cantidad") or entry.get("stock") or 0)
                for key in result:
                    if key in code:
                        result[key] = qty
        return result
