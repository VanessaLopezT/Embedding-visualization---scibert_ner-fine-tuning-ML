"""
prepare_article.py
Archivo auxiliar para procesar artÃ­culos acadÃ©micos en inglÃ©s.
- Lee artÃ­culos en texto plano (.txt) o PDF (.pdf)
- Extrae texto de PDFs automÃ¡ticamente
- Limpia referencias, citas, figuras, tablas y contenido sin valor
- Extrae pÃ¡rrafos coherentes

RUTAS PORTABLES: Usa rutas relativas para funcionar en cualquier PC
"""

import re
import argparse
import sys
from pathlib import Path


class ArticlePreprocessor:
    """Preprocesa artÃ­culos acadÃ©micos para uso con SciBERT NER."""

    def __init__(self):
        self.text = ""
        self.source_type = None
        self.stats = {
            "pages": None,
            "chars_before": 0,
            "chars_after": 0,
            "removed_references": 0,
            "removed_citations": 0,
            "removed_figures_tables": 0,
            "removed_special_sections": 0,
            "removed_urls": 0,
            "paragraphs_before": 0,
            "paragraphs_after": 0,
        }

    def load_article(self, file_path):
        """Carga un artÃ­culo desde archivo .txt o .pdf"""
        try:
            file_path = Path(file_path)
            
            if file_path.suffix.lower() == ".pdf":
                self.source_type = "pdf"
                return self._load_pdf(file_path)
            elif file_path.suffix.lower() == ".txt":
                self.source_type = "txt"
                return self._load_txt(file_path)
            else:
                print(f"Error: Formato no soportado. Use .txt o .pdf")
                return False
                
        except Exception as e:
            print(f"Error al cargar archivo: {e}")
            return False

    def _load_txt(self, file_path):
        """Carga un archivo de texto plano"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.text = f.read()
            print(f"ArtÃ­culo TXT cargado: {file_path}")
            return True
        except FileNotFoundError:
            print(f"Error: No se encontrÃ³ el archivo {file_path}")
            return False

    def _load_pdf(self, file_path):
        """Carga un archivo PDF y extrae el texto - alternativa robusta"""
        try:
            # Intentar primero con PyPDF2 (mejor para PDFs complejos)
            try:
                try:
                    from pypdf import PdfReader
                    reader_name = "pypdf"
                except ImportError:
                    from PyPDF2 import PdfReader
                    reader_name = "PyPDF2"
                
                reader = PdfReader(file_path)
                text_parts = []
                
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text:
                        # Limpiar espacios pegados
                        text = self._fix_pdf_spacing(text)
                        text_parts.append(text)
                
                self.text = "\n\n".join(text_parts)
                self.stats["pages"] = len(reader.pages)
                print(f"ArtÃ­culo PDF cargado con {reader_name}: {file_path} ({len(reader.pages)} pÃ¡ginas)")
                return True
                
            except ImportError:
                # Si no estÃ¡ pypdf/PyPDF2, usar pdfplumber
                print("pypdf/PyPDF2 no disponible, usando pdfplumber...")
                import pdfplumber
                
                with pdfplumber.open(file_path) as pdf:
                    text_parts = []
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            page_text = self._fix_pdf_spacing(page_text)
                            text_parts.append(page_text)
                    
                    self.text = "\n\n".join(text_parts)
                    self.stats["pages"] = len(pdf.pages)
                
                print(f"ArtÃ­culo PDF cargado con pdfplumber: {file_path} ({len(pdf.pages)} pÃ¡ginas)")
                return True
            
        except ImportError as e:
            print("Error: No hay librerÃ­as PDF disponibles")
            print("Instala con: pip install pypdf pdfplumber")
            return False
        except Exception as e:
            print(f"Error al cargar PDF: {e}")
            return False

    def _fix_pdf_spacing(self, text):
        """Arregla espaciado pobre de PDFs"""
        import re
        # Normalizar caracteres raros/ligaduras comunes en PDFs
        text = text.replace("\u00ad", "")  # soft hyphen
        text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
        text = text.replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
        text = text.replace("\u2022", " ").replace("\u00b7", " ")
        text = text.replace("\u00a0", " ")  # nonâ€‘breaking space
        # Unir palabras cortadas por guion al final de lÃ­nea
        text = re.sub(r'-\n(\w)', r'\1', text)
        
        # 1. Reemplazar saltos de lÃ­nea sin espacios
        text = re.sub(r'([a-zÃ¡Ã©Ã­Ã³ÃºÃ±])\n([a-zÃ¡Ã©Ã­Ã³ÃºÃ±])', r'\1 \2', text, flags=re.IGNORECASE)
        
        # 2. Agregar espacio despuÃ©s de puntos si no tienen
        text = re.sub(r'\.([A-Z])', r'. \1', text)
        
        # 3. Arreglar CamelCase (MachinelearningModel -> Machine learning Model)
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        
        # 4. Arreglar palabras pegadas con nÃºmeros (word1word2 -> word1 word2)
        text = re.sub(r'([a-z])([A-Z][a-z]+)', r'\1 \2', text)
        
        # 5. Limpiar espacios mÃºltiples
        text = re.sub(r' +', ' ', text)
        
        # 6. Limpiar tabs
        text = re.sub(r'\t+', ' ', text)
        
        # 7. Limpiar mÃºltiples saltos de lÃ­nea
        text = re.sub(r'\n\n+', '\n\n', text)
        
        return text.strip()

    def _normalize_pdf_text(self):
        """Normaliza texto de PDF para reducir tokens inflados."""
        # Remover caracteres de control invisibles
        self.text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", self.text)
        # Colapsar repeticiones largas de sÃ­mbolos
        self.text = re.sub(r"[_\-]{4,}", " ", self.text)
        self.text = re.sub(r"[=]{3,}", " ", self.text)
        # Compactar espacios
        self.text = re.sub(r"[ \t]{2,}", " ", self.text)

    def remove_references(self):
        """Elimina la secciÃ³n de referencias si aparece hacia el final del documento."""
        match = re.search(r"(?:\n|^)(References|Bibliography|Works Cited)\b", self.text, flags=re.IGNORECASE)
        if not match:
            return

        # Solo cortar si el encabezado estÃ¡ en el Ãºltimo 40% del texto
        cutoff_index = int(len(self.text) * 0.6)
        if match.start() >= cutoff_index:
            self.stats["removed_references"] += 1
            self.text = self.text[:match.start()].rstrip()

    def remove_references_anywhere_pdf(self):
        """Elimina referencias aunque no estÃ©n al final (solo para PDFs)."""
        match = re.search(r"(?:\n|^)(References|Bibliography|Works Cited)\b", self.text, flags=re.IGNORECASE)
        if not match:
            return
        self.stats["removed_references"] += 1
        self.text = self.text[:match.start()].rstrip()

    def remove_citations(self):
        """Elimina citas de estilo (Author, Year)"""
        patterns = [
            r"\([A-Z][a-z]+\s*(?:et\s+al\.?)?,?\s*\d{4}\)",  # (Author, 2020)
            r"\([A-Z][a-z]+\s+\d{4}\)",  # (Author 2020)
        ]
        for pattern in patterns:
            self.stats["removed_citations"] += len(re.findall(pattern, self.text))
            self.text = re.sub(pattern, "", self.text)

    def remove_figures_tables(self):
        """Elimina referencias a figuras, tablas y ecuaciones"""
        patterns = [
            r"(?:Fig(?:ure)?|Table|Eq\.?|Equation)\s*\.?\s*\d+[\s\S]*?(?:\.|$)",
            r"(?:See|shown in|as shown in)\s+(?:Fig|Figure|Table)\s*\.?\s*\d+",
            r"Figure \d+.*?\n",
            r"Table \d+.*?\n",
        ]
        for pattern in patterns:
            self.stats["removed_figures_tables"] += len(re.findall(pattern, self.text, flags=re.IGNORECASE))
            self.text = re.sub(pattern, "", self.text, flags=re.IGNORECASE)

    def remove_figure_blocks_pdf(self):
        """Elimina bloques de figuras/tablas en PDFs (mÃ¡s conservador)."""
        patterns = [
            r"(?:^|\n)(Figure|Fig\.|Table)\s*\d+.*(?:\n.+){0,3}",
            r"(?:^|\n)(Fig\.|Figure|Table)\s*\d+:\s*.*(?:\n.+){0,3}",
        ]
        for pattern in patterns:
            self.stats["removed_figures_tables"] += len(re.findall(pattern, self.text, flags=re.IGNORECASE))
            self.text = re.sub(pattern, "\n", self.text, flags=re.IGNORECASE)

    def remove_special_sections(self):
        """Elimina secciones sin valor: Abstract, Acknowledgments, Appendix, etc."""
        patterns = [
            r"(?:Abstract|Acknowledgments?|Funding|Conflicts? of Interest|Author Contributions|Data Availability)[\s\S]*?(?=\n(?:[A-Z][a-z]+|[A-Z]{2,})|$)",
            r"(?:^|\n)Appendix[\s\S]*?(?=\n(?:[A-Z][a-z]+|$)|$)",
        ]
        for pattern in patterns:
            self.stats["removed_special_sections"] += len(re.findall(pattern, self.text, flags=re.IGNORECASE | re.MULTILINE))
            self.text = re.sub(pattern, "", self.text, flags=re.IGNORECASE | re.MULTILINE)

    def remove_urls(self):
        """Elimina URLs"""
        self.stats["removed_urls"] += len(re.findall(r"https?://[^\s]+", self.text))
        self.stats["removed_urls"] += len(re.findall(r"www\.[^\s]+", self.text))
        self.text = re.sub(r"https?://[^\s]+", "", self.text)
        self.text = re.sub(r"www\.[^\s]+", "", self.text)

    def remove_equations_and_captions_pdf(self):
        """Elimina bloques tÃ­picos de ecuaciones y captions en PDFs."""
        patterns = [
            r"(?:^|\n)Equation\s*\d+.*(?:\n.+){0,3}",
            r"(?:^|\n)Eq\.?\s*\(?\d+\)?[:\s].*(?:\n.+){0,2}",
            r"(?:^|\n)Table\s*\d+[:\s].*(?:\n.+){0,3}",
            r"(?:^|\n)Figure\s*\d+[:\s].*(?:\n.+){0,3}",
            r"(?:^|\n)Fig\.?\s*\d+[:\s].*(?:\n.+){0,3}",
        ]
        for pattern in patterns:
            self.stats["removed_figures_tables"] += len(re.findall(pattern, self.text, flags=re.IGNORECASE))
            self.text = re.sub(pattern, "\n", self.text, flags=re.IGNORECASE)

    def remove_headers_footers_pdf(self):
        """Elimina encabezados/pies repetidos tÃ­picos de PDFs (ej. 'Page 1', 'Vol. 12')."""
        patterns = [
            r"(?:^|\n)Page\s+\d+\s*(?:of\s+\d+)?",
            r"(?:^|\n)\d+\s*/\s*\d+\s*$",
            r"(?:^|\n)Vol\.?\s*\d+.*",
            r"(?:^|\n)ISSN\s*\d{4}-\d{3}[\dxX]",
            r"(?:^|\n)doi:\s*\S+",
        ]
        for pattern in patterns:
            self.text = re.sub(pattern, "\n", self.text, flags=re.IGNORECASE)

    def remove_ack_appendix_copyright_pdf(self):
        """Elimina secciones de acknowledgments, appendix y lÃ­neas de copyright/licencia."""
        patterns = [
            r"(?:\n|^)(Acknowledgments?|Acknowledgement|Funding|Conflicts? of Interest)[\s\S]*?(?=\n[A-Z][A-Za-z ]{2,}\n|$)",
            r"(?:\n|^)Appendix[\s\S]*?(?=\n[A-Z][A-Za-z ]{2,}\n|$)",
            r"(?:\n|^)(Copyright|Â©)\s*[^\n]*",
            r"(?:\n|^)All rights reserved\.*",
            r"(?:\n|^)This is an open access article.*",
            r"(?:\n|^)Creative Commons.*",
        ]
        for pattern in patterns:
            self.text = re.sub(pattern, "\n", self.text, flags=re.IGNORECASE)

    def remove_pdf_boilerplate(self):
        """Elimina lÃ­neas tÃ­picas de portada/Ã­ndices en PDFs."""
        patterns = [
            r"(?:^|\n)Contents lists available at.*",
            r"(?:^|\n)journal homepage:.*",
            r"(?:^|\n)A\s+R\s+T\s+I\s+C\s+L\s+E\s+I\s+N\s+F\s+O.*",
            r"(?:^|\n)Keywords?:.*",
            r"(?:^|\n)Received\s+.*",
            r"(?:^|\n)Accepted\s+.*",
            r"(?:^|\n)Available\s+online.*",
        ]
        for pattern in patterns:
            self.text = re.sub(pattern, "\n", self.text, flags=re.IGNORECASE)

    def remove_pdf_line_noise(self):
        """Elimina lÃ­neas repetitivas de revista/afiliaciÃ³n y metadatos."""
        noisy_patterns = [
            r"^Decision Analytics Journal.*$",
            r"^Contents$",
            r"^School of .*University.*$",
            r"^A\s+R\s+T\s+I\s+C\s+L\s+E\s+I\s+N\s+F\s+O.*$",
            r"^Keywords?:.*$",
            r"^\*Corresponding author.*$",
            r"^E-?mail address:.*$",
            r"^Published by Elsevier.*$",
            r"^This is an open access article.*$",
            r"^Data availability.*$",
            r"^\d{4}-\d{4}.*$",
        ]
        lines = self.text.splitlines()
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append(line)
                continue
            if any(re.match(pat, stripped, flags=re.IGNORECASE) for pat in noisy_patterns):
                continue
            cleaned.append(line)
        self.text = "\n".join(cleaned)

    def remove_toc_lines_pdf(self):
        """Elimina lÃ­neas de tabla de contenidos con lÃ­deres de puntos y nÃºmeros de pÃ¡gina."""
        lines = self.text.splitlines()
        cleaned = []
        toc_line = re.compile(r"\.{4,}\s*\d+\s*$")
        section_line = re.compile(r"^\s*\d+(\.\d+)*\s+.*$")
        for line in lines:
            if toc_line.search(line):
                continue
            if section_line.match(line) and re.search(r"\s+\d+\s*$", line):
                continue
            cleaned.append(line)
        self.text = "\n".join(cleaned)

    def remove_extra_whitespace(self):
        """Limpia espacios en blanco excesivos"""
        self.text = re.sub(r"\n{3,}", "\n\n", self.text)  # MÃ¡ximo 2 saltos de lÃ­nea
        self.text = re.sub(r"[ \t]{2,}", " ", self.text)  # MÃºltiples espacios a uno
        self.text = re.sub(r"(?:^|\n)\s+", "\n", self.text)  # Espacios al inicio de lÃ­nea

    def extract_paragraphs(self, min_length=30, max_length=450, max_paragraphs=40):
        """
        Extrae pÃ¡rrafos coherentes filtrando lÃ­neas muy cortas.
        min_length: longitud mÃ­nima en caracteres
        max_length: longitud mÃ¡xima en caracteres (para evitar pÃ¡rrafos demasiado grandes)
        """
        paragraphs = self.text.split("\n\n")
        self.stats["paragraphs_before"] = len([p for p in paragraphs if p.strip()])
        cleaned = []

        for para in paragraphs:
            para = para.strip()
            if self.source_type == "pdf":
                # Filtrar lÃ­neas tÃ­picas de tabla de contenido
                if re.search(r"\.{4,}\s*\d+\s*$", para):
                    continue
                if re.match(r"^\s*\d+(\.\d+)*\s+.*\s+\d+\s*$", para):
                    continue
            
            # Si el pÃ¡rrafo es mÃ¡s largo que max_length, dividirlo por puntos y seguido
            if len(para) > max_length:
                # Dividir por oraciones (puntos/!/? seguidos de espacio o salto)
                sentences = re.split(r'(?<=[.!?])\s+', para)
                current_chunk = ""
                
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    
                    test_chunk = current_chunk + sentence + ". " if current_chunk else sentence + ". "
                    
                    if len(test_chunk) <= max_length:
                        current_chunk = test_chunk
                    else:
                        if len(current_chunk) > min_length and any(c.isalpha() for c in current_chunk):
                            cleaned.append(current_chunk.strip())
                        current_chunk = sentence + ". "
                
                if len(current_chunk) > min_length and any(c.isalpha() for c in current_chunk):
                    cleaned.append(current_chunk.strip())
                
                # Si aÃºn queda un bloque demasiado largo (sin puntuaciÃ³n), cortar por tamaÃ±o fijo
                if not sentences or (len(sentences) == 1 and len(sentences[0]) > max_length):
                    cleaned = []
                    for i in range(0, len(para), max_length):
                        chunk = para[i:i + max_length].strip()
                        if len(chunk) > min_length and any(c.isalpha() for c in chunk):
                            cleaned.append(chunk)
            
            elif len(para) > min_length and not para.isdigit():
                # Verificar que no sea solo nÃºmeros o caracteres especiales
                alpha_ratio = sum(c.isalpha() for c in para) / max(len(para), 1)
                digit_ratio = sum(c.isdigit() for c in para) / max(len(para), 1)
                if self.source_type == "pdf":
                    if any(c.isalpha() for c in para) and alpha_ratio > 0.1 and digit_ratio < 0.6:
                        cleaned.append(para)
                else:
                    if any(c.isalpha() for c in para) and alpha_ratio > 0.2 and digit_ratio < 0.4:
                        cleaned.append(para)

        # Si el PDF quedÃ³ con muy pocos pÃ¡rrafos, intentar con saltos simples
        if self.source_type == "pdf" and len(cleaned) < 5:
            cleaned = []
            paragraphs = self.text.split("\n")
            for para in paragraphs:
                para = para.strip()
                if len(para) > min_length and any(c.isalpha() for c in para):
                    cleaned.append(para)

        # Para PDFs muy largos, limitar cantidad de pÃ¡rrafos para acelerar NER
        if self.source_type == "pdf" and len(cleaned) > max_paragraphs:
            step = max(len(cleaned) // max_paragraphs, 1)
            cleaned = cleaned[::step][:max_paragraphs]

        self.stats["paragraphs_after"] = len(cleaned)
        return cleaned

    def clean(self):
        """Aplica todas las limpiezas en orden lÃ³gico"""
        self.stats["chars_before"] = len(self.text)
        print("Limpiando artÃ­culo...")
        # Limpieza menos agresiva para PDFs cientÃ­ficos
        if self.source_type == "pdf":
            # Limpieza mÃ¡s suave para no perder demasiado contenido
            self._normalize_pdf_text()
            self.remove_headers_footers_pdf()
            self.remove_pdf_boilerplate()
            self.remove_toc_lines_pdf()
            self.remove_pdf_line_noise()
            self.remove_references()
            self.remove_references_anywhere_pdf()
            self.remove_urls()
            self.remove_extra_whitespace()
        else:
            self.remove_references()
            self.remove_special_sections()
            self.remove_figures_tables()
            self.remove_citations()
            self.remove_urls()
        self.remove_extra_whitespace()
        self.stats["chars_after"] = len(self.text)
        print("ArtÃ­culo limpiado")
        self._print_stats()

    def _print_stats(self):
        removed_chars = self.stats["chars_before"] - self.stats["chars_after"]
        pages = self.stats["pages"]
        if pages is not None:
            print(f"[INFO] PÃ¡ginas detectadas: {pages}")
        print(f"[INFO] Caracteres antes/despuÃ©s: {self.stats['chars_before']} -> {self.stats['chars_after']} (removidos: {removed_chars})")
        print(f"[INFO] Coincidencias removidas: referencias={self.stats['removed_references']}, "
              f"citas={self.stats['removed_citations']}, figuras/tablas={self.stats['removed_figures_tables']}, "
              f"secciones={self.stats['removed_special_sections']}, urls={self.stats['removed_urls']}")
        if self.stats["paragraphs_before"]:
            print(f"[INFO] PÃ¡rrafos antes/despuÃ©s: {self.stats['paragraphs_before']} -> {self.stats['paragraphs_after']}")

    def get_paragraphs(self):
        """Retorna lista de pÃ¡rrafos procesados"""
        if self.source_type == "pdf":
            return self.extract_paragraphs(min_length=20, max_length=700, max_paragraphs=120)
        return self.extract_paragraphs()

    def save_processed(self, output_file="article_processed.txt"):
        """Guarda el texto procesado en archivo"""
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(self.text)
        print(f"ArtÃ­culo procesado guardado en: {output_file}")

    def generate_for_process_ner(self, output_file="article_for_ner.txt"):
        """
        Genera archivo listo para pasar directamente a process_ner.py
        Guarda los pÃ¡rrafos uno por lÃ­nea para fÃ¡cil lectura
        """
        paragraphs = self.get_paragraphs()
        with open(output_file, "w", encoding="utf-8") as f:
            for para in paragraphs:
                f.write(para + "\n\n")
        print(f"Archivo generado para NER: {output_file}")
        print(f"Total de pÃ¡rrafos extraÃ­dos: {len(paragraphs)}")
        return paragraphs


def main():
    parser = argparse.ArgumentParser(
        description="Preprocesa artÃ­culos acadÃ©micos en inglÃ©s (.txt o .pdf) para SciBERT NER"
    )
    parser.add_argument(
        "article",
        help="Ruta del archivo de artÃ­culo (.txt o .pdf)"
    )
    parser.add_argument(
        "--output",
        default="article_for_ner.txt",
        help="Archivo de salida (default: article_for_ner.txt)"
    )
    parser.add_argument(
        "--save-processed",
        action="store_true",
        help="Guardar tambiÃ©n el texto procesado limpio"
    )

    args = parser.parse_args()

    preprocessor = ArticlePreprocessor()

    # Cargar artÃ­culo (detecta automÃ¡ticamente si es PDF o TXT)
    if not preprocessor.load_article(args.article):
        sys.exit(1)

    # Limpiar
    preprocessor.clean()

    # Guardar versiÃ³n limpia si se pide
    if args.save_processed:
        preprocessor.save_processed("article_cleaned.txt")

    # Generar archivo para process_ner.py
    paragraphs = preprocessor.generate_for_process_ner(args.output)
    if not paragraphs:
        print("Error: no se extrajeron parrafos validos del articulo.")
        sys.exit(1)

    print("\n--- Resumen ---")
    print(f"PÃ¡rrafos extraÃ­dos: {len(paragraphs)}")


if __name__ == "__main__":
    main()

