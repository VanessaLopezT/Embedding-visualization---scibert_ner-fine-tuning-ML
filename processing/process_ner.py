"""
Procesamiento de NER con SciBERT
Divide textos largos en chunks y aplica NER
Guarda resultados en JSON + embeddings por entidad

Puede procesar:
- Textos directos como argumentos
- Archivos .txt/.pdf (se limpian antes con prepare_article.py)

RUTAS PORTABLES: Usa rutas relativas para funcionar en cualquier PC
"""

import torch
import json
import argparse
import numpy as np
from pathlib import Path
from tqdm import tqdm
import time
import os
import json
import re
import subprocess
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

# Modo rápido: evita t-SNE y usa PCA 2D como proyección visual
FAST_MODE = os.getenv("SCIBERT_FAST", "0") == "1"

# CONFIGURACION
DEFAULT_CHECKPOINT = "checkpoint-90"

# Rutas relativas portables (funciona en cualquier PC)
PROJECT_ROOT = Path(__file__).parent.parent  # Sube a la carpeta raíz
PROCESSING_DIR = Path(__file__).parent       # Carpeta actual (processing)


def process_article_if_needed(text_input):
    """
    Detecta si text_input es un archivo de artículo (.txt o .pdf)
    Si lo es, lo procesa con prepare_article.py y retorna los párrafos procesados
    Si no, retorna el texto original
    """
    path = Path(text_input)

    # Verificar si es un archivo .txt o .pdf
    if path.exists() and path.suffix.lower() in [".txt", ".pdf"]:
        print(f"\nDetectado archivo de artículo: {text_input}")

        # TXT: no limpiar, solo leer y devolver tal cual (dividir en párrafos simples)
        if path.suffix.lower() == ".txt":
            try:
                raw = path.read_text(encoding="utf-8")
                # Separar por líneas en blanco sin alterar contenido
                parts = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
                return parts if parts else [raw]
            except Exception as e:
                print(f"Error leyendo TXT: {e}")
                return [text_input]

        # PDF: limpiar con prepare_article.py
        print("Procesando artículo con prepare_article.py...")

        try:
            # Importar dinámicamente prepare_article
            import sys
            sys.path.insert(0, str(PROCESSING_DIR))
            from prepare_article import ArticlePreprocessor

            preprocessor = ArticlePreprocessor()
            if not preprocessor.load_article(str(path)):
                print("Error al cargar artículo. Usando texto directo.")
                return [text_input]

            preprocessor.clean()
            paragraphs = preprocessor.get_paragraphs()

            print(f"Artículo procesado: {len(paragraphs)} párrafos extraídos")
            return paragraphs

        except ImportError:
            print("Error: No se encontró prepare_article.py")
            print("Asegúrate de que prepare_article.py esté en la carpeta processing/")
            return [text_input]
        except Exception as e:
            print(f"Error procesando artículo: {e}")
            return [text_input]

    # Si no es un archivo, retornar como texto directo
    return [text_input]


class SciBERTNERProcessor:
    def __init__(self, checkpoint_path=DEFAULT_CHECKPOINT):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Ruta del checkpoint (relativa a PROJECT_ROOT)
        checkpoint = PROJECT_ROOT / checkpoint_path
        
        print(f"Cargando modelo desde: {checkpoint}")
        self.tokenizer = AutoTokenizer.from_pretrained(str(checkpoint))
        self.model = AutoModelForTokenClassification.from_pretrained(str(checkpoint))
        self.model.to(self.device)
        self.model.eval()
        
        self.ner_pipeline = pipeline(
            "token-classification",
            model=self.model,
            tokenizer=self.tokenizer,
            device=0 if self.device == "cuda" else -1,
            aggregation_strategy="simple"
        )

    def chunk_text(self, text, max_tokens=200, overlap=25):
        """Divide el texto en chunks por palabras para velocidad."""
        words = text.split() if text else []
        if len(words) <= max_tokens:
            return [text] if text else []

        chunks = []
        start = 0
        while start < len(words):
            end = min(start + max_tokens, len(words))
            chunks.append(" ".join(words[start:end]))
            start = max(end - overlap, 0)
        return chunks

    def _truncate_chunk_for_bert(self, chunk, max_length=512):
        """Asegura que el chunk no exceda el máximo de tokens del modelo."""
        if not chunk:
            return chunk
        token_ids = self.tokenizer(
            chunk,
            add_special_tokens=True,
            return_attention_mask=False,
            return_tensors=None,
            truncation=True,
            max_length=max_length,
        )["input_ids"]
        if len(token_ids) <= max_length:
            return chunk
        return self.tokenizer.decode(token_ids, skip_special_tokens=True)

    def process_texts(
        self,
        texts,
        output_file="ner_results.json",
        entity_embeddings_file="entity_embeddings.npz",
        tsne_output=None,
        progress_file=None
    ):
        print("\nProcesando textos con NER...")
        start_time = time.time()
        total_texts = len(texts)
        # Ajustes base
        token_limit = 320
        overlap = 25

        if progress_file:
            _write_progress(
                progress_file,
                {
                    "stage": "ner",
                    "percent": 5,
                    "processed": 0,
                    "total": total_texts,
                    "eta_seconds": None,
                },
            )

        results = []
        total_entities = 0

        entity_embeddings = []
        entity_labels = []
        entity_texts = []
        entity_text_index = []
        entity_sentence_texts = []
        entity_sentence_ids = []
        entity_offsets = []

        with torch.no_grad():
            for text_idx, text in enumerate(tqdm(texts, desc="Procesando", ncols=70)):
                chunks = self.chunk_text(text, max_tokens=token_limit, overlap=overlap)
                total_chunks = max(len(chunks), 1)
                all_entities = []
                for chunk_idx, chunk in enumerate(chunks):
                    try:
                        safe_chunk = self._truncate_chunk_for_bert(chunk, max_length=512)
                        entities = self.ner_pipeline(safe_chunk)
                    except Exception as e:
                        print(f"[ERROR] Fallo en NER del texto {text_idx + 1}, chunk {chunk_idx + 1}/{total_chunks}")
                        print(f"[ERROR] Detalle: {e}")
                        raise
                    for e in entities:
                        e["score"] = float(e["score"])
                    all_entities.extend(entities)

                    inputs = self.tokenizer(
                        safe_chunk,
                        return_tensors="pt",
                        truncation=True,
                        max_length=512,
                        return_offsets_mapping=True
                    )
                    # Seguridad extra por si el tokenizer no truncó correctamente
                    if inputs["input_ids"].shape[1] > 512:
                        inputs["input_ids"] = inputs["input_ids"][:, :512]
                        if "attention_mask" in inputs:
                            inputs["attention_mask"] = inputs["attention_mask"][:, :512]
                        if "token_type_ids" in inputs:
                            inputs["token_type_ids"] = inputs["token_type_ids"][:, :512]
                    offsets = inputs.pop("offset_mapping")[0]
                    inputs = {k: v.to(self.device) for k, v in inputs.items()}

                    outputs = self.model(**inputs, output_hidden_states=True)
                    hidden_states = outputs.hidden_states[-2][0]  # (seq_len, hidden)

                    for ent in entities:
                        start, end = ent["start"], ent["end"]

                        token_mask = [
                            i for i, (s, e) in enumerate(offsets.tolist())
                            if s >= start and e <= end and e > s
                        ]

                        if not token_mask:
                            continue

                        emb = hidden_states[token_mask].mean(dim=0).cpu().numpy()

                        # Extraer el texto real de la entidad
                        entity_text = safe_chunk[start:end]

                        entity_embeddings.append(emb)
                        entity_labels.append(ent["entity_group"])
                        entity_texts.append(entity_text)
                        entity_text_index.append(text_idx)
                        entity_sentence_texts.append(chunk)
                        entity_sentence_ids.append(text_idx)
                        entity_offsets.append({"start": start, "end": end})

                results.append({
                    "text": text,
                    "entities": all_entities
                })
                total_entities += len(all_entities)
                if progress_file:
                    percent = 5 + int(70 * (text_idx + 1) / max(total_texts, 1))
                    _write_progress(
                        progress_file,
                        {
                            "stage": "ner",
                            "percent": percent,
                            "processed": text_idx + 1,
                            "total": total_texts,
                            "eta_seconds": None,
                            "entities_extracted": total_entities,
                        },
                    )

        elapsed = time.time() - start_time
        print(f"Procesamiento completado en {elapsed:.2f}s\n")

        # Guardar con rutas relativas al PROJECT_ROOT
        output_path = PROJECT_ROOT / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"NER guardado en: {output_path.relative_to(PROJECT_ROOT)}")

        embeddings_path = PROJECT_ROOT / entity_embeddings_file
        embeddings_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            str(embeddings_path),
            embeddings=np.array(entity_embeddings),
            labels=np.array(entity_labels),
            texts=np.array(entity_texts),
            text_index=np.array(entity_text_index),
            sentence_texts=np.array(entity_sentence_texts),
            sentence_ids=np.array(entity_sentence_ids)
        )
        print(f"Embeddings por entidad guardados en: {embeddings_path.relative_to(PROJECT_ROOT)}")

        # Ejecutar visualize_tsne_prepare automáticamente
        print("\nGenerando visualización t-SNE...")
        if progress_file:
            _write_progress(
                progress_file,
                {
                    "stage": "tsne",
                    "percent": 85,
                    "processed": total_texts,
                    "total": total_texts,
                    "eta_seconds": None,
                    "entities_extracted": total_entities,
                },
            )
        self._run_tsne_visualization(str(embeddings_path), output_file, tsne_output)
        if progress_file:
            _write_progress(
                progress_file,
                {
                    "stage": "completed",
                    "percent": 100,
                    "processed": total_texts,
                    "total": total_texts,
                    "eta_seconds": 0,
                    "entities_extracted": total_entities,
                },
            )

        return results

    def _run_tsne_visualization(self, embeddings_file, ner_output_file, tsne_output=None):
        """
        Ejecuta visualize_tsne_prepare.py automáticamente después del procesamiento NER
        Determina el archivo de salida basado en el archivo de entrada
        """
        try:
            # Determinar archivo de salida para t-SNE si no se especifica
            if not tsne_output:
                if "article" in ner_output_file:
                    tsne_output = str(PROJECT_ROOT / "web" / "tsne_data_article.json")
                else:
                    tsne_output = str(PROJECT_ROOT / "web" / "tsne_data.json")

            if FAST_MODE:
                print("Modo rápido: usando PCA 2D en lugar de t-SNE.")
                self._export_pca_fallback(embeddings_file, tsne_output)
                return

            # Ejecutar visualize_tsne_prepare como subproceso con timeout
            tsne_script = PROCESSING_DIR / "visualize_tsne_prepare.py"
            command = [
                os.sys.executable,
                str(tsne_script),
                "--embeddings",
                str(embeddings_file),
                "--output",
                str(tsne_output),
            ]
            try:
                subprocess.run(command, check=True, timeout=45)
                print("Visualización t-SNE generada correctamente")
            except subprocess.TimeoutExpired:
                print("Advertencia: t-SNE tardó demasiado. Usando fallback PCA 2D.")
                self._export_pca_fallback(embeddings_file, tsne_output)
            except subprocess.CalledProcessError as e:
                print(f"Advertencia: t-SNE falló ({e}). Usando fallback PCA 2D.")
                self._export_pca_fallback(embeddings_file, tsne_output)

        except ImportError as e:
            print(f"Advertencia: No se pudo importar visualize_tsne_prepare: {e}")
            print("Asegúrate de que visualize_tsne_prepare.py esté en la carpeta processing/")
        except Exception as e:
            print(f"Advertencia: Error al generar visualización t-SNE: {e}")
            print("Puedes ejecutar visualize_tsne_prepare.py manualmente si es necesario")

    def _export_pca_fallback(self, embeddings_file, output_path):
        try:
            data = np.load(str(embeddings_file), allow_pickle=True)
            embeddings = data["embeddings"]
            labels = data["labels"]
            texts = data["texts"]
            text_index = data["text_index"]
            sentence_texts = data["sentence_texts"]
            sentence_ids = data["sentence_ids"]

            if len(embeddings) < 2:
                points = []
            else:
                scaler = StandardScaler()
                emb_norm = scaler.fit_transform(embeddings)
                pca = PCA(n_components=2, random_state=42)
                emb_2d = pca.fit_transform(emb_norm)

                points = []
                for i in range(len(emb_2d)):
                    points.append({
                        "id": i,
                        "x": float(emb_2d[i, 0]),
                        "y": float(emb_2d[i, 1]),
                        "label": labels[i],
                        "entity": texts[i],
                        "text_index": int(text_index[i]),
                        "sentence_id": int(sentence_ids[i]),
                        "sentence_text": str(sentence_texts[i]),
                    })

            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(str(out_path), "w", encoding="utf-8") as f:
                json.dump(points, f, ensure_ascii=False, indent=2)
            print("Fallback PCA 2D generado correctamente")
        except Exception as e:
            print(f"Advertencia: Error en fallback PCA 2D: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Procesar textos o artículos académicos con NER SciBERT"
    )
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output", default="ner_results.json")
    parser.add_argument("--embeddings", default="entity_embeddings.npz")
    parser.add_argument("--tsne-output", default=None)
    parser.add_argument("--progress-file", default=None)
    parser.add_argument("--text", nargs="+", help="Textos directos o ruta a archivo .txt/.pdf")

    args = parser.parse_args()

    texts_to_process = []
    if not args.text:
        # Textos por defecto si no se especifican
        texts_to_process = [
            "The Transformer architecture has revolutionized natural language processing. "
            "BERT and GPT are state-of-the-art models using attention mechanisms. "
            "ImageNet dataset contains millions of labeled images for computer vision tasks. "
            "The BLEU and ROUGE metrics are commonly used to evaluate machine translation systems.", 
            "Deep learning techniques like Convolutional Neural Networks and Recurrent Neural Networks have achieved impressive results. "
            "The ResNet architecture won the ImageNet competition. Transfer learning with models like BERT provides excellent accuracy. "
            "Common applications include sentiment analysis and named entity recognition.", 
            "The Vision Transformer model applies attention mechanisms to image processing. "
            "YOLO is a popular object detection model. The CIFAR-10 dataset is widely used for benchmarking. "
            "Accuracy and F1-score are standard evaluation metrics in machine learning research.", 
            "Large Language Models such as GPT-3 and PaLM have demonstrated remarkable capabilities. "
            "The Transformer-XL architecture improves upon standard Transformers. Word2Vec embeddings were pioneering in NLP technology. "
            "The SQuAD dataset revolutionized question answering evaluation."
        ]
    else:
        # Procesar cada argumento (puede ser un artículo .txt/.pdf o texto directo)
        for text_input in args.text:
            processed = process_article_if_needed(text_input)
            texts_to_process.extend(processed)

    processor = SciBERTNERProcessor(args.checkpoint)
    processor.process_texts(
        texts_to_process,
        output_file=args.output,
        entity_embeddings_file=args.embeddings,
        tsne_output=args.tsne_output,
        progress_file=args.progress_file
    )


def _write_progress(path, payload):
    if not path:
        return
    try:
        progress_path = Path(path)
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        with open(progress_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


if __name__ == "__main__":
    main()
