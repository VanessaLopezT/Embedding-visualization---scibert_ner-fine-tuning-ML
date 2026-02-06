"""
Procesamiento de NER con SciBERT
Divide textos largos en chunks y aplica NER
Guarda resultados en JSON + embeddings por entidad

Puede procesar:
- Textos directos como argumentos
- Artículos académicos en inglés (se procesan automáticamente con prepare_article.py)
"""

import torch
import json
import argparse
import numpy as np
from pathlib import Path
from tqdm import tqdm
import time
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

# CONFIGURACION
DEFAULT_CHECKPOINT = "checkpoint-90"


def process_article_if_needed(text_input):
    """
    Detecta si text_input es un archivo de artículo (.txt)
    Si lo es, lo procesa con prepare_article.py y retorna los párrafos procesados
    Si no, retorna el texto original
    """
    path = Path(text_input)
    
    # Verificar si es un archivo .txt
    if path.exists() and path.suffix.lower() == ".txt":
        print(f"\nDetectado archivo de artículo: {text_input}")
        print("Procesando artículo con prepare_article.py...")
        
        try:
            # Importar dinámicamente prepare_article
            import sys
            sys.path.insert(0, str(path.parent))
            from prepare_article import ArticlePreprocessor
            
            preprocessor = ArticlePreprocessor()
            if not preprocessor.load_article(str(path)):
                print(f"Error al cargar artículo. Usando texto directo.")
                return [text_input]
            
            preprocessor.clean()
            paragraphs = preprocessor.get_paragraphs()
            
            print(f"Artículo procesado: {len(paragraphs)} párrafos extraídos")
            return paragraphs
            
        except ImportError:
            print("Error: No se encontró prepare_article.py")
            print("Asegúrate de que prepare_article.py esté en el mismo directorio")
            return [text_input]
        except Exception as e:
            print(f"Error procesando artículo: {e}")
            return [text_input]
    
    # Si no es un archivo, retornar como texto directo
    return [text_input]


class SciBERTNERProcessor:
    def __init__(self, checkpoint_path=DEFAULT_CHECKPOINT):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.checkpoint_path = checkpoint_path
        
        print(f"Cargando modelo desde: {checkpoint_path}")
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint_path)
        self.model = AutoModelForTokenClassification.from_pretrained(checkpoint_path)
        self.model.to(self.device)
        self.model.eval()
        
        self.ner_pipeline = pipeline(
            "token-classification",
            model=self.model,
            tokenizer=self.tokenizer,
            device=0 if self.device == "cuda" else -1,
            aggregation_strategy="simple"
        )

    def chunk_text(self, text, max_tokens=400, overlap=50):
        tokens = text.split()
        if len(tokens) <= max_tokens:
            return [text]

        chunks, start = [], 0
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            chunks.append(" ".join(tokens[start:end]))
            start = end - overlap
        return chunks

    def process_texts(
        self,
        texts,
        output_file="ner_results.json",
        entity_embeddings_file="entity_embeddings.npz"
    ):
        print("\nProcesando textos con NER...")
        start_time = time.time()

        results = []

        entity_embeddings = []
        entity_labels = []
        entity_texts = []
        entity_text_index = []
        entity_sentence_texts = []
        entity_sentence_ids = []
        entity_offsets = []

        with torch.no_grad():
            for text_idx, text in enumerate(tqdm(texts, desc="Procesando", ncols=70)):
                chunks = self.chunk_text(text)
                all_entities = []

                for chunk in chunks:
                    entities = self.ner_pipeline(chunk)
                    for e in entities:
                        e["score"] = float(e["score"])
                    all_entities.extend(entities)

                    inputs = self.tokenizer(
                        chunk,
                        return_tensors="pt",
                        truncation=True,
                        max_length=512,
                        return_offsets_mapping=True
                    )
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
                        entity_text = chunk[start:end]

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

        elapsed = time.time() - start_time
        print(f"Procesamiento completado en {elapsed:.2f}s\n")

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"NER guardado en: {output_file}")

        np.savez_compressed(
            entity_embeddings_file,
            embeddings=np.array(entity_embeddings),
            labels=np.array(entity_labels),
            texts=np.array(entity_texts),
            text_index=np.array(entity_text_index),
            sentence_texts=np.array(entity_sentence_texts),
            sentence_ids=np.array(entity_sentence_ids)
        )
        print(f"Embeddings por entidad guardados en: {entity_embeddings_file}")

        # Ejecutar visualize_tsne_prepare automáticamente
        print("\nGenerando visualización t-SNE...")
        self._run_tsne_visualization(entity_embeddings_file, output_file)

        return results

    def _run_tsne_visualization(self, embeddings_file, ner_output_file):
        """
        Ejecuta visualize_tsne_prepare.py automáticamente después del procesamiento NER
        Determina el archivo de salida basado en el archivo de entrada
        """
        try:
            # Importar dinámicamente visualize_tsne_prepare
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from visualize_tsne_prepare import main as tsne_main
            
            # Determinar archivo de salida para t-SNE
            if "article" in ner_output_file:
                tsne_output = "web/tsne_data_article.json"
            else:
                tsne_output = "web/tsne_data.json"
            
            # Crear argumentos simulados
            class Args:
                def __init__(self):
                    self.embeddings = embeddings_file
                    self.output = tsne_output
            
            args = Args()
            
            # Ejecutar visualize_tsne_prepare
            tsne_main(args.embeddings, args.output)
            print(f"Visualización t-SNE generada en: {args.output}")
            
        except ImportError as e:
            print(f"Advertencia: No se pudo importar visualize_tsne_prepare: {e}")
            print("Asegúrate de que visualize_tsne_prepare.py esté en el mismo directorio")
        except Exception as e:
            print(f"Advertencia: Error al generar visualización t-SNE: {e}")
            print("Puedes ejecutar visualize_tsne_prepare.py manualmente si es necesario")


def main():
    parser = argparse.ArgumentParser(
        description="Procesar textos o artículos académicos con NER SciBERT"
    )
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output", default="ner_results.json")
    parser.add_argument("--text", nargs="+", help="Textos directos o ruta a archivo .txt de artículo")

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
        # Procesar cada argumento (puede ser un artículo .txt o texto directo)
        for text_input in args.text:
            processed = process_article_if_needed(text_input)
            texts_to_process.extend(processed)

    processor = SciBERTNERProcessor(args.checkpoint)
    processor.process_texts(texts_to_process, output_file=args.output)


if __name__ == "__main__":
    main()
