from __future__ import annotations
import csv
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
import json

import time

from ..contifico import ContificoAPIError, ContificoClient, ContificoTransportError
from .odoo19_variants import (
    build_products_with_variants_from_variant_rows,
    build_variant_sku_mapping,
    PRODUCTS_COLUMNS as ODOO_TEMPLATE_COLUMNS,
    VARIANT_MAPPING_COLUMNS,
    STOCK_QUANT_SIMPLE_COLUMNS,
)
from .rules import (
    detect_brand, detect_color, detect_category, calculate_total_stock, should_exclude_zero_stock,
    parse_shirt_sku, parse_suit_sku, parse_blazer_sku, parse_tie_sku, parse_bowtie_sku, parse_fajin_sku,
    parse_generic_size, build_product_values, build_external_id, build_mapping_report_row,
    build_error_row, build_zero_stock_exclusion_row, normalize_sku_for_group,
)

WAREHOUSE_TO_LOCATION = {"BPU": "BPU/Existencias", "TUR": "TUR/Existencias", "BAT": "BAT/Existencias", "BSR": "BSR/Existencias", "OFA": "OFA/Existencias", "BMT": "BMT/Existencias", "B2": "B2/Existencias", "BW": "BW/Existencias", "BM": "BM/Existencias", "BTL": "BTL/Existencias"}
WAREHOUSE_MAP_CONFIG = json.loads((Path(__file__).resolve().parents[3] / "config/warehouse_mapping.json").read_text(encoding="utf-8"))
WAREHOUSE_CATALOG = json.loads((Path(__file__).resolve().parents[3] / "config/warehouse_catalog.json").read_text(encoding="utf-8"))
CONTIFICO_CATEGORY_ID_MAP = json.loads((Path(__file__).resolve().parents[3] / "config/contifico_category_id_map.json").read_text(encoding="utf-8"))
CONTIFICO_CATEGORY_TO_ODOO = json.loads((Path(__file__).resolve().parents[3] / "config/contifico_category_to_odoo.json").read_text(encoding="utf-8"))
PRODUCT_COLUMNS = ["External ID","Name","Product Type","Internal Reference","Barcode","Sales Price","Cost","Weight","Sales Description","Product Values"]
STOCK_COLUMNS = ["sku","ubicacion_odoo","cantidad","costo_unitario"]
STOCK_QUANT_COLUMNS = ["Product", "Lot/Serial Number", "Quantity", "Counted Quantity", "Difference", "Scheduled Date", "Assigned To"]
MAP_COLUMNS = ["sku","nombre_contifico","producto_madre_detectado","categoria_odoo_detectada","talla_detectada","manga_detectada","ancho_corbata_detectado","marca_detectada","color_detectado","barcode","precio","costo","stock_bpu","stock_tur","stock_bat","stock_total_contifico","estado","confidence","parser_rule"]
ERROR_COLUMNS = ["sku","nombre_contifico","problema","sugerencia","raw_categoria_id","raw_marca_nombre","raw_codigo_barra"]
EXCLUDED_ZERO_COLUMNS = ["sku","nombre_contifico","codigo_barra","categoria_id","marca_nombre","pvp1","costo","stock_total_contifico","estado_contifico","motivo_exclusion"]
UNMAPPED_CATEGORY_COLUMNS = ["categoria_id","categoria_nombre_resuelta","productos_detectados"]
TEMPLATE_PRODUCT_PATH = Path(__file__).resolve().parents[3] / "docs/odoo_import_templates/product_product_template.csv"
TEMPLATE_STOCK_PATH = Path(__file__).resolve().parents[3] / "docs/odoo_import_templates/stock_quant.csv"
TEMPLATE_ATTR_COLUMNS = ["External ID","Name","Product Type","Sales Price","Cost","Weight","Sales Description","Product Attributes / Attribute","Product Attributes / Values"]
VARIANT_MAP_COLUMNS = ["Template External ID","Template Name","Source Variant External ID","Variant Attributes Key","Internal Reference","Barcode","Sales Price","Cost","Weight","Original Product Values"]
STOCK_BY_VARIANT_COLUMNS = ["Product External ID","Location","Quantity"]
MISSING_ATTR_COLUMNS = ["Attribute","Value","Product Count","Example Product","Example Internal Reference"]


@dataclass
class MigrationOutput:
    folder: Path; product_csv: Path; stock_csv: Path; errors_csv: Path; mapping_csv: Path; excluded_zero_csv: Path
    total_products: int; total_errors: int; pages_fetched: int; hit_max_pages: bool; debug_log: Path; raw_log: Path; summary: dict[str, Any]


class OdooMigrationService:
    PRODUCT_PAGE_SERVER_RETRIES = 3
    PRODUCT_PAGE_RETRY_BACKOFF_BASE_SECONDS = 0.8

    def __init__(self, client: ContificoClient, output_root: str | Path = "backend/data/odoo_migration", *, page_delay_seconds: float = 1.0, page_retry_attempts: int | None = None, page_retry_backoff_base_seconds: float | None = None, page_retry_jitter_seconds: float = 0.4):
        self.client = client; self.output_root = Path(output_root)
        self.page_delay_seconds = max(0.0, float(page_delay_seconds))
        self.page_retry_attempts = int(page_retry_attempts or self.PRODUCT_PAGE_SERVER_RETRIES)
        self.page_retry_backoff_base_seconds = float(page_retry_backoff_base_seconds or self.PRODUCT_PAGE_RETRY_BACKOFF_BASE_SECONDS)
        self.page_retry_jitter_seconds = max(0.0, float(page_retry_jitter_seconds))
        self._warehouse_by_id = {w.get("id"): w for w in WAREHOUSE_CATALOG if w.get("id")}
        self._warehouse_by_code = {str(w.get("codigo","")).upper(): w for w in WAREHOUSE_CATALOG}
        self._warehouse_by_name = {str(w.get("nombre","")).upper(): w for w in WAREHOUSE_CATALOG}

    def generate_products_and_stock_csv(self, *, page_size=200, max_pages=200, export_stock: bool = False, include_additional_attributes: bool = False, progress_callback: Callable[[dict[str, Any]], None] | None = None) -> MigrationOutput:
        self._validate_templates()
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S'); folder = self.output_root / ts; folder.mkdir(parents=True, exist_ok=True)
        product_csv=folder/'product_product.csv'; stock_csv=folder/'initial_stock.csv'; stock_quant_csv=folder/'stock_quant_legacy.csv'; errors_csv=folder/'migration_errors.csv'; mapping_csv=folder/'mapping_report.csv'; excluded_zero_csv=folder/'excluded_zero_stock.csv'; unmapped_categories_csv=folder/'unmapped_categories.csv'; debug_log=folder/'debug.log'; raw_log=folder/'raw.log'
        snapshot_path = folder / 'products_snapshot.jsonl'; state_path = folder / 'stock_state.json'
        debug_lines=[f'start={datetime.utcnow().isoformat()}Z',f'page_size={page_size}',f'max_pages={max_pages}',f'export_stock={export_stock}']; raw_lines=[]
        started_at = datetime.utcnow()
        products,pages_fetched,hit_max_pages,expected_min_items=self._fetch_products(page_size=page_size,max_pages=max_pages,run_folder=folder,progress_callback=progress_callback,debug_lines=debug_lines,raw_lines=raw_lines)
        return self._generate_from_products(
            products=products, folder=folder, pages_fetched=pages_fetched, hit_max_pages=hit_max_pages,
            expected_min_items=expected_min_items, started_at=started_at,
            export_stock=export_stock, include_additional_attributes=include_additional_attributes,
            progress_callback=progress_callback, debug_lines=debug_lines, raw_lines=raw_lines,
        )

    def generate_products_and_stock_csv_from_items(self, *, products: list[dict[str, Any]], export_stock: bool = False, include_additional_attributes: bool = False, progress_callback: Callable[[dict[str, Any]], None] | None = None) -> MigrationOutput:
        self._validate_templates()
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S'); folder = self.output_root / ts; folder.mkdir(parents=True, exist_ok=True)
        debug_lines=[f'start={datetime.utcnow().isoformat()}Z',f'source=uploaded_raw_json',f'export_stock={export_stock}']; raw_lines=[json.dumps({"uploaded_items": len(products)})]
        return self._generate_from_products(
            products=products, folder=folder, pages_fetched=0, hit_max_pages=False, expected_min_items=None, started_at=datetime.utcnow(),
            export_stock=export_stock, include_additional_attributes=include_additional_attributes,
            progress_callback=progress_callback, debug_lines=debug_lines, raw_lines=raw_lines,
        )

    def _generate_from_products(self, *, products: list[dict[str, Any]], folder: Path, pages_fetched: int, hit_max_pages: bool, expected_min_items: int | None, started_at: datetime, export_stock: bool, include_additional_attributes: bool, progress_callback=None, debug_lines=None, raw_lines=None) -> MigrationOutput:
        product_csv=folder/'product_product.csv'; stock_csv=folder/'initial_stock.csv'; stock_quant_csv=folder/'stock_quant_legacy.csv'; errors_csv=folder/'migration_errors.csv'; mapping_csv=folder/'mapping_report.csv'; excluded_zero_csv=folder/'excluded_zero_stock.csv'; unmapped_categories_csv=folder/'unmapped_categories.csv'; debug_log=folder/'debug.log'; raw_log=folder/'raw.log'
        snapshot_path = folder / 'products_snapshot.jsonl'; state_path = folder / 'stock_state.json'
        phase1 = self._phase1_prepare_products(products=products, folder=folder, snapshot_path=snapshot_path, errors_csv=errors_csv, mapping_csv=mapping_csv, excluded_zero_csv=excluded_zero_csv, product_csv=product_csv, include_additional_attributes=include_additional_attributes, export_stock=export_stock, progress_callback=progress_callback)
        self._write_stock_state(state_path, phase1['stock_state'])
        self._write_csv(stock_csv, STOCK_COLUMNS, [])
        self._write_csv(stock_quant_csv, STOCK_QUANT_COLUMNS, [])

        if export_stock:
            self._phase2_enrich_stock(snapshot_path=snapshot_path, state_path=state_path, stock_csv=stock_csv, stock_quant_csv=stock_quant_csv, phase1_errors=phase1['erows'], progress_callback=progress_callback)

        self._write_csv(errors_csv, ERROR_COLUMNS, phase1['erows'])
        self._write_csv(mapping_csv, MAP_COLUMNS, phase1['mrows'])
        self._write_csv(excluded_zero_csv, EXCLUDED_ZERO_COLUMNS, phase1['zrows'])
        self._write_csv(unmapped_categories_csv, UNMAPPED_CATEGORY_COLUMNS, phase1['unmapped_category_rows'])

        self._write_variant_import_outputs(folder, phase1.get("variant_rows", []), include_stock=export_stock)
        o19_warnings: list[str] = []
        o19_product_rows = build_products_with_variants_from_variant_rows(phase1.get("variant_rows", []), warnings=o19_warnings)
        o19_variant_map_rows = build_variant_sku_mapping(phase1.get("variant_rows", []))
        o19_stock_rows = []
        for vr in phase1.get("variant_rows", []):
            sku = str(vr.get("sku") or "").strip()
            for wh, loc in WAREHOUSE_TO_LOCATION.items():
                qty = float((vr.get("stock_map") or {}).get(wh, 0) or 0)
                if qty > 0:
                    o19_stock_rows.append({"Product / Internal Reference": sku, "Location": loc, "Inventory Quantity": f"{qty:.2f}"})
        self._write_csv(folder / "odoo_product_templates.csv", ODOO_TEMPLATE_COLUMNS, o19_product_rows)
        self._write_csv(folder / "odoo_variant_sku_mapping.csv", VARIANT_MAPPING_COLUMNS, o19_variant_map_rows)
        self._write_csv(folder / "odoo_stock_quant.csv", STOCK_QUANT_SIMPLE_COLUMNS, o19_stock_rows)
        self._write_csv(folder / "odoo_import_validation_report.csv", ["level", "rule", "entity", "message"], [])

        counts = phase1['counts']
        debug_lines += [f"summary={json.dumps(counts)}", f"pages_fetched={pages_fetched}", f"hit_max_pages={hit_max_pages}", f"snapshot={snapshot_path.name}", f"state={state_path.name}"]
        debug_log.write_text("\n".join(debug_lines)+"\n", encoding='utf-8'); raw_log.write_text("\n".join(raw_lines)+"\n", encoding='utf-8')
        duration_seconds = round((datetime.utcnow() - started_at).total_seconds(), 2)
        summary={"total_products":len(phase1['prows']),"total_categorias_no_mapeadas":len(phase1['unmapped_category_rows']),"total_skus_unicos_product_product":len({r.get('Internal Reference') for r in phase1['prows']}),"total_lineas_initial_stock":0,"total_lineas_stock_quant":0,"total_skus_stock_match_producto":0,"total_skus_stock_no_match_producto":0,"total_ubicaciones_mapeadas":0,"total_ubicaciones_no_mapeadas":0,"total_productos_excluidos_stock_0":len(phase1['zrows']),"total_errores_reales":len(phase1['erows']),"stock_export_enabled": export_stock, "phase_1_completed": True, "phase_2_completed": export_stock, "include_additional_attributes": include_additional_attributes, "include_brand_color_attributes": include_additional_attributes, "expected_min_items_from_api": expected_min_items, "fetched_items_meet_expected_min": (len(products) >= expected_min_items) if expected_min_items is not None else None, "duration_seconds": duration_seconds}
        if export_stock:
            stock_rows = self._read_csv_rows(stock_csv)
            stock_quant_rows = self._read_csv_rows(stock_quant_csv)
            stock_skus = {r.get('sku') for r in stock_rows if r.get('sku')}
            product_skus = {r.get('Internal Reference') for r in phase1['prows'] if r.get('Internal Reference')}
            summary.update({
                "total_lineas_initial_stock": len(stock_rows),
                "total_lineas_stock_quant": len(stock_quant_rows),
                "total_skus_stock_match_producto": len(stock_skus & product_skus),
                "total_skus_stock_no_match_producto": len(stock_skus - product_skus),
                "total_ubicaciones_mapeadas": len([r for r in stock_rows if r.get('ubicacion_odoo')]),
                "total_ubicaciones_no_mapeadas": 0,
            })
        (folder / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return MigrationOutput(folder,product_csv,stock_csv,errors_csv,mapping_csv,excluded_zero_csv,len(phase1['prows']),len(phase1['erows']),pages_fetched,hit_max_pages,debug_log,raw_log,summary)

    def _phase1_prepare_products(self, *, products: list[dict[str, Any]], folder: Path, snapshot_path: Path, errors_csv: Path, mapping_csv: Path, excluded_zero_csv: Path, product_csv: Path, include_additional_attributes: bool = False, export_stock: bool = False, progress_callback=None) -> dict[str, Any]:
        prows=[]; mrows=[]; erows=[]; zrows=[]; variant_rows=[]; unmapped_categories={} 
        seen_sku=set(); seen_barcode=set(); counts={"ok":0,"manual_review":0,"error":0,"excluded_zero_stock":0}
        group_totals = {}; prepared=[]; stock_state=[]
        for item in products:
            sku=str(item.get('codigo') or '').strip(); name=str(item.get('nombre') or '')
            stock_map=self._extract_stock_from_item(item)
            stock_total=calculate_total_stock(stock_map)
            base_key = self._base_group_key(sku, name)
            group_totals[base_key] = group_totals.get(base_key, 0.0) + stock_total
            prepared.append((item, sku, name, stock_map, stock_total, base_key))

        with snapshot_path.open('w', encoding='utf-8') as snap:
            for i,(item, sku, name, stock_map, stock_total, base_key) in enumerate(prepared, start=1):
                barcode=str(item.get('codigo_barra') or '').strip(); categoria_id=str(item.get('categoria_id') or item.get('categoria') or '')
                marca_raw=str(item.get('marca_nombre') or item.get('marca') or '')
                price=float(item.get('pvp1') or 0); cost=float(item.get('costo_maximo') or item.get('costo_promedio') or item.get('costo') or 0)
                include_by_group = group_totals.get(base_key, 0.0) > 0
                if should_exclude_zero_stock(stock_total) and not include_by_group:
                    zrows.append(build_zero_stock_exclusion_row(sku=sku,nombre_contifico=name,codigo_barra=barcode,categoria_id=categoria_id,marca_nombre=marca_raw,pvp1=f"{price:.2f}",costo=f"{cost:.2f}",stock_total_contifico=f"{stock_total:.2f}",estado_contifico=str(item.get('estado') or '')))
                    counts['excluded_zero_stock'] += 1
                    mrows.append(build_mapping_report_row(sku=sku,nombre_contifico=name,producto_madre_detectado='',categoria_odoo_detectada='',talla_detectada='',manga_detectada='',ancho_corbata_detectado='',marca_detectada=detect_brand(marca_raw,name),color_detectado=detect_color(name),barcode=barcode,precio=f"{price:.2f}",costo=f"{cost:.2f}",stock_bpu=f"{stock_map['BPU']:.2f}",stock_tur=f"{stock_map['TUR']:.2f}",stock_bat=f"{stock_map['BAT']:.2f}",stock_total_contifico=f"{stock_total:.2f}",estado='excluded_zero_stock',confidence='1.00',parser_rule='exclude_zero_no_group_stock'))
                    continue

                parser_rule=''; parsed={}; resolved_categoria = CONTIFICO_CATEGORY_ID_MAP.get(categoria_id, categoria_id)
                category=CONTIFICO_CATEGORY_TO_ODOO.get(categoria_id) or detect_category(name, categoria_id, sku=sku)
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
                if categoria_id and categoria_id not in CONTIFICO_CATEGORY_TO_ODOO:
                    unmapped_categories[categoria_id] = {"categoria_id": categoria_id, "categoria_nombre_resuelta": resolved_categoria or "", "productos_detectados": int(unmapped_categories.get(categoria_id, {}).get("productos_detectados", 0)) + 1}
                if not category or not talla and not ancho and not manga:
                    state='manual_review'; confidence='0.65'; counts['manual_review'] += 1
                else: counts['ok'] += 1
                if sku in seen_sku:
                    erows.append(build_error_row(sku=sku,nombre_contifico=name,problema='SKU duplicado',sugerencia='Depurar duplicados',raw_categoria_id=categoria_id,raw_marca_nombre=marca_raw,raw_codigo_barra=barcode)); counts['error'] +=1; continue
                if barcode and barcode in seen_barcode:
                    erows.append(build_error_row(sku=sku,nombre_contifico=name,problema='Código de barras duplicado',sugerencia='Depurar barcode',raw_categoria_id=categoria_id,raw_marca_nombre=marca_raw,raw_codigo_barra=barcode)); counts['error'] +=1; continue
                seen_sku.add(sku); seen_barcode.add(barcode)
                pvalues=build_product_values(talla=talla,manga=manga,ancho_corbata=ancho,marca=brand if include_additional_attributes else '',color=color if include_additional_attributes else '')
                prows.append({"External ID": build_external_id(sku),"Name": prod_name,"Product Type":"Goods", "Internal Reference":sku,"Barcode":barcode,"Sales Price":f"{price:.2f}","Cost":f"{cost:.2f}","Weight":"0.0","Sales Description":f"Categoría sugerida: {category}","Product Values":pvalues})
                mrows.append(build_mapping_report_row(sku=sku,nombre_contifico=name,producto_madre_detectado=prod_name,categoria_odoo_detectada=category,talla_detectada=talla,manga_detectada=manga,ancho_corbata_detectado=ancho,marca_detectada=brand,color_detectado=color,barcode=barcode,precio=f"{price:.2f}",costo=f"{cost:.2f}",stock_bpu=f"{stock_map['BPU']:.2f}",stock_tur=f"{stock_map['TUR']:.2f}",stock_bat=f"{stock_map['BAT']:.2f}",stock_total_contifico=f"{stock_total:.2f}",estado=state,confidence=confidence,parser_rule=parser_rule or 'generic'))
                variant_rows.append({
                    "sku": sku, "name": prod_name, "barcode": barcode, "price": f"{price:.2f}", "cost": f"{cost:.2f}",
                    "weight": "0.0", "category": category, "stock_map": stock_map,
                    "attrs": {"Marca": brand, "Color": color, "Talla": talla, "Manga de Camisa": manga, "Ancho Corbata": ancho}
                })
                payload = {"id": str(item.get('id') or ''), "sku": sku, "cost": cost, "stock_map": stock_map}
                snap.write(json.dumps(payload, ensure_ascii=False) + "\n")
                stock_state.append({"product_id": payload["id"], "sku": sku, "status": "pending", "retry_count": 0, "last_error": ""})
                if progress_callback and (i % 25 == 0 or i == len(prepared)): progress_callback({"stage":"phase_1_processing","processed_items":i,"total_items":len(prepared),"found_items":len(products)})

        self._write_csv(product_csv, PRODUCT_COLUMNS, prows)
        return {"prows": prows, "mrows": mrows, "erows": erows, "zrows": zrows, "counts": counts, "stock_state": stock_state, "variant_rows": variant_rows, "unmapped_category_rows": list(unmapped_categories.values())}

    def _write_variant_import_outputs(self, run_folder: Path, variant_rows: list[dict[str, Any]], include_stock: bool = False) -> None:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in variant_rows:
            key = self._slugify(row.get("name") or row.get("sku") or "")
            grouped.setdefault(key, []).append(row)

        used_templates: dict[str, int] = {}
        template_rows, variant_map_rows, stock_rows, missing_rows = [], [], [], []
        examples = []
        for key, rows in grouped.items():
            base_ext = f"adams_tmpl_{key}" if key else "adams_tmpl_producto"
            n = used_templates.get(base_ext, 0) + 1
            used_templates[base_ext] = n
            tmpl_ext = base_ext if n == 1 else f"{base_ext}_dup_{n}"
            first = rows[0]
            attr_values: dict[str, set[str]] = {}
            real_combos = set()
            for r in rows:
                attrs = {k: v for k, v in (r.get("attrs") or {}).items() if v}
                for a, v in attrs.items():
                    attr_values.setdefault(a, set()).add(v)
                combo = "|".join([f"{k}={attrs[k]}" for k in sorted(attrs.keys())])
                real_combos.add(combo)
                source_ext = build_external_id(r["sku"])
                variant_map_rows.append({
                    "Template External ID": tmpl_ext, "Template Name": first["name"], "Source Variant External ID": source_ext,
                    "Variant Attributes Key": combo, "Internal Reference": r["sku"], "Barcode": r.get("barcode",""),
                    "Sales Price": r["price"], "Cost": r["cost"], "Weight": r["weight"],
                    "Original Product Values": build_product_values(talla=attrs.get("Talla",""), manga=attrs.get("Manga de Camisa",""), ancho_corbata=attrs.get("Ancho Corbata",""), marca=attrs.get("Marca",""), color=attrs.get("Color",""))
                })
                if include_stock:
                    for wh, loc in WAREHOUSE_TO_LOCATION.items():
                        qty = float((r.get("stock_map") or {}).get(wh, 0) or 0)
                        if qty > 0:
                            stock_rows.append({"Product External ID": source_ext, "Location": loc, "Quantity": f"{qty:.2f}"})
            for attr, values in sorted(attr_values.items()):
                values_csv = ",".join(sorted(values))
                template_rows.append({
                    "External ID": tmpl_ext, "Name": first["name"], "Product Type": "Goods", "Sales Price": first["price"],
                    "Cost": first["cost"], "Weight": first["weight"], "Sales Description": f"Categoría sugerida: {first['category']}",
                    "Product Attributes / Attribute": attr, "Product Attributes / Values": values_csv
                })
                for v in sorted(values):
                    missing_rows.append({"Attribute": attr, "Value": v, "Product Count": str(sum(1 for rr in rows if (rr.get('attrs') or {}).get(attr)==v)), "Example Product": first["name"], "Example Internal Reference": rows[0]["sku"]})
            # combinaciones fantasma
            axes = [sorted(vs) for vs in attr_values.values() if vs]
            theoretical = 1
            for axis in axes:
                theoretical *= max(1, len(axis))
            ghost = theoretical - len(real_combos)
            if ghost > 0 and len(examples) < 10:
                examples.append((tmpl_ext, first["name"], len(rows), ghost))

        self._write_csv(run_folder / "01_product_templates_with_existing_attributes.csv", TEMPLATE_ATTR_COLUMNS, template_rows)
        self._write_csv(run_folder / "02_variant_update_map.csv", VARIANT_MAP_COLUMNS, variant_map_rows)
        self._write_csv(run_folder / "03_stock_quant_by_variant.csv", STOCK_BY_VARIANT_COLUMNS, stock_rows)
        self._write_csv(run_folder / "04_missing_attribute_values_report.csv", MISSING_ATTR_COLUMNS, missing_rows)
        report = [
            "# import_products_and_variants_report",
            f"- Total SKUs de origen: {len(variant_rows)}",
            f"- Total productos madre generados: {len({r['External ID'] for r in template_rows})}",
            f"- Total variantes/subproductos reales: {len(variant_map_rows)}",
            f"- Total productos con Marca: {sum(1 for r in variant_rows if (r.get('attrs') or {}).get('Marca'))}",
            f"- Total productos con Color: {sum(1 for r in variant_rows if (r.get('attrs') or {}).get('Color'))}",
            f"- Total productos con Talla: {sum(1 for r in variant_rows if (r.get('attrs') or {}).get('Talla'))}",
            f"- Total productos con Ancho Corbata: {sum(1 for r in variant_rows if (r.get('attrs') or {}).get('Ancho Corbata'))}",
            f"- Total productos con Manga de Camisa: {sum(1 for r in variant_rows if (r.get('attrs') or {}).get('Manga de Camisa'))}",
            f"- Productos sin barcode: {sum(1 for r in variant_rows if not r.get('barcode'))}",
            f"- Productos sin Internal Reference: {sum(1 for r in variant_rows if not r.get('sku'))}",
            f"- Confirmación: NO se crean atributos/categorías de variante, solo se usan atributos existentes."
        ]
        if examples:
            report.append("- Ejemplos con posibles combinaciones fantasma:")
            for e in examples:
                report.append(f"  - {e[0]} | {e[1]} | variantes reales={e[2]} | combinaciones fantasma≈{e[3]}")
        (run_folder / "import_products_and_variants_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    @staticmethod
    def _slugify(text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
        return slug[:80]

    def _phase2_enrich_stock(self, *, snapshot_path: Path, state_path: Path, stock_csv: Path, stock_quant_csv: Path, phase1_errors: list[dict[str, Any]], progress_callback=None) -> None:
        state = self._read_stock_state(state_path)
        by_sku = {r.get("sku"): r for r in state}
        rows=[]; stock_quant_rows=[]; processed=0
        for line in snapshot_path.read_text(encoding='utf-8').splitlines():
            item = json.loads(line)
            sku = item.get("sku") or ""
            st = by_sku.get(sku)
            if not st or st.get("status") != "pending":
                continue
            try:
                stock_map = item.get("stock_map") or {key:0.0 for key in WAREHOUSE_TO_LOCATION}
                product_id = item.get("id")
                if product_id:
                    stock_detail = self.client.get_product_stock(str(product_id))
                    stock_map = self._map_stock_detail(stock_detail, base=stock_map)
                for wh, loc in WAREHOUSE_TO_LOCATION.items():
                    qty=float(stock_map.get(wh,0) or 0)
                    if qty > 0:
                        rows.append({"sku": sku, "ubicacion_odoo": loc, "cantidad": f"{qty:.2f}", "costo_unitario": f"{float(item.get('cost') or 0):.2f}"})
                        stock_quant_rows.append({"Product": f"[{sku}]", "Lot/Serial Number": "", "Quantity": f"{qty:.2f}", "Counted Quantity": f"{qty:.2f}", "Difference": "0", "Scheduled Date": "", "Assigned To": ""})
                st["status"] = "done"; st["last_error"] = ""
            except Exception as exc:
                st["status"] = "error"; st["retry_count"] = int(st.get("retry_count") or 0) + 1; st["last_error"] = str(exc)
            processed += 1
            self._write_csv(stock_csv, STOCK_COLUMNS, rows)
            self._write_csv(stock_quant_csv, STOCK_QUANT_COLUMNS, stock_quant_rows)
            self._write_stock_state(state_path, state)
            if progress_callback and (processed % 25 == 0):
                progress_callback({"stage":"phase_2_stock", "processed_items": processed, "total_items": len(state)})

    def _map_stock_detail(self, detail: Any, base: dict[str, float] | None = None) -> dict[str, float]:
        result = {key: float((base or {}).get(key, 0) or 0) for key in WAREHOUSE_TO_LOCATION}
        if not isinstance(detail, list):
            return result
        for e in detail:
            if not isinstance(e, dict):
                continue
            raw_name = str(e.get('bodega_nombre') or '').upper(); raw_id = str(e.get('bodega_id') or '')
            qty = float(e.get('cantidad') or 0)
            mapped = None
            if raw_id and raw_id in self._warehouse_by_id:
                mapped = self._warehouse_by_id[raw_id].get('odoo_key')
            if not mapped and raw_name:
                mapped = WAREHOUSE_MAP_CONFIG.get(raw_name) or self._warehouse_by_name.get(raw_name, {}).get('odoo_key')
            if mapped in result:
                result[mapped] += qty
        return result

    def _extract_stock_from_item(self, item: dict[str, Any]):
        result={key:0.0 for key in WAREHOUSE_TO_LOCATION}
        raw=item.get('bodegas') or item.get('stock_por_bodega') or []
        if isinstance(raw,dict):
            for k in result: result[k]=float(raw.get(k) or 0)
            if sum(result.values()) <= 0: result['BPU'] = float(item.get('cantidad_stock') or 0)
            return result
        if isinstance(raw,list):
            for e in raw:
                if not isinstance(e,dict): continue
                raw_code=str(e.get('codigo') or e.get('siglas') or e.get('bodega_codigo') or '').upper()
                raw_name=str(e.get('bodega_nombre') or e.get('bodega') or '').upper(); raw_id=str(e.get('bodega_id') or e.get('id') or '')
                qty=float(e.get('cantidad') or e.get('stock') or 0)
                mapped = None
                if raw_id and raw_id in self._warehouse_by_id: mapped = self._warehouse_by_id[raw_id].get('odoo_key')
                if not mapped and raw_code: mapped = WAREHOUSE_MAP_CONFIG.get(raw_code) or self._warehouse_by_code.get(raw_code, {}).get('odoo_key')
                if not mapped and raw_name: mapped = WAREHOUSE_MAP_CONFIG.get(raw_name) or self._warehouse_by_name.get(raw_name, {}).get('odoo_key')
                if mapped in result: result[mapped] += qty
        if sum(result.values()) <= 0: result['BPU'] = float(item.get('cantidad_stock') or 0)
        return result

    def _extract_stock_by_warehouse(self, item: dict[str, Any]):
        return self._extract_stock_from_item(item)

    def _validate_templates(self):
        if self._read_header(TEMPLATE_PRODUCT_PATH) != PRODUCT_COLUMNS: raise ValueError('Plantilla producto no coincide')
        if self._read_header(TEMPLATE_STOCK_PATH) != STOCK_QUANT_COLUMNS: raise ValueError('Plantilla stock no coincide')

    @staticmethod
    def _read_header(path: Path):
        with path.open('r', encoding='utf-8') as f: line=f.readline().strip()
        return [c.strip() for c in line.split(',') if c.strip()]

    def _fetch_products(self, *, page_size:int, max_pages:int, run_folder: Path, progress_callback=None, debug_lines=None, raw_lines=None):
        resume_state_path = run_folder / "products_fetch_resume_state.json"
        resume_items_path = run_folder / "products_fetch_resume_items.jsonl"
        items, start_page = self._load_fetch_resume_state(
            resume_state_path=resume_state_path,
            resume_items_path=resume_items_path,
            page_size=page_size,
            max_pages=max_pages,
        )
        pages = start_page - 1
        products_v2_mode = "/api/v2" in str(getattr(self.client, "products_base_url", "")).lower()
        expected_min_items = None
        for page in range(start_page, max_pages + 1):
            if progress_callback: progress_callback({"stage":"fetching","page":page,"max_pages":max_pages,"found_items":len(items)})
            batch, effective_page_size = self._fetch_products_page_with_fallback(page=page, page_size=page_size); pages=page
            if debug_lines is not None: debug_lines.append(f"fetch page={page} items={len(batch)}")
            if raw_lines is not None: raw_lines.append(json.dumps({"page":page,"response":batch}, ensure_ascii=False))
            if not batch: break
            page_items = [b for b in batch if isinstance(b,dict)]
            items.extend(page_items)
            api_total = getattr(self.client, "last_products_total_count", None)
            if isinstance(api_total, int) and api_total > 0:
                expected_min_items = api_total
            self._save_fetch_resume_state(
                resume_state_path=resume_state_path,
                resume_items_path=resume_items_path,
                page=page,
                page_size=page_size,
                max_pages=max_pages,
                page_items=page_items,
            )
            if progress_callback:
                progress_callback({
                    "stage":"fetched_page",
                    "page":page,
                    "fetched":len(batch),
                    "found_items":len(items),
                    "expected_min_items_from_api": expected_min_items,
                    "fetched_items_meet_expected_min": (len(items) >= expected_min_items) if expected_min_items is not None else None,
                })
            if (not products_v2_mode) and len(batch) < effective_page_size:
                break
            if self.page_delay_seconds > 0:
                time.sleep(self.page_delay_seconds)
        self._clear_fetch_resume_state(resume_state_path=resume_state_path, resume_items_path=resume_items_path)
        return items, pages, pages>=max_pages, expected_min_items

    def _load_fetch_resume_state(self, *, resume_state_path: Path, resume_items_path: Path, page_size: int, max_pages: int) -> tuple[list[dict[str, Any]], int]:
        if not resume_state_path.exists() or not resume_items_path.exists():
            return [], 1
        try:
            state = json.loads(resume_state_path.read_text(encoding="utf-8"))
            if int(state.get("page_size") or 0) != int(page_size) or int(state.get("max_pages") or 0) != int(max_pages):
                return [], 1
            last_page = int(state.get("last_successful_page") or 0)
            items = []
            for line in resume_items_path.read_text(encoding="utf-8").splitlines():
                payload = json.loads(line)
                if isinstance(payload, dict):
                    items.append(payload)
            return items, max(1, last_page + 1)
        except Exception:
            return [], 1

    def _save_fetch_resume_state(self, *, resume_state_path: Path, resume_items_path: Path, page: int, page_size: int, max_pages: int, page_items: list[dict[str, Any]]) -> None:
        resume_state_path.parent.mkdir(parents=True, exist_ok=True)
        with resume_items_path.open("a", encoding="utf-8") as fh:
            for item in page_items:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        resume_state_path.write_text(
            json.dumps({"last_successful_page": page, "page_size": page_size, "max_pages": max_pages}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _clear_fetch_resume_state(*, resume_state_path: Path, resume_items_path: Path) -> None:
        if resume_state_path.exists():
            resume_state_path.unlink()
        if resume_items_path.exists():
            resume_items_path.unlink()

    def _fetch_products_page_with_fallback(self, *, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
        # Importante: no degradar page_size entre reintentos porque el número de página
        # representa offsets distintos para cada tamaño y puede crear huecos/duplicados.
        sizes = [page_size]
        last_exc: Exception | None = None
        for size in sizes:
            for attempt in range(1, self.page_retry_attempts + 1):
                try:
                    return list(self.client.list_products(page=page, page_size=size)), size
                except ContificoTransportError as exc:
                    last_exc = exc
                except ContificoAPIError as exc:
                    if self._is_page_out_of_range_error(exc):
                        return [], size
                    if exc.status_code not in {429, 500, 502, 503, 504}:
                        raise
                    last_exc = exc

                if attempt < self.page_retry_attempts:
                    base = self.page_retry_backoff_base_seconds * (2 ** (attempt - 1))
                    jitter = random.uniform(0.0, self.page_retry_jitter_seconds) if self.page_retry_jitter_seconds > 0 else 0.0
                    time.sleep(base + jitter)
            continue
        if last_exc:
            raise last_exc
        return [], page_size

    @staticmethod
    def _is_page_out_of_range_error(exc: ContificoAPIError) -> bool:
        status_code = int(getattr(exc, "status_code", 0) or 0)
        if status_code not in {400, 404}:
            return False
        payload = getattr(exc, "payload", None)
        message = str(getattr(exc, "detail", "") or "")
        if isinstance(payload, dict):
            for key in ("error", "mensaje", "message", "detail"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    message = f"{message} {value}".strip()
                    break
            code_value = str(payload.get("code") or "").strip()
            if code_value and code_value != "400":
                return False
        elif status_code == 404:
            return False
        normalized = message.lower()
        return "pagina fuera del rango" in normalized or "página fuera del rango" in normalized

    @staticmethod
    def _base_group_key(sku: str, name: str) -> str:
        if '-' in sku and sku.endswith(('-CO', '-FJ')): return sku[:-3]
        normalized = normalize_sku_for_group(sku)
        if '-' in normalized and normalized.endswith(('-CO', '-FJ')): return normalized[:-3]
        if '/' in normalized: return normalized.rsplit('/', 1)[0]
        if '-' in sku: return sku.rsplit('-', 1)[0]
        return sku or name

    @staticmethod
    def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]):
        with path.open('w', newline='', encoding='utf-8') as f:
            w=csv.DictWriter(f, fieldnames=columns); w.writeheader(); [w.writerow(r) for r in rows]

    @staticmethod
    def _write_stock_state(path: Path, rows: list[dict[str, Any]]) -> None:
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')

    @staticmethod
    def _read_stock_state(path: Path) -> list[dict[str, Any]]:
        if not path.exists(): return []
        return json.loads(path.read_text(encoding='utf-8'))

    @staticmethod
    def _read_csv_rows(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open('r', newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))
