"""
Runtime de procesamiento en background para articulos.

Objetivos:
- Mantener compatibilidad con las rutas y archivos actuales.
- Procesar trabajos mediante colas por modelo.
- Reutilizar el modelo cargado entre articulos del mismo modelo.
- Reutilizar cleaned_text.txt cuando ya exista (por ejemplo, en reprocess).
"""

from __future__ import annotations

import gc
import json
import os
import queue
import re
import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


DATA_DIR = settings.DATA_DIR
ARTICLES_DIR = DATA_DIR / "articles"
PROCESSING_DIR = settings.BASE_DIR / "processing"

ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

MAX_ACTIVE_JOBS = max(1, int(getattr(settings, "PROCESSING_MAX_ACTIVE_JOBS", 1)))
WORKER_IDLE_SECONDS = max(60, int(getattr(settings, "PROCESSING_WORKER_IDLE_SECONDS", 600)))
_ACTIVE_JOB_SEMAPHORE = threading.BoundedSemaphore(MAX_ACTIVE_JOBS)


def _article_dir(article_id: str) -> Path:
    return ARTICLES_DIR / article_id


def _meta_path(article_id: str) -> Path:
    return _article_dir(article_id) / "meta.json"


def _progress_path(article_id: str) -> Path:
    return _article_dir(article_id) / "progress.json"


def _tsne_path(article_id: str, model_key: str) -> Path:
    return _article_dir(article_id) / f"tsne_{model_key}.json"


def _ner_path(article_id: str, model_key: str) -> Path:
    return _article_dir(article_id) / f"ner_{model_key}.json"


def _cleaned_text_path(article_id: str) -> Path:
    return _article_dir(article_id) / "cleaned_text.txt"


def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_progress(article_id: str, payload: dict):
    try:
        _write_json(_progress_path(article_id), payload)
    except Exception:
        pass


def _ensure_processing_import_path():
    processing_dir_str = str(PROCESSING_DIR)
    if processing_dir_str not in sys.path:
        sys.path.insert(0, processing_dir_str)


@dataclass(frozen=True)
class ArticleJob:
    article_id: str
    raw_path: Path
    model_key: str
    checkpoint_path: str


class ModelWorker(threading.Thread):
    """
    Worker dedicado a un modelo.

    Cada worker procesa los trabajos de su cola de forma secuencial y mantiene
    el modelo cargado en memoria entre trabajos exitosos.
    """

    def __init__(self, model_key: str):
        super().__init__(name=f"article-worker-{model_key}", daemon=True)
        self.model_key = model_key
        self._jobs: "queue.Queue[ArticleJob]" = queue.Queue()
        self._processor = None
        self._checkpoint_path: str | None = None
        self._processor_lock = threading.Lock()

    def submit(self, job: ArticleJob):
        self._jobs.put(job)

    def run(self):
        while True:
            try:
                job = self._jobs.get(timeout=WORKER_IDLE_SECONDS)
            except queue.Empty:
                self._reset_processor()
                continue
            try:
                self._process_job(job)
            except Exception:
                tb = traceback.format_exc()
                print(f"[ERROR] Worker {self.model_key}:\n{tb}")
            finally:
                self._jobs.task_done()

    def _process_job(self, job: ArticleJob):
        meta = _read_json(_meta_path(job.article_id))
        try:
            with _ACTIVE_JOB_SEMAPHORE:
                _write_json(_meta_path(job.article_id), {
                    **meta,
                    "status": "processing",
                    "stage": "processing",
                    "model": job.model_key,
                    "error": None,
                })
                _write_progress(job.article_id, {
                    "stage": "processing",
                    "percent": 10,
                    "processed": 0,
                    "total": 0,
                })

                paragraphs, cleaned_text = _prepare_article_inputs(job.article_id, job.raw_path)
                if not paragraphs:
                    raise ValueError("No se pudo extraer texto del documento.")

                cleaned_path = _cleaned_text_path(job.article_id)
                cleaned_path.write_text(cleaned_text, encoding="utf-8")

                _write_json(_meta_path(job.article_id), {
                    **meta,
                    "status": "processing",
                    "stage": "ner",
                    "model": job.model_key,
                    "error": None,
                })
                _write_progress(job.article_id, {
                    "stage": "ner",
                    "percent": 30,
                    "processed": 0,
                    "total": len(paragraphs),
                })

                processor = self._get_or_load_processor(job.checkpoint_path)
                article_dir = _article_dir(job.article_id)

                processor.process_texts(
                    paragraphs,
                    output_file=str(_ner_path(job.article_id, job.model_key)),
                    entity_embeddings_file=str(article_dir / f"embeddings_{job.model_key}.npz"),
                    tsne_output=str(_tsne_path(job.article_id, job.model_key)),
                    progress_file=str(_progress_path(job.article_id)),
                )

                _write_json(_meta_path(job.article_id), {
                    **meta,
                    "status": "processed",
                    "stage": "completed",
                    "model": job.model_key,
                    "error": None,
                })
        except Exception as exc:
            self._reset_processor()
            tb = traceback.format_exc()
            print(f"[ERROR] Procesando articulo {job.article_id}:\n{tb}")
            _write_json(_meta_path(job.article_id), {
                **meta,
                "status": "failed",
                "stage": "failed",
                "model": job.model_key,
                "error": str(exc),
            })
            _write_progress(job.article_id, {
                "stage": "failed",
                "percent": 100,
                "error": str(exc),
            })
        finally:
            _COORDINATOR.mark_done(job.article_id, job.model_key)

    def _get_or_load_processor(self, checkpoint_path: str):
        with self._processor_lock:
            if self._processor is not None and self._checkpoint_path == checkpoint_path:
                return self._processor

            self._unload_locked()
            self._processor = _load_processor(checkpoint_path)
            self._checkpoint_path = checkpoint_path
            return self._processor

    def _reset_processor(self):
        with self._processor_lock:
            self._unload_locked()

    def _unload_locked(self):
        if self._processor is None:
            self._checkpoint_path = None
            return
        try:
            self._processor.unload()
        except Exception:
            pass
        self._processor = None
        self._checkpoint_path = None
        gc.collect()


class ProcessingCoordinator:
    def __init__(self):
        self._lock = threading.Lock()
        self._workers: dict[str, ModelWorker] = {}
        self._pending_keys: set[tuple[str, str]] = set()

    def submit(self, article_id: str, raw_path: Path, model_key: str, checkpoint_path: str) -> bool:
        job_key = (article_id, model_key)
        with self._lock:
            if job_key in self._pending_keys:
                return False
            self._pending_keys.add(job_key)
            worker = self._get_worker_locked(model_key)

        worker.submit(ArticleJob(
            article_id=article_id,
            raw_path=Path(raw_path),
            model_key=model_key,
            checkpoint_path=checkpoint_path,
        ))
        return True

    def mark_done(self, article_id: str, model_key: str):
        with self._lock:
            self._pending_keys.discard((article_id, model_key))

    def _get_worker_locked(self, model_key: str) -> ModelWorker:
        worker = self._workers.get(model_key)
        if worker is None:
            worker = ModelWorker(model_key)
            worker.start()
            self._workers[model_key] = worker
        return worker


_COORDINATOR = ProcessingCoordinator()


def submit_article_job(article_id: str, raw_path: Path, model_key: str, checkpoint_path: str) -> bool:
    return _COORDINATOR.submit(article_id, raw_path, model_key, checkpoint_path)


def _load_processor(checkpoint_path: str):
    _ensure_processing_import_path()
    from process_ner import SciBERTNERProcessor

    processor = SciBERTNERProcessor.__new__(SciBERTNERProcessor)
    _init_processor(processor, checkpoint_path)
    return processor


def _init_processor(processor, checkpoint_path: str):
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

    device = "cuda" if torch.cuda.is_available() else "cpu"
    ckpt = Path(checkpoint_path)
    if not ckpt.is_absolute():
        ckpt = settings.BASE_DIR / checkpoint_path
    ckpt = ckpt.resolve()

    if not ckpt.exists():
        raise FileNotFoundError(f"Checkpoint no encontrado: {ckpt}")

    original_cwd = os.getcwd()
    try:
        os.chdir(str(ckpt))
        processor.device = device
        processor.tokenizer = AutoTokenizer.from_pretrained(".", local_files_only=True)
        processor.tokenizer.model_max_length = 512
        processor.model = AutoModelForTokenClassification.from_pretrained(".", local_files_only=True)
    finally:
        os.chdir(original_cwd)

    processor.model.to(device)
    processor.model.eval()
    processor.ner_pipeline = pipeline(
        "token-classification",
        model=processor.model,
        tokenizer=processor.tokenizer,
        device=0 if device == "cuda" else -1,
        aggregation_strategy="simple",
    )
    processor._loaded = True


def _prepare_article_inputs(article_id: str, raw_path: Path):
    cached = _load_cached_cleaned_inputs(article_id)
    if cached is not None:
        return cached
    return _extract_and_clean(raw_path)


def _load_cached_cleaned_inputs(article_id: str):
    cleaned_path = _cleaned_text_path(article_id)
    if not cleaned_path.exists():
        return None

    try:
        cleaned_text = cleaned_path.read_text(encoding="utf-8")
    except Exception:
        return None

    if not cleaned_text.strip():
        return None

    paragraphs = _chunk_cleaned_text(cleaned_text)
    if not paragraphs:
        return None

    print(f"  [cache] reutilizando cleaned_text para {article_id} ({len(paragraphs)} chunks)")
    return paragraphs, cleaned_text


def _chunk_cleaned_text(cleaned_text: str) -> list[str]:
    _ensure_processing_import_path()

    try:
        from mod_chunker import chunk_text

        chunks = chunk_text(cleaned_text)
        return [chunk for chunk in chunks if str(chunk).strip()]
    except Exception:
        return [part.strip() for part in re.split(r"\n\s*\n", cleaned_text) if part.strip()]


def _extract_and_clean(raw_path: Path):
    """
    Pipeline modular de extraccion y limpieza.
    Devuelve: (chunks, cleaned_text)
    """
    _ensure_processing_import_path()
    suffix = raw_path.suffix.lower()

    try:
        from mod_chunker import chunk_text
        from mod_extractor import extract_text
        from mod_sections import clean_all_sections
        from mod_symbols import clean_symbols
        from mod_tables import mark_tables

        if suffix == ".pdf":
            result = extract_text(str(raw_path))
            raw_text = result["text"] if result["success"] else ""
            print(f"  [extractor] motor={result['engine']} layout={result['layout']}")
        else:
            raw_text = raw_path.read_text(encoding="utf-8", errors="replace")

        if not raw_text.strip():
            raise ValueError("Extraccion vacia")

        text = clean_all_sections(raw_text)
        text = mark_tables(text)
        text = re.sub(r"<<TABLE_START>>.*?<<TABLE_END>>", "", text, flags=re.DOTALL)
        text = clean_symbols(text)

        chunks = [chunk for chunk in chunk_text(text) if chunk.strip()]
        print(f"  [pipeline] {len(chunks)} chunks tras limpieza modular")
        return chunks, text

    except Exception as exc:
        print(f"  [pipeline] Error en pipeline modular: {exc}. Usando prepare_article como fallback.")

    try:
        from prepare_article import ArticlePreprocessor

        preprocessor = ArticlePreprocessor()
        if not preprocessor.load_article(str(raw_path)):
            return [], ""
        preprocessor.clean()
        paragraphs = preprocessor.get_paragraphs()
        cleaned_text = preprocessor.text
        print(f"  [fallback] {len(paragraphs)} parrafos desde prepare_article")
        return paragraphs, cleaned_text
    except Exception as exc:
        print(f"  [fallback] prepare_article tambien fallo: {exc}")
        return [], ""
