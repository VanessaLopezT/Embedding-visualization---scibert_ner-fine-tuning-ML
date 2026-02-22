"""
prepare_article.py
Archivo auxiliar para procesar artículos académicos en inglés.
- Lee artículos en texto plano (.txt) o PDF (.pdf)
- Extrae texto de PDFs automáticamente
- Limpia referencias, citas, figuras, tablas y contenido sin valor
- Extrae párrafos coherentes

RUTAS PORTABLES: Usa rutas relativas para funcionar en cualquier PC
"""

import re
import argparse
import sys
from pathlib import Path


class ArticlePreprocessor:
    """Preprocesa artículos académicos para uso con SciBERT NER."""

    def __init__(self):
        self.text = ""
        self.source_type = None
        self.pdf_title_hint = None
        self.first_page_text_raw = None
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
        """Carga un artículo desde archivo .txt o .pdf"""
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
            print(f"Artículo TXT cargado: {file_path}")
            return True
        except FileNotFoundError:
            print(f"Error: No se encontró el archivo {file_path}")
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
                meta = getattr(reader, "metadata", None)
                if meta:
                    try:
                        self.pdf_title_hint = (meta.get("/Title") or "").strip() or None
                    except Exception:
                        self.pdf_title_hint = None
                text_parts = []
                
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text:
                        if page_num == 0:
                            self.first_page_text_raw = text
                        # Limpiar espacios pegados
                        text = self._fix_pdf_spacing(text)
                        text_parts.append(text)
                
                self.text = "\n\n".join(text_parts)
                self.stats["pages"] = len(reader.pages)
                print(f"Artículo PDF cargado con {reader_name}: {file_path} ({len(reader.pages)} páginas)")
                return True
                
            except ImportError:
                # Si no está pypdf/PyPDF2, usar pdfplumber
                print("pypdf/PyPDF2 no disponible, usando pdfplumber...")
                import pdfplumber
                
                with pdfplumber.open(file_path) as pdf:
                    try:
                        meta = getattr(pdf, "metadata", None) or {}
                        self.pdf_title_hint = (meta.get("Title") or meta.get("title") or "").strip() or None
                    except Exception:
                        self.pdf_title_hint = None
                    text_parts = []
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            if self.first_page_text_raw is None:
                                self.first_page_text_raw = page_text
                            page_text = self._fix_pdf_spacing(page_text)
                            text_parts.append(page_text)
                    
                    self.text = "\n\n".join(text_parts)
                    self.stats["pages"] = len(pdf.pages)
                
                print(f"Artículo PDF cargado con pdfplumber: {file_path} ({len(pdf.pages)} páginas)")
                return True
            
        except ImportError as e:
            print("Error: No hay librerías PDF disponibles")
            print("Instala con: pip install pypdf pdfplumber")
            return False
        except Exception as e:
            print(f"Error al cargar PDF: {e}")
            return False

    def _fix_pdf_spacing(self, text):
        """Arregla espaciado pobre de PDFs"""
        import re
        # Corregir mojibake frecuente de PDFs
        replacements = {
            "Â©": "©",
            "Ã—": "x",
            "Ã¾": " ",
            "â€œ": "\"",
            "â€": "\"",
            "â€™": "'",
            "â€˜": "'",
            "â€“": "-",
            "â€”": "-",
            "â€¦": "...",
            "Â±": "+/-",
            "Â¼": "1/4",
            "Â½": "1/2",
            "Â¾": "3/4",
            "Â·": " ",
            "Â": "",
        }
        for src, dst in replacements.items():
            text = text.replace(src, dst)
        # Normalizar caracteres raros/ligaduras comunes en PDFs
        text = text.replace("\u00ad", "")  # soft hyphen
        text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
        text = text.replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
        text = text.replace("\u2022", " ").replace("\u00b7", " ")
        text = text.replace("\u00a0", " ")  # non-breaking space
        # Unir palabras cortadas por guion al final de línea
        text = re.sub(r'-\n(\w)', r'\1', text)
        
        # 1. Reemplazar saltos de línea sin espacios
        text = re.sub(r'([a-záéíóúñ])\n([a-záéíóúñ])', r'\1 \2', text, flags=re.IGNORECASE)
        
        # 2. Agregar espacio después de puntos si no tienen
        text = re.sub(r'\.([A-Z])', r'. \1', text)
        
        # 3. Arreglar CamelCase (MachinelearningModel -> Machine learning Model)
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        
        # 4. Arreglar palabras pegadas con números (word1word2 -> word1 word2)
        text = re.sub(r'([a-z])([A-Z][a-z]+)', r'\1 \2', text)
        
        # 5. Limpiar espacios múltiples
        text = re.sub(r' +', ' ', text)
        
        # 6. Limpiar tabs
        text = re.sub(r'\t+', ' ', text)
        
        # 7. Limpiar múltiples saltos de línea
        text = re.sub(r'\n\n+', '\n\n', text)
        
        return text.strip()

    def _normalize_pdf_text(self):
        """Normaliza texto de PDF para reducir tokens inflados."""
        self.text = self.text.replace("Â", "")
        # Remover caracteres de control invisibles
        self.text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", self.text)
        # Colapsar repeticiones largas de símbolos
        self.text = re.sub(r"[_\-]{4,}", " ", self.text)
        self.text = re.sub(r"[=]{3,}", " ", self.text)
        # Compactar espacios
        self.text = re.sub(r"[ \t]{2,}", " ", self.text)

    def extract_pdf_title(self):
        """Extrae un título probable desde las primeras líneas del PDF."""
        lines = [ln.strip() for ln in self.text.splitlines() if ln.strip()]
        if not lines:
            return None

        ignored_starts = (
            "article info", "keywords", "abstract", "contents",
            "received", "accepted", "available online"
        )

        def is_boilerplate(line):
            low = line.lower()
            if any(low.startswith(p) for p in ignored_starts):
                return True
            blocked = (
                "journal homepage", "contents lists available", "sciencedirect",
                "doi", "www.", "http://", "https://", "article history",
                "department of", "school of", "university", "laboratory", "issn",
                "lab invest"
            )
            return any(tok in low for tok in blocked)

        def looks_like_title_line(line):
            low = line.lower()
            if is_boilerplate(line):
                return False
            if " abstract " in f" {low} " or low.startswith("abstract "):
                return False
            if re.search(r"\bA\W*B\W*S\W*T\W*R\W*A\W*C\W*T\b", line, flags=re.IGNORECASE):
                return False
            if " keyword" in low:
                return False
            if "fig." in low or "fig.." in low:
                return False
            if len(line) < 20:
                return False
            if len(line) > 220:
                return False
            if line.endswith(":"):
                return False
            if "," in line and line.count(",") >= 2:
                # Suele ser lista de autores/afiliaciones.
                return False
            if sum(c.isalpha() for c in line) < 12:
                return False
            if len(line.split()) < 4:
                return False
            return True

        def looks_like_author_line(line):
            low = line.lower()
            if is_boilerplate(line):
                return False
            if any(tok in low for tok in ("department of", "school of", "university", "institute", "laboratory")):
                return False
            # Nombres propios + separadores típicos de autoría.
            name_chunks = len(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z]\.)?", line))
            has_author_marks = ("," in line) or ("*" in line) or ("∗" in line) or (" et al" in low)
            return name_chunks >= 2 and has_author_marks

        def is_affiliation_line(line):
            low = line.lower()
            keys = (
                "department of", "school of", "university", "institute", "laboratory",
                "hospital", "faculty of", "college of"
            )
            return any(k in low for k in keys)

        # Heurística principal: título seguido por autores (en la línea siguiente
        # o la subsiguiente si el título viene partido en dos líneas).
        candidate = None
        head = lines[:140]

        # Caso común Elsevier/ScienceDirect: cabecera de revista y luego título + autores.
        header_idx = None
        for i, line in enumerate(head):
            low = line.lower()
            if "journal homepage" in low or "contents lists available" in low or "sciencedirect" in low:
                header_idx = i
                break
        if header_idx is not None:
            for i in range(header_idx + 1, min(len(head), header_idx + 25)):
                line = head[i]
                if not looks_like_title_line(line):
                    continue
                if i + 1 < len(head) and looks_like_author_line(head[i + 1]):
                    candidate = line
                    break
                if i + 2 < len(head):
                    maybe_cont = head[i + 1]
                    if looks_like_title_line(maybe_cont) and looks_like_author_line(head[i + 2]):
                        candidate = f"{line} {maybe_cont}"
                        break

        # Regla general: tomar el bloque justo antes de autores.
        if not candidate:
            author_idx = None
            for i, line in enumerate(head[:90]):
                if looks_like_author_line(line):
                    author_idx = i
                    break
            if author_idx is not None and author_idx > 0:
                block = []
                j = author_idx - 1
                while j >= 0 and len(block) < 4:
                    cur = head[j].strip()
                    low = cur.lower()
                    if not cur:
                        break
                    if is_boilerplate(cur):
                        break
                    if looks_like_author_line(cur):
                        break
                    if is_affiliation_line(cur):
                        break
                    if "keyword" in low or "abstract" in low:
                        break
                    block.append(cur)
                    j -= 1
                block.reverse()
                if block:
                    if re.match(r"^(review|original|research)\s+article$", block[0], flags=re.IGNORECASE):
                        block = block[1:]
                if block:
                    candidate = " ".join(block)

        for i, line in enumerate(head):
            if candidate:
                break
            if not looks_like_title_line(line):
                continue

            if i + 1 < len(head) and looks_like_author_line(head[i + 1]):
                candidate = line
                break

            if i + 2 < len(head):
                maybe_cont = head[i + 1]
                if looks_like_title_line(maybe_cont) and looks_like_author_line(head[i + 2]):
                    candidate = f"{line} {maybe_cont}"
                    break

        # Fallback conservador.
        if not candidate:
            for line in lines[:25]:
                if looks_like_title_line(line) and len(line.split()) <= 25:
                    candidate = line
                    break

        if not candidate:
            return None

        # Quitar prefijos de tipo de artículo.
        candidate = re.sub(r"^(Review Article|Original Article|Research Article)\s*", "", candidate, flags=re.IGNORECASE)
        # Si quedó pegado al bloque de abstract, cortar antes.
        candidate = re.sub(r"\bA\s*B\s*S\s*T\s*R\s*A\s*C\s*T\b[\s\S]*$", "", candidate, flags=re.IGNORECASE).strip()
        candidate = re.sub(r"\bAbstract\b[\s\S]*$", "", candidate, flags=re.IGNORECASE).strip()
        # Quitar cola típica de autor al final del título (ej. "David Y..").
        candidate = re.sub(r"\s+[A-Z][a-z]+\s+[A-Z]\.\.?$", "", candidate).strip()
        # Limpieza básica final.
        candidate = re.sub(r"\s{2,}", " ", candidate).strip(" -:\t")

        return candidate if len(candidate) >= 12 else None

    def extract_title_from_first_page_header(self):
        """Extrae título usando la cabecera típica de la primera página (ScienceDirect/Elsevier)."""
        if not self.first_page_text_raw:
            return None

        lines = [ln.strip() for ln in self.first_page_text_raw.splitlines() if ln.strip()]
        if not lines:
            return None

        def is_header_line(line):
            low = line.lower()
            return (
                "contents lists available" in low
                or "sciencedirect" in low
                or "journal homepage" in low
                or low.endswith("journal")
            )

        def looks_like_author(line):
            low = line.lower()
            if any(tok in low for tok in ("department of", "school of", "university", "institute", "laboratory")):
                return False
            name_chunks = len(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z]\.)?", line))
            has_marks = ("," in line) or ("*" in line) or ("∗" in line)
            return name_chunks >= 2 and has_marks

        anchor = None
        for i, line in enumerate(lines[:35]):
            if is_header_line(line):
                anchor = i
        if anchor is None:
            return None

        author_idx = None
        for j in range(anchor + 1, min(len(lines), anchor + 30)):
            if looks_like_author(lines[j]):
                author_idx = j
                break
        if author_idx is None or author_idx <= anchor + 1:
            return None

        title_lines = []
        for k in range(anchor + 1, author_idx):
            ln = lines[k]
            low = ln.lower()
            if "journal homepage" in low or "contents lists available" in low or "sciencedirect" in low:
                continue
            if "abstract" in low:
                continue
            if "keyword" in low:
                continue
            if len(ln) < 8:
                continue
            title_lines.append(ln)

        if not title_lines:
            return None

        title = " ".join(title_lines[:3]).strip()
        title = self.normalize_title_text(title)
        return title

    def normalize_title_text(self, title):
        if not title:
            return None
        cleaned = str(title).strip()
        cleaned = re.sub(r"^(Review Article|Original Article|Research Article)\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\bA\W*B\W*S\W*T\W*R\W*A\W*C\W*T\b[\s\S]*$", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\bAbstract\b[\s\S]*$", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^Fig\.{0,2}\s*\d+\.{0,2}\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -:\t")
        return cleaned or None

    def is_bad_title(self, title):
        if not title:
            return True
        low = title.lower()
        bad_tokens = (
            "abstract", "keywords", "article info", "article history", "journal homepage",
            "contents lists available", "sciencedirect", "doi", "www."
        )
        if any(tok in low for tok in bad_tokens):
            return True
        if re.search(r"\bA\W*B\W*S\W*T\W*R\W*A\W*C\W*T\b", title, flags=re.IGNORECASE):
            return True
        if "fig." in low or "fig.." in low:
            return True
        if len(title) > 220:
            return True
        return False

    def strip_pdf_front_matter_keep_title(self, title):
        """Elimina autores/afiliaciones al inicio y conserva el título."""
        if not self.text:
            return

        intro_match = re.search(r"(?:^|\n)\s*Introduction\b", self.text, flags=re.IGNORECASE)
        if intro_match and intro_match.start() < int(len(self.text) * 0.55):
            body = self.text[intro_match.start():].lstrip()
        else:
            # Fallback: recortar hasta abstract si no hay "Introduction" temprano.
            abs_match = re.search(r"(?:^|\n)\s*Abstract\b", self.text, flags=re.IGNORECASE)
            body = self.text[abs_match.start():].lstrip() if abs_match else self.text

        if title:
            self.text = f"TITLE: {title}\n\n{body}"
        else:
            self.text = body

    def remove_inline_pdf_noise(self):
        """Elimina fragmentos editoriales incrustados dentro de líneas narrativas."""
        patterns = [
            r"ARTICLE INFO.*$",
            r"Article history:.*$",
            r"©\s*\d{4}.*?All rights are reserved.*?(?=(Introduction|$))",
            r"\*+\s*Corresponding authors?\..*$",
            r"E-?mail addresses?:.*$",
            r"David\s+Y\..*?Zhang\s+et\s+al\..*?/+\s*Lab\s+Invest\s*\d+\s*\(\d{4}\)\s*\d+\s*\d+\s*\d+",
            r"\bTo\s+David\s+Y\..*?Zhang\s+et\s+al\..*?/+\s*Lab\s+Invest\s*\d+\s*\(\d{4}\)\s*\d+\s*\d+\s*\d+",
        ]
        for pattern in patterns:
            self.text = re.sub(pattern, " ", self.text, flags=re.IGNORECASE | re.MULTILINE)

    def remove_references(self):
        """Elimina la sección de referencias si aparece hacia el final del documento."""
        match = re.search(r"(?:\n|^)(References|Bibliography|Works Cited)\b", self.text, flags=re.IGNORECASE)
        if not match:
            return

        # Solo cortar si el encabezado está en el último 40% del texto
        cutoff_index = int(len(self.text) * 0.6)
        if match.start() >= cutoff_index:
            self.stats["removed_references"] += 1
            self.text = self.text[:match.start()].rstrip()

    def remove_references_anywhere_pdf(self):
        """Elimina referencias aunque no estén al final (solo para PDFs)."""
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
        """Elimina bloques de figuras/tablas en PDFs (más conservador)."""
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
        """Elimina bloques típicos de ecuaciones y captions en PDFs."""
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
        """Elimina encabezados/pies repetidos típicos de PDFs (ej. 'Page 1', 'Vol. 12')."""
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
        """Elimina secciones de acknowledgments, appendix y líneas de copyright/licencia."""
        patterns = [
            r"(?:\n|^)(Acknowledgments?|Acknowledgement|Funding|Conflicts? of Interest)[\s\S]*?(?=\n[A-Z][A-Za-z ]{2,}\n|$)",
            r"(?:\n|^)Appendix[\s\S]*?(?=\n[A-Z][A-Za-z ]{2,}\n|$)",
            r"(?:\n|^)(Copyright|©)\s*[^\n]*",
            r"(?:\n|^)All rights reserved\.*",
            r"(?:\n|^)This is an open access article.*",
            r"(?:\n|^)Creative Commons.*",
        ]
        for pattern in patterns:
            self.text = re.sub(pattern, "\n", self.text, flags=re.IGNORECASE)

    def remove_pdf_boilerplate(self):
        """Elimina líneas típicas de portada/índices en PDFs."""
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
        """Elimina líneas repetitivas de revista/afiliación y metadatos."""
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
            r"^.*@.*$",
            r"^\d{4}-\d{4}.*$",
            r"^ARTICLE INFO.*$",
            r"^Article history:.*$",
            r"^Revised\s+\d+.*$",
            r"^Accepted\s+\d+.*$",
            r"^Available online.*$",
            r"^Lab Invest\s+\d+.*$",
            r"^David Y\.\. Zhang et al\..*$",
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

    def remove_repeated_footer_lines_pdf(self):
        """Elimina líneas cortas repetidas muchas veces (headers/footers de página)."""
        lines = self.text.splitlines()
        counts = {}
        for line in lines:
            key = line.strip()
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1

        repeated = set()
        for line, count in counts.items():
            if count >= 3 and len(line) <= 120:
                # Evitar eliminar texto normal frecuente; solo líneas con rasgos de header/footer.
                if re.search(r"(lab invest|et al\.|^\d+$|^\d+\s+\d+\s+\d+|^page\s+\d+)", line, flags=re.IGNORECASE):
                    repeated.add(line)

        cleaned = []
        for line in lines:
            if line.strip() in repeated:
                continue
            cleaned.append(line)
        self.text = "\n".join(cleaned)

    def remove_table_blocks_pdf(self):
        """Elimina bloques de tablas cuando empiezan por 'Table N'."""
        lines = self.text.splitlines()
        cleaned = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            table_match = re.search(r"\bTable\s+\d+\b", line, flags=re.IGNORECASE)
            if table_match:
                prefix = line[:table_match.start()].strip()
                if len(prefix) >= 50 and prefix.count(" ") >= 8:
                    cleaned.append(prefix)
                # Saltar bloque de tabla hasta volver a narrativa clara.
                i += 1
                blank_run = 0
                while i < len(lines):
                    current = lines[i].strip()
                    if not current:
                        blank_run += 1
                    else:
                        blank_run = 0

                    if blank_run >= 1:
                        break
                    if re.match(r"^(Introduction|Methods?|Results?|Discussion|Conclusion|References)\b", current, flags=re.IGNORECASE):
                        break
                    words = re.findall(r"[A-Za-z]{2,}", current)
                    alpha = sum(c.isalpha() for c in current)
                    symbols = sum(1 for c in current if c in "/\\|%_=+[]()<>:;,*")
                    symbol_ratio = symbols / max(len(current), 1)
                    if len(words) >= 14 and current.endswith(".") and alpha > 60 and symbol_ratio < 0.07:
                        break
                    i += 1
                continue
            cleaned.append(lines[i])
            i += 1
        self.text = "\n".join(cleaned)

    def remove_dense_table_lines_pdf(self):
        """Elimina líneas de aspecto tabular/ruidoso sin narrativa."""
        lines = self.text.splitlines()
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append(line)
                continue

            alpha = sum(c.isalpha() for c in stripped)
            digit = sum(c.isdigit() for c in stripped)
            symbols = sum(1 for c in stripped if c in "/\\|%_=+[]()<>:;,*")
            upper = sum(1 for c in stripped if c.isupper())
            length = max(len(stripped), 1)

            digit_ratio = digit / length
            symbol_ratio = symbols / length
            upper_ratio = (upper / alpha) if alpha else 0.0
            has_table_markers = (
                "/C2" in stripped
                or "FDA approval" in stripped
                or "Scanner system" in stripped
                or "Summary of " in stripped
            )
            looks_table_row = (
                length > 60
                and digit_ratio > 0.15
                and symbol_ratio > 0.08
                and upper_ratio > 0.45
            )

            if has_table_markers or looks_table_row:
                continue

            cleaned.append(line)
        self.text = "\n".join(cleaned)

    def remove_garbled_lines_pdf(self):
        """Elimina lineas con texto corrupto tipico de OCR/encoding en PDFs."""
        lines = self.text.splitlines()
        cleaned = []
        weird_chars = set("ÂÃÅÆÍ¿€‰")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append(line)
                continue

            letters = [c for c in stripped if c.isalpha()]
            letter_count = len(letters)
            lower_count = sum(1 for c in letters if c.islower())
            vowel_count = sum(1 for c in letters if c.lower() in "aeiou")
            weird_count = sum(1 for c in stripped if c in weird_chars)
            non_ascii_count = sum(1 for c in stripped if ord(c) > 127)

            lower_ratio = (lower_count / letter_count) if letter_count else 1.0
            vowel_ratio = (vowel_count / letter_count) if letter_count else 1.0
            non_ascii_ratio = (non_ascii_count / len(stripped)) if stripped else 0.0
            weird_ratio = (weird_count / len(stripped)) if stripped else 0.0
            noisy_tokens = re.findall(r"\b[A-Z0-9]{6,}\b", stripped)

            # Caso 1: bloques largos casi todo en "mayusculas cifradas"
            looks_ciphered = letter_count >= 25 and lower_ratio < 0.18 and vowel_ratio < 0.22
            # Caso 2: mojibake fuerte (Â¿, Ã€, Å... etc.)
            looks_mojibake = (weird_ratio > 0.08 and len(stripped) >= 20) or (non_ascii_ratio > 0.25 and len(stripped) >= 20)
            # Caso 3: lineas con varios tokens "codificados" (ej. 7L]KRR... QXPEHU...)
            looks_encoded_tokens = len(noisy_tokens) >= 2 and len(stripped) >= 20 and lower_ratio < 0.45

            if looks_ciphered or looks_mojibake or looks_encoded_tokens:
                continue

            cleaned.append(line)

        self.text = "\n".join(cleaned)

    def remove_toc_lines_pdf(self):
        """Elimina líneas de tabla de contenidos con líderes de puntos y números de página."""
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
        self.text = re.sub(r"\n{3,}", "\n\n", self.text)  # Máximo 2 saltos de línea
        self.text = re.sub(r"[ \t]{2,}", " ", self.text)  # Múltiples espacios a uno
        self.text = re.sub(r"(?:^|\n)\s+", "\n", self.text)  # Espacios al inicio de línea

    def extract_paragraphs(self, min_length=30, max_length=450, max_paragraphs=40):
        """
        Extrae párrafos coherentes filtrando líneas muy cortas.
        min_length: longitud mínima en caracteres
        max_length: longitud máxima en caracteres (para evitar párrafos demasiado grandes)
        """
        paragraphs = self.text.split("\n\n")
        self.stats["paragraphs_before"] = len([p for p in paragraphs if p.strip()])
        cleaned = []

        for para in paragraphs:
            para = para.strip()
            if self.source_type == "pdf":
                # Filtrar líneas típicas de tabla de contenido
                if re.search(r"\.{4,}\s*\d+\s*$", para):
                    continue
                if re.match(r"^\s*\d+(\.\d+)*\s+.*\s+\d+\s*$", para):
                    continue
            
            # Si el párrafo es más largo que max_length, dividirlo por puntos y seguido
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
                
                # Si aún queda un bloque demasiado largo (sin puntuación), cortar por tamaño fijo
                if not sentences or (len(sentences) == 1 and len(sentences[0]) > max_length):
                    cleaned = []
                    for i in range(0, len(para), max_length):
                        chunk = para[i:i + max_length].strip()
                        if len(chunk) > min_length and any(c.isalpha() for c in chunk):
                            cleaned.append(chunk)
            
            elif len(para) > min_length and not para.isdigit():
                # Verificar que no sea solo números o caracteres especiales
                alpha_ratio = sum(c.isalpha() for c in para) / max(len(para), 1)
                digit_ratio = sum(c.isdigit() for c in para) / max(len(para), 1)
                if self.source_type == "pdf":
                    if any(c.isalpha() for c in para) and alpha_ratio > 0.1 and digit_ratio < 0.6:
                        cleaned.append(para)
                else:
                    if any(c.isalpha() for c in para) and alpha_ratio > 0.2 and digit_ratio < 0.4:
                        cleaned.append(para)

        # Si el PDF quedó con muy pocos párrafos, intentar con saltos simples
        if self.source_type == "pdf" and len(cleaned) < 5:
            cleaned = []
            paragraphs = self.text.split("\n")
            for para in paragraphs:
                para = para.strip()
                if len(para) > min_length and any(c.isalpha() for c in para):
                    cleaned.append(para)

        # Para PDFs muy largos, limitar cantidad de párrafos para acelerar NER
        if self.source_type == "pdf" and len(cleaned) > max_paragraphs:
            step = max(len(cleaned) // max_paragraphs, 1)
            cleaned = cleaned[::step][:max_paragraphs]

        self.stats["paragraphs_after"] = len(cleaned)
        return cleaned

    def clean(self):
        """Aplica todas las limpiezas en orden lógico"""
        self.stats["chars_before"] = len(self.text)
        print("Limpiando artículo...")
        # Limpieza menos agresiva para PDFs científicos
        if self.source_type == "pdf":
            # Limpieza más suave para no perder demasiado contenido
            title = self.extract_title_from_first_page_header()
            if self.is_bad_title(title):
                title = self.normalize_title_text(self.pdf_title_hint)
            if self.is_bad_title(title):
                title = self.normalize_title_text(self.extract_pdf_title())
            self._normalize_pdf_text()
            self.remove_inline_pdf_noise()
            self.remove_headers_footers_pdf()
            self.remove_pdf_boilerplate()
            self.remove_toc_lines_pdf()
            self.remove_pdf_line_noise()
            if self.is_bad_title(title):
                title = self.normalize_title_text(self.extract_pdf_title())
            self.remove_repeated_footer_lines_pdf()
            self.remove_table_blocks_pdf()
            self.remove_dense_table_lines_pdf()
            self.remove_garbled_lines_pdf()
            self.strip_pdf_front_matter_keep_title(title)
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
        print("Artículo limpiado")
        self._print_stats()

    def _print_stats(self):
        removed_chars = self.stats["chars_before"] - self.stats["chars_after"]
        pages = self.stats["pages"]
        if pages is not None:
            print(f"[INFO] Páginas detectadas: {pages}")
        print(f"[INFO] Caracteres antes/después: {self.stats['chars_before']} -> {self.stats['chars_after']} (removidos: {removed_chars})")
        print(f"[INFO] Coincidencias removidas: referencias={self.stats['removed_references']}, "
              f"citas={self.stats['removed_citations']}, figuras/tablas={self.stats['removed_figures_tables']}, "
              f"secciones={self.stats['removed_special_sections']}, urls={self.stats['removed_urls']}")
        if self.stats["paragraphs_before"]:
            print(f"[INFO] Párrafos antes/después: {self.stats['paragraphs_before']} -> {self.stats['paragraphs_after']}")

    def get_paragraphs(self):
        """Retorna lista de párrafos procesados"""
        if self.source_type == "pdf":
            return self.extract_paragraphs(min_length=20, max_length=700, max_paragraphs=120)
        return self.extract_paragraphs()

    def save_processed(self, output_file="article_processed.txt"):
        """Guarda el texto procesado en archivo"""
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(self.text)
        print(f"Artículo procesado guardado en: {output_file}")

    def generate_for_process_ner(self, output_file="article_for_ner.txt"):
        """
        Genera archivo listo para pasar directamente a process_ner.py
        Guarda los párrafos uno por línea para fácil lectura
        """
        paragraphs = self.get_paragraphs()
        with open(output_file, "w", encoding="utf-8") as f:
            for para in paragraphs:
                f.write(para + "\n\n")
        print(f"Archivo generado para NER: {output_file}")
        print(f"Total de párrafos extraídos: {len(paragraphs)}")
        return paragraphs


def main():
    parser = argparse.ArgumentParser(
        description="Preprocesa artículos académicos en inglés (.txt o .pdf) para SciBERT NER"
    )
    parser.add_argument(
        "article",
        help="Ruta del archivo de artículo (.txt o .pdf)"
    )
    parser.add_argument(
        "--output",
        default="article_for_ner.txt",
        help="Archivo de salida (default: article_for_ner.txt)"
    )
    parser.add_argument(
        "--save-processed",
        action="store_true",
        help="Guardar también el texto procesado limpio"
    )

    args = parser.parse_args()

    preprocessor = ArticlePreprocessor()

    # Cargar artículo (detecta automáticamente si es PDF o TXT)
    if not preprocessor.load_article(args.article):
        sys.exit(1)

    # Limpiar
    preprocessor.clean()

    # Guardar versión limpia si se pide
    if args.save_processed:
        preprocessor.save_processed("article_cleaned.txt")

    # Generar archivo para process_ner.py
    paragraphs = preprocessor.generate_for_process_ner(args.output)
    if not paragraphs:
        print("Error: no se extrajeron parrafos validos del articulo.")
        sys.exit(1)

    print("\n--- Resumen ---")
    print(f"Párrafos extraídos: {len(paragraphs)}")


if __name__ == "__main__":
    main()

