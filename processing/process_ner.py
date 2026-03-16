"""
Procesamiento de NER con SciBERT — versión optimizada en RAM
Divide textos largos en chunks y aplica NER
Guarda resultados en JSON + embeddings por entidad

OPTIMIZACIONES vs versión original:
  1. Método unload() para liberar modelo antes de cargar otro
  2. Solo se pide la penúltima hidden layer (no todas)
  3. Embeddings se escriben a disco incrementalmente (no se acumulan en RAM)
  4. Textos de oraciones se indexan, no se duplican por entidad
  5. Chunks se procesan y descartan (no se retienen)
  6. gc.collect() + torch.cuda.empty_cache() en puntos clave

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
import re
import gc
import subprocess
import tempfile
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

# Modo rápido: evita t-SNE y usa PCA 2D como proyección visual
FAST_MODE = os.getenv("SCIBERT_FAST", "0") == "1"

# CONFIGURACION
DEFAULT_CHECKPOINT = "scibert/checkpoint-120"

# Rutas relativas portables (funciona en cualquier PC)
PROJECT_ROOT = Path(__file__).parent.parent  # Sube a la carpeta raíz
PROCESSING_DIR = Path(__file__).parent       # Carpeta actual (processing)

# --- Límite de RAM suave (en GB) para decidir si hacer flush a disco ---
_RAM_FLUSH_THRESHOLD_ENTITIES = 5000  # flush embeddings cada N entidades


def process_article_if_needed(text_input):
    """
    Detecta si text_input es un archivo de artículo (.txt o .pdf)
    Si lo es, lo procesa con prepare_article.py y retorna los párrafos procesados
    Si no, retorna el texto original
    """
    path = Path(text_input)

    if path.exists() and path.suffix.lower() in [".txt", ".pdf"]:
        print(f"\nDetectado archivo de artículo: {text_input}")

        # TXT: leer y dividir en párrafos
        if path.suffix.lower() == ".txt":
            try:
                raw = path.read_text(encoding="utf-8")
                parts = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
                return parts if parts else [raw]
            except Exception as e:
                print(f"Error leyendo TXT: {e}")
                return [text_input]

        # PDF: limpiar con prepare_article.py
        print("Procesando artículo con prepare_article.py...")
        try:
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
            return [text_input]
        except Exception as e:
            print(f"Error procesando artículo: {e}")
            return [text_input]

    return [text_input]


class SciBERTNERProcessor:
    """
    Procesador NER optimizado en memoria.

    Uso típico desde un backend web (2 modelos secuenciales):

        proc1 = SciBERTNERProcessor("modelo_A/checkpoint")
        proc1.process_texts(...)
        proc1.unload()          # <-- libera RAM antes de cargar el segundo
        del proc1
        gc.collect()

        proc2 = SciBERTNERProcessor("modelo_B/checkpoint")
        proc2.process_texts(...)
        proc2.unload()
    """

    def __init__(self, checkpoint_path=DEFAULT_CHECKPOINT):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Ruta del checkpoint (relativa a PROJECT_ROOT)
        checkpoint = PROJECT_ROOT / checkpoint_path

        print(f"Cargando modelo desde: {checkpoint}")
        self.tokenizer = AutoTokenizer.from_pretrained(str(checkpoint))
        # Forzar límite de 512 tokens — algunos checkpoints no lo declaran explícitamente
        self.tokenizer.model_max_length = 512
        self.model = AutoModelForTokenClassification.from_pretrained(str(checkpoint))
        self.model.to(self.device)
        self.model.eval()

        self.ner_pipeline = pipeline(
            "token-classification",
            model=self.model,
            tokenizer=self.tokenizer,
            device=0 if self.device == "cuda" else -1,
            aggregation_strategy="simple",
        )

        self._loaded = True

    # ------------------------------------------------------------------ #
    #  LIBERACIÓN DE MEMORIA — llamar antes de cargar otro modelo         #
    # ------------------------------------------------------------------ #
    def unload(self):
        """Libera modelo, tokenizer y pipeline de la RAM/VRAM."""
        if not getattr(self, "_loaded", False):
            return

        print("Liberando modelo de memoria...")

        # 1. Eliminar pipeline (tiene refs internas al modelo)
        if hasattr(self, "ner_pipeline"):
            del self.ner_pipeline

        # 2. Mover modelo a CPU antes de eliminar (evita leak en CUDA)
        if hasattr(self, "model") and self.model is not None:
            self.model.cpu()
            del self.model

        # 3. Eliminar tokenizer
        if hasattr(self, "tokenizer"):
            del self.tokenizer

        self._loaded = False

        # 4. Forzar recolección
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

        print("Modelo liberado correctamente.")

    def __del__(self):
        """Safety net: liberar al destruirse el objeto."""
        try:
            self.unload()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  CHUNKING                                                           #
    # ------------------------------------------------------------------ #
    def chunk_text(self, text, max_tokens=200, overlap=25):
        """Divide el texto en chunks por palabras."""
        words = text.split() if text else []
        if len(words) <= max_tokens:
            return [text] if text else []

        chunks = []
        start = 0
        while start < len(words):
            end = min(start + max_tokens, len(words))
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            if end >= len(words):
                break
            start = end - overlap
        return chunks

    def _truncate_chunk_for_bert(self, chunk, max_length=512):
        """
        Garantiza que el chunk no supere max_length tokens BERT.
        Siempre tokeniza y decodifica para que el texto resultante
        sea seguro sin importar la versión de transformers instalada.
        El pipeline nunca necesita truncar por sí mismo.
        """
        if not chunk:
            return chunk
        # Tokenizar con truncation explícito aquí (tokenizer directo, no pipeline)
        encoded = self.tokenizer(
            chunk,
            add_special_tokens=False,   # sin [CLS]/[SEP] para contar tokens útiles
            return_attention_mask=False,
            return_tensors=None,
            truncation=True,
            max_length=max_length - 2,  # reservar 2 para [CLS] y [SEP]
        )
        token_ids = encoded["input_ids"]
        # Siempre decodificar para devolver texto limpio y dentro del límite
        return self.tokenizer.decode(token_ids, skip_special_tokens=True)

    # ------------------------------------------------------------------ #
    #  PROCESAMIENTO PRINCIPAL                                            #
    # ------------------------------------------------------------------ #
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
        token_limit = 320
        overlap = 25

        if progress_file:
            _write_progress(progress_file, {
                "stage": "ner", "percent": 5,
                "processed": 0, "total": total_texts, "eta_seconds": None,
            })

        # --------------------------------------------------------------- #
        #  Almacenamiento incremental: escribimos embeddings a un archivo  #
        #  temporal en disco en lugar de acumular todo en RAM.             #
        # --------------------------------------------------------------- #
        embeddings_path = PROJECT_ROOT / entity_embeddings_file
        embeddings_path.parent.mkdir(parents=True, exist_ok=True)

        # Buffers parciales (se flushean a disco periódicamente)
        buf_embeddings = []
        buf_labels = []
        buf_texts = []
        buf_text_index = []
        buf_sentence_ids = []
        buf_offsets = []

        # Mapa de oraciones únicas para no duplicar strings pesados
        sentence_store = []   # lista indexada de textos de chunk únicos
        sentence_map = {}     # chunk_text -> índice en sentence_store

        # Archivo temporal para ir acumulando embeddings parciales
        tmp_dir = tempfile.mkdtemp(prefix="scibert_emb_")
        flush_counter = 0
        flushed_files = []

        total_entities = 0

        # Resultados NER (solo entidades ligeras, sin embeddings)
        results = []

        def _flush_buffers():
            nonlocal flush_counter
            if not buf_embeddings:
                return
            part_path = os.path.join(tmp_dir, f"part_{flush_counter:04d}.npz")
            np.savez_compressed(
                part_path,
                embeddings=np.array(buf_embeddings, dtype=np.float32),
                labels=np.array(buf_labels),
                texts=np.array(buf_texts),
                text_index=np.array(buf_text_index, dtype=np.int32),
                sentence_ids=np.array(buf_sentence_ids, dtype=np.int32),
            )
            flushed_files.append(part_path)
            flush_counter += 1
            buf_embeddings.clear()
            buf_labels.clear()
            buf_texts.clear()
            buf_text_index.clear()
            buf_sentence_ids.clear()
            buf_offsets.clear()
            gc.collect()

        with torch.no_grad():
            for text_idx, text in enumerate(tqdm(texts, desc="Procesando", ncols=70)):
                chunks = self.chunk_text(text, max_tokens=token_limit, overlap=overlap)
                all_entities = []

                for chunk_idx, chunk in enumerate(chunks):
                    # --- NER ---
                    try:
                        safe_chunk = self._truncate_chunk_for_bert(chunk, max_length=512)
                        entities = self.ner_pipeline(safe_chunk)  # ya truncado por _truncate_chunk_for_bert
                    except Exception as e:
                        print(f"[ERROR] texto {text_idx+1}, chunk {chunk_idx+1}: {e}")
                        raise

                    for e in entities:
                        e["score"] = float(e["score"])
                    all_entities.extend(entities)

                    # Si no hay entidades en este chunk, no necesitamos embeddings
                    if not entities:
                        continue

                    # --- Embeddings (solo penúltima capa) ---
                    inputs = self.tokenizer(
                        safe_chunk,
                        return_tensors="pt",
                        truncation=True,
                        max_length=512,
                        return_offsets_mapping=True
                    )

                    # Seguridad: truncar si excede 512
                    for key in ("input_ids", "attention_mask", "token_type_ids"):
                        if key in inputs and inputs[key].shape[1] > 512:
                            inputs[key] = inputs[key][:, :512]

                    offsets = inputs.pop("offset_mapping")[0]
                    inputs = {k: v.to(self.device) for k, v in inputs.items()}

                    # ⚡ OPTIMIZACIÓN CLAVE: solo pedir hidden states, y
                    # extraer solo la penúltima capa inmediatamente
                    outputs = self.model(**inputs, output_hidden_states=True)
                    # Copiar solo la capa que necesitamos a CPU y liberar el resto
                    penultimate = outputs.hidden_states[-2][0].cpu()
                    # Eliminar outputs completos (todas las capas) de memoria
                    del outputs
                    if self.device == "cuda":
                        torch.cuda.empty_cache()

                    # Indexar el chunk de oración (dedup)
                    if safe_chunk not in sentence_map:
                        sid = len(sentence_store)
                        sentence_store.append(safe_chunk)
                        sentence_map[safe_chunk] = sid
                    else:
                        sid = sentence_map[safe_chunk]

                    for ent in entities:
                        start, end = ent["start"], ent["end"]
                        token_mask = [
                            i for i, (s, e) in enumerate(offsets.tolist())
                            if s >= start and e <= end and e > s
                        ]
                        if not token_mask:
                            continue

                        emb = penultimate[token_mask].mean(dim=0).numpy()

                        buf_embeddings.append(emb)
                        buf_labels.append(ent["entity_group"])
                        buf_texts.append(safe_chunk[start:end])
                        buf_text_index.append(text_idx)
                        buf_sentence_ids.append(sid)

                    # Liberar tensores del chunk
                    del penultimate, offsets, inputs
                    # Fin del chunk

                results.append({
                    "text": text,
                    "entities": all_entities
                })
                total_entities += len(all_entities)

                # Flush periódico a disco
                if len(buf_embeddings) >= _RAM_FLUSH_THRESHOLD_ENTITIES:
                    _flush_buffers()

                if progress_file:
                    percent = 5 + int(70 * (text_idx + 1) / max(total_texts, 1))
                    _write_progress(progress_file, {
                        "stage": "ner", "percent": percent,
                        "processed": text_idx + 1, "total": total_texts,
                        "eta_seconds": None, "entities_extracted": total_entities,
                    })

        # Flush final
        _flush_buffers()

        elapsed = time.time() - start_time
        print(f"Procesamiento completado en {elapsed:.2f}s\n")

        # ----------------------------------------------------------- #
        #  Consolidar archivos parciales en el .npz final              #
        # ----------------------------------------------------------- #
        if flushed_files:
            all_emb, all_lab, all_txt, all_tidx, all_sid = [], [], [], [], []
            for fp in flushed_files:
                d = np.load(fp, allow_pickle=True)
                all_emb.append(d["embeddings"])
                all_lab.append(d["labels"])
                all_txt.append(d["texts"])
                all_tidx.append(d["text_index"])
                all_sid.append(d["sentence_ids"])
                d.close()
                os.remove(fp)  # Liberar espacio en disco
            np.savez_compressed(
                str(embeddings_path),
                embeddings=np.concatenate(all_emb) if all_emb else np.array([]),
                labels=np.concatenate(all_lab) if all_lab else np.array([]),
                texts=np.concatenate(all_txt) if all_txt else np.array([]),
                text_index=np.concatenate(all_tidx) if all_tidx else np.array([]),
                sentence_ids=np.concatenate(all_sid) if all_sid else np.array([]),
                sentence_texts=np.array(sentence_store),
            )
            # Liberar listas de consolidación
            del all_emb, all_lab, all_txt, all_tidx, all_sid
            gc.collect()
        else:
            # Sin entidades
            np.savez_compressed(
                str(embeddings_path),
                embeddings=np.array([]),
                labels=np.array([]),
                texts=np.array([]),
                text_index=np.array([]),
                sentence_ids=np.array([]),
                sentence_texts=np.array(sentence_store),
            )

        # Limpiar directorio temporal
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass

        print(f"Embeddings guardados en: {embeddings_path.relative_to(PROJECT_ROOT)}")

        # Guardar resultados NER
        output_path = PROJECT_ROOT / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"NER guardado en: {output_path.relative_to(PROJECT_ROOT)}")

        # t-SNE / PCA
        print("\nGenerando visualización t-SNE...")
        if progress_file:
            _write_progress(progress_file, {
                "stage": "tsne", "percent": 85,
                "processed": total_texts, "total": total_texts,
                "eta_seconds": None, "entities_extracted": total_entities,
            })
        self._run_tsne_visualization(str(embeddings_path), output_file, tsne_output)
        if progress_file:
            _write_progress(progress_file, {
                "stage": "completed", "percent": 100,
                "processed": total_texts, "total": total_texts,
                "eta_seconds": 0, "entities_extracted": total_entities,
            })

        return results

    def _run_tsne_visualization(self, embeddings_file, ner_output_file, tsne_output=None):
        try:
            if not tsne_output:
                if "article" in ner_output_file:
                    tsne_output = str(PROJECT_ROOT / "web" / "tsne_data_article.json")
                else:
                    tsne_output = str(PROJECT_ROOT / "web" / "tsne_data.json")

            if FAST_MODE:
                print("Modo rápido: usando PCA 2D en lugar de t-SNE.")
                self._export_pca_fallback(embeddings_file, tsne_output)
                return

            tsne_script = PROCESSING_DIR / "visualize_tsne_prepare.py"
            command = [
                os.sys.executable, str(tsne_script),
                "--embeddings", str(embeddings_file),
                "--output", str(tsne_output),
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
        except Exception as e:
            print(f"Advertencia: Error al generar visualización t-SNE: {e}")

    def _export_pca_fallback(self, embeddings_file, output_path):
        try:
            data = np.load(str(embeddings_file), allow_pickle=True)
            embeddings = data["embeddings"]
            labels = data["labels"]
            texts = data["texts"]
            text_index = data["text_index"]
            sentence_ids = data["sentence_ids"]
            sentence_texts = data["sentence_texts"]

            if len(embeddings) < 2:
                points = []
            else:
                scaler = StandardScaler()
                emb_norm = scaler.fit_transform(embeddings)
                pca = PCA(n_components=2, random_state=42)
                emb_2d = pca.fit_transform(emb_norm)

                points = []
                for i in range(len(emb_2d)):
                    sid = int(sentence_ids[i])
                    points.append({
                        "id": i,
                        "x": float(emb_2d[i, 0]),
                        "y": float(emb_2d[i, 1]),
                        "label": str(labels[i]),
                        "entity": str(texts[i]),
                        "text_index": int(text_index[i]),
                        "sentence_id": sid,
                        "sentence_text": str(sentence_texts[sid]) if sid < len(sentence_texts) else "",
                    })

                del emb_norm, emb_2d
                gc.collect()

            data.close()

            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(str(out_path), "w", encoding="utf-8") as f:
                json.dump(points, f, ensure_ascii=False, indent=2)
            print("Fallback PCA 2D generado correctamente")
        except Exception as e:
            print(f"Advertencia: Error en fallback PCA 2D: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Procesar textos o artículos académicos con NER SciBERT (optimizado)"
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
    # Liberar modelo al terminar
    processor.unload()


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