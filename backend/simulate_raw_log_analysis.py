from __future__ import annotations
import argparse, json, csv
from collections import Counter
from pathlib import Path


def load_raw_items(path: Path):
    items = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        resp = obj.get('response')
        if isinstance(resp, list):
            items.extend(resp)
    return items


def count_duplicates(items):
    sku = Counter((str(i.get('codigo') or '').strip() for i in items if str(i.get('codigo') or '').strip()))
    bc = Counter((str(i.get('codigo_barra') or '').strip() for i in items if str(i.get('codigo_barra') or '').strip()))
    return sum(1 for _, n in sku.items() if n > 1), sum(1 for _, n in bc.items() if n > 1)


def csv_counter(path: Path, col: str):
    if not path.exists():
        return Counter()
    with path.open(encoding='utf-8') as f:
        rows = [{k.lstrip('\ufeff'): v for k, v in r.items()} for r in csv.DictReader(f)]
    return Counter(r.get(col, '') for r in rows)


def main():
    ap = argparse.ArgumentParser(description='Simulación de análisis de migración usando raw.log y outputs CSV existentes')
    ap.add_argument('--raw-log', default='docs/odoo_import_templates/raw.log')
    ap.add_argument('--outputs-dir', default='docs/odoo_import_templates')
    ap.add_argument('--out', default='docs/odoo_import_templates/simulation_report.json')
    args = ap.parse_args()

    raw = Path(args.raw_log)
    outdir = Path(args.outputs_dir)
    items = load_raw_items(raw)
    dup_sku, dup_bc = count_duplicates(items)

    migration_errors = csv_counter(outdir / 'migration_errors.csv', 'problema')
    phase2_issues = csv_counter(outdir / 'odoo_phase2_variant_internal_reference_validation.csv', 'issue_type')

    report = {
        'raw_items': len(items),
        'raw_duplicate_sku_keys': dup_sku,
        'raw_duplicate_barcode_keys': dup_bc,
        'migration_errors_by_type': dict(migration_errors),
        'phase2_issues_by_type': dict(phase2_issues),
        'recommendations': [
            'Mantener exclusión de stock 0 para limpieza (regla vigente).',
            'Conservar excepción por grupo/código madre con stock > 0 para incluir variantes.',
            'Revisar catálogo de atributos Odoo para bajar Empty Variant Values/Invalid attribute value.',
            'Corregir SKUs/barcodes duplicados desde origen para evitar ambigüedad operativa.'
        ]
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
