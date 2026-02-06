import subprocess
import sys
import threading
import os
import json
from pathlib import Path
import shutil

from django.conf import settings

from .storage import update_status


def process_article(paths, checkpoint="checkpoint-90"):
    processing_dir = Path(settings.BASE_DIR) / "processing"
    process_script = processing_dir / "process_ner.py"
    prepare_script = processing_dir / "prepare_article.py"

    update_status(paths, "processing", stage="ner")
    _write_progress(paths.progress_file, {
        "stage": "loading",
        "percent": 5,
        "processed": 0,
        "total": 0,
        "eta_seconds": None,
    })

    source_ext = paths.source_file.suffix.lower()
    input_for_ner = paths.source_file

    # Si es PDF, limpiar con prepare_article.py y usar el TXT limpio
    if source_ext == ".pdf":
        prep_command = [
            sys.executable,
            str(prepare_script),
            str(paths.source_file),
            "--output",
            str(paths.cleaned_text),
        ]
        result = _run_streamed("prepare_article.py", prep_command)
        if result != 0:
            raise RuntimeError("Error ejecutando prepare_article.py (revisa la salida en consola).")
        input_for_ner = paths.cleaned_text
    elif source_ext == ".txt":
        # Mantener un cleaned_text consistente para TXT (copia directa)
        if not paths.cleaned_text.exists():
            paths.cleaned_text.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(paths.source_file, paths.cleaned_text)

    command = [
        sys.executable,
        str(process_script),
        "--checkpoint",
        checkpoint,
        "--text",
        str(input_for_ner),
        "--output",
        str(paths.ner_results),
        "--embeddings",
        str(paths.embeddings),
        "--tsne-output",
        str(paths.tsne_data),
        "--progress-file",
        str(paths.progress_file),
    ]

    env_overrides = {"SCIBERT_FAST": "1"}
    result = _run_streamed("process_ner.py", command, env_overrides=env_overrides)
    if result != 0:
        raise RuntimeError("Error ejecutando process_ner.py (revisa la salida en consola).")

    # Verificar que la salida exista; si no, intentar regenerar t-SNE
    if not paths.tsne_data.exists() and paths.embeddings.exists():
        update_status(paths, "processing", stage="tsne")
        generate_tsne_from_embeddings(paths.embeddings, paths.tsne_data)

    if not paths.tsne_data.exists():
        raise RuntimeError("No se generó tsne_data.json para el artículo.")


def generate_tsne_from_embeddings(embeddings_path, output_path):
    processing_dir = Path(settings.BASE_DIR) / "processing"
    tsne_script = processing_dir / "visualize_tsne_prepare.py"

    command = [
        sys.executable,
        str(tsne_script),
        "--embeddings",
        str(embeddings_path),
        "--output",
        str(output_path),
    ]

    result = _run_streamed("visualize_tsne_prepare.py", command)
    if result != 0:
        raise RuntimeError("Error ejecutando visualize_tsne_prepare.py (revisa la salida en consola).")


def _run_streamed(name, command, env_overrides=None):
    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(settings.BASE_DIR),
        env=env,
        bufsize=1,
    )

    def _drain(stream, label):
        if not stream:
            return
        for line in stream:
            line = line.rstrip()
            if not line:
                continue
            if label == "stderr":
                filtered = _filter_stderr(line)
                if not filtered:
                    continue
                print(f"[{name} stderr] {filtered}")
            else:
                print(f"[{name} stdout] {line}")

    t_out = threading.Thread(target=_drain, args=(process.stdout, "stdout"), daemon=True)
    t_err = threading.Thread(target=_drain, args=(process.stderr, "stderr"), daemon=True)
    t_out.start()
    t_err.start()
    exit_code = process.wait()
    t_out.join(timeout=1)
    t_err.join(timeout=1)
    return exit_code


def _filter_stderr(line):
    stripped = line.strip()
    if not stripped:
        return ""
    if stripped.startswith("Loading weights"):
        return ""
    if stripped.startswith("Procesando:"):
        return ""
    return line


def _write_progress(path, progress):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
