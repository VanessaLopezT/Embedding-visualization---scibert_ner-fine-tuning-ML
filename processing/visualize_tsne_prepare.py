"""
visualize_tsne_prepare.py
Genera proyecciones t-SNE de embeddings de entidades SciBERT

RUTAS PORTABLES: Usa rutas relativas para funcionar en cualquier PC
"""

import numpy as np
import json
from pathlib import Path
from sklearn.manifold import TSNE
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import argparse
import time

# Rutas relativas portables
PROJECT_ROOT = Path(__file__).parent.parent


def main(embeddings_file="entity_embeddings.npz", output="web/tsne_data.json"):
    # Convertir rutas a absolutas si son relativas
    if not Path(embeddings_file).is_absolute():
        embeddings_file = PROJECT_ROOT / embeddings_file
    if not Path(output).is_absolute():
        output = PROJECT_ROOT / output
    
    print(f"\n[CARGA] Embeddings desde: {embeddings_file}")
    data = np.load(str(embeddings_file), allow_pickle=True)

    embeddings = data["embeddings"]        # (N, 768)
    labels = data["labels"]                # entity_group
    texts = data["texts"]                  # palabra de la entidad
    text_index = data["text_index"]        # índice del texto original
    sentence_texts = data["sentence_texts"]  # texto completo de la frase
    sentence_ids = data["sentence_ids"]      # ID de la frase

    print(f"[OK] Entidades: {len(embeddings)}")
    if len(embeddings) < 2:
        print("[WARN] No hay suficientes entidades para t-SNE. Exportando JSON vacío.")
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(output_path), "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        return

    # STEP 0 — Normalización
    print("[STEP 0] Normalizando embeddings")
    scaler = StandardScaler()
    emb_norm = scaler.fit_transform(embeddings)

    # STEP 1 — PCA previo
    print("[STEP 1] Aplicando PCA previo")
    n_samples = emb_norm.shape[0]
    n_components = min(30, n_samples - 1)

    pca = PCA(n_components=n_components, random_state=42)
    emb_pca = pca.fit_transform(emb_norm)

    print(f"[OK] PCA: {embeddings.shape[1]}D -> {emb_pca.shape[1]}D")

    # STEP 2 — t-SNE
    print("[STEP 2] Ejecutando t-SNE")
    start = time.time()

    tsne = TSNE(
        n_components=2,
        random_state=42,
        perplexity=min(5, n_samples - 1),
        learning_rate="auto",
        early_exaggeration=12.0,
        max_iter=600,
        n_iter_without_progress=200,
        init="pca",
        method="exact" if n_samples <= 500 else "barnes_hut",
        verbose=1
    )

    emb_2d = tsne.fit_transform(emb_pca)

    print(f"[OK] t-SNE completado en {time.time() - start:.2f}s")

    # STEP 3 — Exportar JSON (SOLO proyección visual)
    print("[STEP 3] Exportando JSON para visualización")

    points = []
    for i in range(len(emb_2d)):
        points.append({
            "id": i,                                  # ID estable de la entidad
            "x": float(emb_2d[i, 0]),
            "y": float(emb_2d[i, 1]),
            "label": labels[i],                       # tipo de entidad
            "entity": texts[i],                       # texto real de la entidad
            "text_index": int(text_index[i]),         # índice del texto original
            "sentence_id": int(sentence_ids[i]),      # ID de la frase
            "sentence_text": str(sentence_texts[i])   # texto completo de la frase
        })

    # Crear carpeta de salida si no existe
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(str(output_path), "w", encoding="utf-8") as f:
        json.dump(points, f, ensure_ascii=False, indent=2)

    try:
        print(f"[OK] JSON generado correctamente: {output_path.relative_to(PROJECT_ROOT)}")
    except ValueError:
        print(f"[OK] JSON generado correctamente: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generar proyección t-SNE de embeddings de entidades SciBERT"
    )
    parser.add_argument(
        "--embeddings",
        default="entity_embeddings.npz",
        help="Archivo NPZ con embeddings y metadata"
    )
    parser.add_argument(
        "--output",
        default="web/tsne_data.json",
        help="Archivo JSON de salida para ECharts"
    )

    args = parser.parse_args()
    main(args.embeddings, args.output)
