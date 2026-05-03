from __future__ import annotations

import csv
import json
import os
import random
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from ..contifico import ContificoAPIError, ContificoClient
from .service import OdooMigrationService, STOCK_COLUMNS

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class StockWorker:
    def __init__(self, run_id: str, client: ContificoClient, output_root: Path):
        self.run_id = run_id
        self.client = client
        self.output_root = output_root
        self.run_folder = output_root / run_id
        self.snapshot_path = self.run_folder / "products_snapshot.jsonl"
        self.state_path = self.run_folder / "stock_state.json"
        self.stock_csv = self.run_folder / "initial_stock.csv"
        self.debug_log = self.run_folder / "debug.log"
        self.error_report = self.run_folder / "stock_errors.csv"

        self.batch_size = int(os.getenv("STOCK_BATCH_SIZE", "25"))
        self.max_concurrency = max(1, int(os.getenv("STOCK_MAX_CONCURRENCY", "3")))
        self.rps_limit = float(os.getenv("STOCK_RPS_LIMIT", "3"))

        self._paused = threading.Event()
        self._stop = threading.Event()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def stop(self) -> None:
        self._stop.set()

    def run(self, retry_failed: bool = False) -> dict[str, Any]:
        svc = OdooMigrationService(self.client, output_root=self.output_root)
        state = svc._read_stock_state(self.state_path)
        snapshot = [json.loads(line) for line in self.snapshot_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        by_sku = {r.get("sku"): r for r in state}
        pending = deque()
        for item in snapshot:
            st = by_sku.get(item.get("sku"))
            if not st:
                continue
            if st.get("status") == "pending" or (retry_failed and st.get("status") == "error"):
                pending.append(item)
                if retry_failed and st.get("status") == "error":
                    st["status"] = "pending"

        rows = self._load_stock_rows()
        durations = []
        errors = []
        processed = 0
        started = time.time()
        next_allowed = 0.0

        while pending and not self._stop.is_set():
            if self._paused.is_set():
                time.sleep(0.2)
                continue
            batch = [pending.popleft() for _ in range(min(self.batch_size, len(pending)))]
            results: list[tuple[dict[str, Any], dict[str, float] | None, str | None, float]] = []
            lock = threading.Lock()

            def worker(item: dict[str, Any]):
                nonlocal next_allowed
                sku = item.get("sku") or ""
                begin = time.time()
                stock_map = item.get("stock_map") or {k: 0.0 for k in svc._warehouse_by_code}
                err = None
                try:
                    pid = item.get("id")
                    if pid:
                        while True:
                            now = time.time()
                            with lock:
                                wait = max(0.0, next_allowed - now)
                                if wait <= 0:
                                    next_allowed = now + (1.0 / max(self.rps_limit, 0.1))
                                    break
                            time.sleep(min(wait, 0.05))
                        stock_map = self._fetch_with_retry(svc, str(pid), stock_map)
                except Exception as exc:
                    err = str(exc)
                elapsed = time.time() - begin
                with lock:
                    results.append((item, stock_map if err is None else None, err, elapsed))

            threads = []
            for item in batch:
                while len([t for t in threads if t.is_alive()]) >= self.max_concurrency:
                    time.sleep(0.01)
                t = threading.Thread(target=worker, args=(item,), daemon=True)
                threads.append(t); t.start()
            for t in threads:
                t.join()

            for item, stock_map, err, elapsed in results:
                sku = item.get("sku") or ""
                st = by_sku.get(sku)
                processed += 1
                durations.append(elapsed)
                if not st:
                    continue
                if err:
                    st["status"] = "error"; st["retry_count"] = int(st.get("retry_count") or 0) + 1; st["last_error"] = err
                    errors.append({"sku": sku, "product_id": item.get("id") or "", "error": err})
                else:
                    st["status"] = "done"; st["last_error"] = ""
                    from .service import WAREHOUSE_TO_LOCATION
                    for wh, loc in WAREHOUSE_TO_LOCATION.items():
                        qty = float(stock_map.get(wh, 0) or 0)
                        if qty > 0:
                            rows.append({"sku": sku, "ubicacion_odoo": loc, "cantidad": f"{qty:.2f}", "costo_unitario": f"{float(item.get('cost') or 0):.2f}"})

            svc._write_csv(self.stock_csv, STOCK_COLUMNS, rows)
            svc._write_stock_state(self.state_path, state)
            self._write_errors(errors)
            self._append_debug(processed=processed, errors=errors, durations=durations, started=started)

        total = len(state)
        done = len([r for r in state if r.get("status") == "done"])
        failed = len([r for r in state if r.get("status") == "error"])
        pending_n = len([r for r in state if r.get("status") == "pending"])
        elapsed = max(time.time() - started, 0.001)
        throughput = processed / elapsed
        eta = (pending_n / throughput) if throughput > 0 else None
        return {"total": total, "done": done, "failed": failed, "pending": pending_n, "processed": processed, "throughput": throughput, "eta_seconds": eta}

    def _fetch_with_retry(self, svc: OdooMigrationService, product_id: str, base: dict[str, float]) -> dict[str, float]:
        attempts = 0
        while True:
            attempts += 1
            try:
                detail = self.client.get_product_stock(product_id)
                return svc._map_stock_detail(detail, base=base)
            except ContificoAPIError as exc:
                if exc.status_code not in RETRYABLE_STATUS or attempts >= 5:
                    raise
                backoff = (2 ** (attempts - 1)) * 0.4 + random.uniform(0, 0.25)
                time.sleep(backoff)

    def _load_stock_rows(self) -> list[dict[str, Any]]:
        if not self.stock_csv.exists():
            return []
        with self.stock_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def _write_errors(self, rows: list[dict[str, Any]]) -> None:
        with self.error_report.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["sku", "product_id", "error"])
            w.writeheader(); [w.writerow(r) for r in rows]

    def _append_debug(self, *, processed: int, errors: list[dict[str, Any]], durations: list[float], started: float) -> None:
        avg = (sum(durations) / len(durations)) if durations else 0.0
        elapsed = max(time.time() - started, 0.001)
        throughput = processed / elapsed
        line = f"stock_worker processed={processed} errors={len(errors)} throughput={throughput:.2f}/s avg_request={avg:.3f}s"
        with self.debug_log.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
