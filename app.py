"""
app.py
Servidor Flask para manejar upload de artículos científicos.
- Recibe artículos .txt o .pdf
- Ejecuta process_ner.py con prepare_article
- Ejecuta visualize_tsne_prepare.py automáticamente
- NO sobrescribe los datos de ejemplo originales

RUTAS PORTABLES: Usa rutas relativas para funcionar en cualquier PC
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import subprocess
import json
from pathlib import Path
import time
import sys

app = Flask(__name__)
CORS(app)

# Rutas relativas portables
PROJECT_ROOT = Path(__file__).parent
PROCESSING_DIR = PROJECT_ROOT / "processing"
WEB_DIR = PROJECT_ROOT / "web"


@app.route("/api/upload-article", methods=["POST"])
def upload_article():
    """
    Recibe un artículo .txt o .pdf y lo procesa
    """
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        # Aceptar .txt y .pdf
        allowed_extensions = [".txt", ".pdf"]
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_extensions:
            return jsonify({"error": "Solo archivos .txt y .pdf son permitidos"}), 400

        # Guardar archivo temporal en la carpeta processing
        temp_article = PROCESSING_DIR / ("temp_article" + file_ext)
        file.save(str(temp_article))
        print(f"Artículo recibido: {file.filename}")

        # Ejecutar process_ner.py desde la carpeta processing
        print("Ejecutando process_ner.py...")
        result = subprocess.run(
            [
                sys.executable,  # Usa el mismo intérprete Python
                str(PROCESSING_DIR / "process_ner.py"),
                "--text",
                str(temp_article),
                "--output",
                "ner_results_article.json"
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)  # Ejecuta desde la carpeta raíz del proyecto
        )

        if result.returncode != 0:
            return jsonify({"error": f"Error en process_ner: {result.stderr}"}), 500

        print("Proceso NER completado")

        print("Artículo procesado exitosamente")

        # Limpiar archivo temporal
        if temp_article.exists():
            temp_article.unlink()

        # Cargar y retornar los datos del artículo procesado
        data_file = WEB_DIR / "tsne_data_article.json"
        if data_file.exists():
            with open(data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return jsonify({
                "success": True,
                "message": "Artículo procesado correctamente",
                "timestamp": time.time(),
                "data": data,
                "source": "article"
            }), 200
        
        return jsonify({
            "success": True,
            "message": "Artículo procesado correctamente",
            "timestamp": time.time()
        }), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/get-data", methods=["GET"])
def get_data():
    """
    Retorna los datos de ejemplo (tsne_data.json) por defecto
    """
    data_file = WEB_DIR / "tsne_data.json"
    if data_file.exists():
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify({"data": data, "source": "example"}), 200
    return jsonify({"error": "No data available"}), 404


@app.route("/api/get-article-data", methods=["GET"])
def get_article_data():
    """
    Retorna los datos del artículo procesado (tsne_data_article.json)
    """
    data_file = WEB_DIR / "tsne_data_article.json"
    if data_file.exists():
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify({"data": data, "source": "article"}), 200
    return jsonify({"error": "No article data available"}), 404


@app.route("/", methods=["GET"])
def index():
    """Sirve la página principal"""
    return send_file(str(WEB_DIR / "index_text_view.html"))


@app.route("/<path:path>", methods=["GET"])
def serve_static(path):
    """Sirve archivos estáticos"""
    file_path = WEB_DIR / path
    if file_path.exists() and file_path.is_file():
        return send_file(str(file_path))
    return "File not found", 404


if __name__ == "__main__":
    print("=" * 60)
    print("SciBERT NER Visualization Server")
    print("=" * 60)
    print(f"Proyecto: {PROJECT_ROOT}")
    print(f"Processing: {PROCESSING_DIR}")
    print(f"Web: {WEB_DIR}")
    print("=" * 60)
    print("Servidor iniciado en http://localhost:5000")
    print("Abre el navegador y ve a http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, port=5000)
