from __future__ import annotations
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
import json

from ..contifico import ContificoClient
from .rules import (
    detect_brand, detect_color, detect_category, calculate_total_stock, should_exclude_zero_stock,
    parse_shirt_sku, parse_suit_sku, parse_blazer_sku, parse_tie_sku, parse_bowtie_sku, parse_fajin_sku,
    parse_generic_size, build_product_values, build_external_id, build_mapping_report_row,
    build_error_row, build_zero_stock_exclusion_row,
)

WAREHOUSE_TO_LOCATION = {"BPU": "BPU/Existencias", "TUR": "TUR/Existencias", "BAT": "BAT/Existencias"}
PRODUCT_COLUMNS = ["External ID","Name","Product Type","Product Category","Internal Reference","Barcode","Sales Price","Cost","Weight","Sales Description","Product Values"]
STOCK_COLUMNS = ["sku","ubicacion_odoo","cantidad","costo_unitario"]
MAP_COLUMNS = ["sku","nombre_contifico","producto_madre_detectado","categoria_odoo_detectada","talla_detectada","manga_detectada","ancho_corbata_detectado","marca_detectada","color_detectado","barcode","precio","costo","stock_bpu","stock_tur","stock_bat","stock_total_contifico","estado","confidence","parser_rule"]
ERROR_COLUMNS = ["sku","nombre_contifico","problema","sugerencia","raw_categoria_id","raw_marca_nombre","raw_codigo_barra"]
EXCLUDED_ZERO_COLUMNS = ["sku","nombre_contifico","codigo_barra","categoria_id","marca_nombre","pvp1","costo","stock_total_contifico","estado_contifico","motivo_exclusion"]
TEMPLATE_PRODUCT_PATH = Path(__file__).resolve().parents[3] / "docs/odoo_import_templates/adams_products_template.csv"
TEMPLATE_STOCK_PATH = Path(__file__).resolve().parents[3] / "docs/odoo_import_templates/adams_stock_template.csv"

@dataclass
class MigrationOutput:
    folder: Path; product_csv: Path; stock_csv: Path; errors_csv: Path; mapping_csv: Path; excluded_zero_csv: Path
    total_products: int; total_errors: int; pages_fetched: int; hit_max_pages: bool; debug_log: Path; raw_log: Path; summary: dict[str, Any]

class OdooMigrationService:
    def __init__(self, client: ContificoClient, output_root: str | Path = "backend/data/odoo_migration"):
        self.client = client; self.output_root = Path(output_root)

    def generate_products_and_stock_csv(self, *, page_size=200, max_pages=200, export_stock: bool = False, progress_callback: Callable[[dict[str, Any]], None] | None = None) -> MigrationOutput:
        self._validate_templates()
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S'); folder = self.output_root / ts; folder.mkdir(parents=True, exist_ok=True)
        product_csv=folder/'product_product.csv'; stock_csv=folder/'initial_stock.csv'; errors_csv=folder/'migration_errors.csv'; mapping_csv=folder/'mapping_report.csv'; excluded_zero_csv=folder/'excluded_zero_stock.csv'; debug_log=folder/'debug.log'; raw_log=folder/'raw.log'
        debug_lines=[f'start={datetime.utcnow().isoformat()}Z',f'page_size={page_size}',f'max_pages={max_pages}',f'export_stock={export_stock}']; raw_lines=[]
        products,pages_fetched,hit_max_pages=self._fetch_products(page_size=page_size,max_pages=max_pages,progress_callback=progress_callback,debug_lines=debug_lines,raw_lines=raw_lines)

        prows=[]; srows=[]; mrows=[]; erows=[]; zrows=[]
        seen_sku=set(); seen_barcode=set(); counts={"ok":0,"manual_review":0,"error":0,"excluded_zero_stock":0}
        # precompute stock by mother/base SKU (regla: incluir variantes si alguna tiene stock)
        group_totals = {}
        prepared = []
        for item in products:
            sku=str(item.get('codigo') or '').strip(); name=str(item.get('nombre') or '')
            stock_map=self._extract_stock_by_warehouse(item); stock_total=calculate_total_stock(stock_map)
            base_key = self._base_group_key(sku, name)
            group_totals[base_key] = group_totals.get(base_key, 0.0) + stock_total
            prepared.append((item, sku, name, stock_map, stock_total, base_key))

        for i,(item, sku, name, stock_map, stock_total, base_key) in enumerate(prepared, start=1):
            barcode=str(item.get('codigo_barra') or '').strip()
            categoria_id=str(item.get('categoria_id') or item.get('categoria') or '')
            marca_raw=str(item.get('marca_nombre') or item.get('marca') or '')
            price=float(item.get('pvp1') or 0); cost=float(item.get('costo_maximo') or item.get('costo_promedio') or item.get('costo') or 0)
            include_by_group = group_totals.get(base_key, 0.0) > 0
            if should_exclude_zero_stock(stock_total) and not include_by_group:
                zrows.append(build_zero_stock_exclusion_row(sku=sku,nombre_contifico=name,codigo_barra=barcode,categoria_id=categoria_id,marca_nombre=marca_raw,pvp1=f"{price:.2f}",costo=f"{cost:.2f}",stock_total_contifico=f"{stock_total:.2f}",estado_contifico=str(item.get('estado') or '')))
                counts['excluded_zero_stock'] += 1
                mrows.append(build_mapping_report_row(sku=sku,nombre_contifico=name,producto_madre_detectado='',categoria_odoo_detectada='',talla_detectada='',manga_detectada='',ancho_corbata_detectado='',marca_detectada=detect_brand(marca_raw,name),color_detectado=detect_color(name),barcode=barcode,precio=f"{price:.2f}",costo=f"{cost:.2f}",stock_bpu=f"{stock_map['BPU']:.2f}",stock_tur=f"{stock_map['TUR']:.2f}",stock_bat=f"{stock_map['BAT']:.2f}",stock_total_contifico=f"{stock_total:.2f}",estado='excluded_zero_stock',confidence='1.00',parser_rule='exclude_zero_no_group_stock'))
                continue

            parser_rule=''; parsed={}; category=detect_category(name, categoria_id)
            for fn in (parse_shirt_sku, parse_tie_sku, parse_bowtie_sku, parse_fajin_sku):
                parsed = fn(sku) or {}
                if parsed: break
            if not parsed and 'LEVA' in name.upper(): parsed = parse_blazer_sku(sku) or {}
            if not parsed: parsed = parse_suit_sku(sku) or {}
            if parsed: parser_rule=parsed.get('parser_rule','')
            talla=parsed.get('talla') or parse_generic_size(sku)
            manga=parsed.get('manga',''); ancho=parsed.get('ancho_corbata','')
            prod_name=parsed.get('product_name') or name or sku
            brand=detect_brand(marca_raw,name); color=detect_color(name)
            if not sku:
                erows.append(build_error_row(sku=sku,nombre_contifico=name,problema='SKU obligatorio',sugerencia='Revisar codigo',raw_categoria_id=categoria_id,raw_marca_nombre=marca_raw,raw_codigo_barra=barcode)); counts['error'] +=1; continue
            state='ok'; confidence='0.95'
            if not category or not talla and not ancho and not manga:
                state='manual_review'; confidence='0.65'; counts['manual_review'] += 1
            else: counts['ok'] += 1
            if sku in seen_sku:
                erows.append(build_error_row(sku=sku,nombre_contifico=name,problema='SKU duplicado',sugerencia='Depurar duplicados',raw_categoria_id=categoria_id,raw_marca_nombre=marca_raw,raw_codigo_barra=barcode)); counts['error'] +=1; continue
            if barcode and barcode in seen_barcode:
                erows.append(build_error_row(sku=sku,nombre_contifico=name,problema='Código de barras duplicado',sugerencia='Depurar barcode',raw_categoria_id=categoria_id,raw_marca_nombre=marca_raw,raw_codigo_barra=barcode)); counts['error'] +=1; continue
            seen_sku.add(sku); seen_barcode.add(barcode)
            pvalues=build_product_values(talla=talla,manga=manga,ancho_corbata=ancho,marca=brand,color=color)
            prows.append({"External ID": build_external_id(sku),"Name": prod_name,"Product Type":"Goods","Product Category": category, "Internal Reference":sku,"Barcode":barcode,"Sales Price":f"{price:.2f}","Cost":f"{cost:.2f}","Weight":"0.0","Sales Description":"","Product Values":pvalues})
            if export_stock:
                for wh,loc in WAREHOUSE_TO_LOCATION.items():
                    qty=float(stock_map.get(wh,0) or 0)
                    if qty>0: srows.append({"sku":sku,"ubicacion_odoo":loc,"cantidad":f"{qty:.2f}","costo_unitario":f"{cost:.2f}"})
            mrows.append(build_mapping_report_row(sku=sku,nombre_contifico=name,producto_madre_detectado=prod_name,categoria_odoo_detectada=category,talla_detectada=talla,manga_detectada=manga,ancho_corbata_detectado=ancho,marca_detectada=brand,color_detectado=color,barcode=barcode,precio=f"{price:.2f}",costo=f"{cost:.2f}",stock_bpu=f"{stock_map['BPU']:.2f}",stock_tur=f"{stock_map['TUR']:.2f}",stock_bat=f"{stock_map['BAT']:.2f}",stock_total_contifico=f"{stock_total:.2f}",estado=state,confidence=confidence,parser_rule=parser_rule or 'generic'))
            if progress_callback and (i % 25 == 0 or i == len(products)): progress_callback({"stage":"processing","processed_items":i,"total_items":len(products),"found_items":len(products)})

        self._write_csv(product_csv, PRODUCT_COLUMNS, prows); self._write_csv(stock_csv, STOCK_COLUMNS, srows); self._write_csv(errors_csv, ERROR_COLUMNS, erows); self._write_csv(mapping_csv, MAP_COLUMNS, mrows); self._write_csv(excluded_zero_csv, EXCLUDED_ZERO_COLUMNS, zrows)
        debug_lines += [f"summary={json.dumps(counts)}", f"pages_fetched={pages_fetched}", f"hit_max_pages={hit_max_pages}"]
        debug_log.write_text("\n".join(debug_lines)+"\n", encoding='utf-8'); raw_log.write_text("\n".join(raw_lines)+"\n", encoding='utf-8')
        summary={"total_extracted":len(products),"total_stock_gt_zero":len(products)-len(zrows),"total_excluded_zero_stock":len(zrows),"total_ok":counts['ok'],"total_manual_review":counts['manual_review'],"total_error":counts['error'],"stock_export_enabled": export_stock}
        return MigrationOutput(folder,product_csv,stock_csv,errors_csv,mapping_csv,excluded_zero_csv,len(prows),len(erows),pages_fetched,hit_max_pages,debug_log,raw_log,summary)

    def _validate_templates(self):
        if self._read_header(TEMPLATE_PRODUCT_PATH) != PRODUCT_COLUMNS: raise ValueError('Plantilla producto no coincide')
        if self._read_header(TEMPLATE_STOCK_PATH) != STOCK_COLUMNS: raise ValueError('Plantilla stock no coincide')

    @staticmethod
    def _read_header(path: Path):
        with path.open('r', encoding='utf-8') as f: line=f.readline().strip()
        return [c.strip() for c in line.split(',') if c.strip()]

    def _fetch_products(self, *, page_size:int, max_pages:int, progress_callback=None, debug_lines=None, raw_lines=None):
        items=[]; pages=0
        for page in range(1,max_pages+1):
            if progress_callback: progress_callback({"stage":"fetching","page":page,"max_pages":max_pages,"found_items":len(items)})
            batch=list(self.client.list_products(page=page,page_size=page_size)); pages=page
            if debug_lines is not None: debug_lines.append(f"fetch page={page} items={len(batch)}")
            if raw_lines is not None: raw_lines.append(json.dumps({"page":page,"response":batch}, ensure_ascii=False))
            if not batch: break
            items.extend([b for b in batch if isinstance(b,dict)])
            if progress_callback: progress_callback({"stage":"fetched_page","page":page,"fetched":len(batch),"found_items":len(items)})
            if len(batch)<page_size: break
        return items, pages, pages>=max_pages

    @staticmethod
    def _extract_stock_by_warehouse(item: dict[str, Any]):
        result={"BPU":0.0,"TUR":0.0,"BAT":0.0}
        raw=item.get('bodegas') or item.get('stock_por_bodega') or []
        if isinstance(raw,dict):
            for k in result:
                result[k]=float(raw.get(k) or 0)
            if sum(result.values()) <= 0:
                result['BPU'] = float(item.get('cantidad_stock') or 0)
            return result
        if isinstance(raw,list):
            for e in raw:
                if not isinstance(e,dict):
                    continue
                code=str(e.get('codigo') or e.get('siglas') or e.get('bodega') or '').upper()
                qty=float(e.get('cantidad') or e.get('stock') or 0)
                for key in result:
                    if key in code:
                        result[key]=qty
        if sum(result.values()) <= 0:
            result['BPU'] = float(item.get('cantidad_stock') or 0)
        return result

    @staticmethod
    def _base_group_key(sku: str, name: str) -> str:
        if '-' in sku and sku.endswith(('-CO', '-FJ')):
            return sku[:-3]
        if '/' in sku:
            return sku.rsplit('/', 1)[0]
        if '-' in sku:
            return sku.rsplit('-', 1)[0]
        return sku or name

    @staticmethod
    def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]):
        with path.open('w', newline='', encoding='utf-8') as f:
            w=csv.DictWriter(f, fieldnames=columns); w.writeheader(); [w.writerow(r) for r in rows]
