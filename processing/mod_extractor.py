"""
mod_extractor.py — PDF Text Extraction Module
Handles: multi-library fallback, single/dual column detection, page-level extraction.
Libraries: pdfplumber (layout detection + fallback), pdfminer.six (primary), pypdf (fallback 2)

Smart engine selection:
  - Extracts a sample with both pdfplumber and pdfminer
  - Detects "glued words" (common in Elsevier, some Springer PDFs)
  - Auto-selects the engine that produces cleaner text
"""

import re
from pathlib import Path

# ── Library imports with availability flags ──────────────────────────
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    HAS_PDFMINER = True
except ImportError:
    HAS_PDFMINER = False

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


# ═══════════════════════════════════════════════════════════════════════
# QUALITY DETECTION
# ═══════════════════════════════════════════════════════════════════════

def _glued_word_ratio(text: str) -> float:
    """
    Detect ratio of likely-glued words in extracted text.
    Glued words happen when PDF encoding lacks proper space info.
    Examples: "managementasithasbeen", "TheNLPalgorithmwastrained"
    Returns: ratio from 0.0 (clean) to 1.0 (all glued)
    """
    words = text.split()
    if not words:
        return 0.0

    glued = 0
    for w in words:
        if len(w) > 20:
            # Multiple lowercase->uppercase transitions (not acronyms)
            transitions = len(re.findall(r'[a-z][A-Z]', w))
            # Punctuation inside word: "word,anotherword" or "word.Another"
            internal_punct = len(re.findall(r'[a-z],[a-z]|[a-z]\.[A-Z]', w))
            if transitions > 1 or internal_punct > 0:
                glued += 1
    return glued / max(len(words), 1)


def _select_best_engine(pdf_path: str) -> str:
    """
    Compare extraction quality between available engines on a sample page.
    Returns the name of the best engine: 'pdfminer', 'pdfplumber', or 'pypdf'.
    """
    sample_texts = {}

    # Get a content page (skip first page which is often title/abstract)
    sample_page = 1  # second page (0-indexed)

    if HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if len(pdf.pages) > sample_page:
                    page = pdf.pages[sample_page]
                else:
                    page = pdf.pages[0]
                sample_texts["pdfplumber"] = page.extract_text() or ""
        except Exception:
            pass

    if HAS_PDFMINER:
        try:
            page_num = sample_page if sample_page >= 0 else 0
            text = pdfminer_extract(pdf_path, page_numbers=[page_num])
            sample_texts["pdfminer"] = text or ""
        except Exception:
            pass

    if not sample_texts:
        return "pypdf"  # last resort

    # Compare quality
    best_engine = "pdfminer"  # default preference
    best_score = -1

    for engine, text in sample_texts.items():
        glued_ratio = _glued_word_ratio(text)
        word_count = len(text.split())
        # Score: more words is better, fewer glued is better
        score = word_count * (1 - glued_ratio * 10)
        if score > best_score:
            best_score = score
            best_engine = engine

    return best_engine


# ═══════════════════════════════════════════════════════════════════════
# COLUMN DETECTION (always uses pdfplumber)
# ═══════════════════════════════════════════════════════════════════════

def _detect_columns_on_page(page) -> bool:
    """Analyze word x-positions to detect dual-column layout (pdfplumber page)."""
    words = page.extract_words(keep_blank_chars=False)
    if len(words) < 30:
        return False

    page_width = page.width
    mid = page_width / 2
    margin = page_width * 0.08

    left_words = [w for w in words if w["x1"] < mid - margin]
    right_words = [w for w in words if w["x0"] > mid + margin]

    if not left_words or not right_words:
        return False

    left_ratio = len(left_words) / len(words)
    right_ratio = len(right_words) / len(words)
    return left_ratio > 0.25 and right_ratio > 0.25


def detect_layout(pdf_path: str) -> str:
    """Detect if PDF is 'dual' or 'single' column (samples first 4 pages)."""
    if not HAS_PDFPLUMBER:
        return "single"

    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_to_check = pdf.pages[0:min(4, len(pdf.pages))]
            dual_count = sum(1 for p in pages_to_check if _detect_columns_on_page(p))
            return "dual" if dual_count >= len(pages_to_check) * 0.5 else "single"
    except Exception:
        return "single"


# ═══════════════════════════════════════════════════════════════════════
# EXTRACTION ENGINES
# ═══════════════════════════════════════════════════════════════════════

# ── pdfplumber (with column-aware extraction) ──

LINE_TOLERANCE = 6
GAP_THRESHOLD = 15


def _words_to_lines(word_list):
    """Convert pdfplumber words into text lines, preserving table gaps."""
    if not word_list:
        return ""

    lines = []
    current_line = [word_list[0]]

    for w in word_list[1:]:
        if abs(w["top"] - current_line[-1]["top"]) < LINE_TOLERANCE:
            current_line.append(w)
        else:
            lines.append(_build_line_text(current_line))
            current_line = [w]
    lines.append(_build_line_text(current_line))

    return "\n".join(lines)


def _build_line_text(words_in_line):
    """Join words preserving large gaps as multiple spaces (for table detection)."""
    if not words_in_line:
        return ""

    words_in_line.sort(key=lambda w: w["x0"])
    parts = [words_in_line[0]["text"]]

    for i in range(1, len(words_in_line)):
        prev = words_in_line[i - 1]
        curr = words_in_line[i]
        gap = curr["x0"] - prev["x1"]

        if gap > GAP_THRESHOLD:
            num_spaces = max(2, int(gap / 4))
            parts.append(" " * num_spaces)
        else:
            parts.append(" ")
        parts.append(curr["text"])

    return "".join(parts)


def _extract_dual_column_page(page) -> str:
    """Extract text from a dual-column page respecting reading order."""
    words = page.extract_words(keep_blank_chars=False)
    if not words:
        return ""

    mid = page.width / 2

    left_words = []
    right_words = []

    for w in words:
        if w["x1"] <= mid:
            left_words.append(w)
        elif w["x0"] >= mid:
            right_words.append(w)
        else:
            left_overlap = mid - w["x0"]
            right_overlap = w["x1"] - mid
            if left_overlap >= right_overlap:
                left_words.append(w)
            else:
                right_words.append(w)

    left_words.sort(key=lambda w: (w["top"], w["x0"]))
    right_words.sort(key=lambda w: (w["top"], w["x0"]))

    parts = []
    left_text = _words_to_lines(left_words)
    right_text = _words_to_lines(right_words)

    if left_text.strip():
        parts.append(left_text)
    if right_text.strip():
        parts.append(right_text)

    return "\n\n".join(parts)


def _extract_with_pdfplumber(pdf_path: str, layout: str) -> str:
    """Extract using pdfplumber with column awareness."""
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            if layout == "dual" and _detect_columns_on_page(page):
                pages_text.append(_extract_dual_column_page(page))
            else:
                words = page.extract_words(keep_blank_chars=False)
                if words:
                    words.sort(key=lambda w: (w["top"], w["x0"]))
                    pages_text.append(_words_to_lines(words))
                else:
                    pages_text.append(page.extract_text() or "")
    return "\n\n".join(pages_text)


# ── pdfminer ──

def _extract_with_pdfminer(pdf_path: str) -> str:
    """Extract using pdfminer.six -- handles most PDF encodings correctly."""
    return pdfminer_extract(pdf_path)


# ── pypdf ──

def _extract_with_pypdf(pdf_path: str) -> str:
    """Fallback: pypdf (basic extraction)."""
    reader = PdfReader(pdf_path)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


# ═══════════════════════════════════════════════════════════════════════
# POST-PROCESSING
# ═══════════════════════════════════════════════════════════════════════

def _post_process(text: str) -> str:
    """
    Light post-processing to fix common extraction artifacts.
    - Fix pdfminer (cid:XX) artifacts
    - Normalize whitespace
    """
    # Replace (cid:XX) with common substitutions
    text = re.sub(r'\(cid:\d+\)', '', text)

    # Fix broken hyphens at line endings: "signifi-\ncantly" -> "significantly"
    text = re.sub(r'-\s*\n\s*', '-', text)

    # Normalize multiple spaces (but preserve 2+ spaces for table detection)
    # Only collapse 6+ spaces to 5 (keep table structure)
    text = re.sub(r' {6,}', '     ', text)

    return text


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════

def extract_text(pdf_path: str) -> dict:
    """
    Extract text from PDF with smart engine selection.

    Strategy:
      1. Detect layout (single/dual column) using pdfplumber
      2. Compare extraction quality between engines on a sample page
      3. Use the engine that produces cleaner text
      4. Apply post-processing

    Returns: {"text": str, "layout": str, "engine": str, "success": bool}
    """
    layout = detect_layout(pdf_path)

    # Smart engine selection
    best_engine = _select_best_engine(pdf_path)

    # Build engine list with best first
    engines = []

    if best_engine == "pdfminer" and HAS_PDFMINER:
        engines.append(("pdfminer", lambda: _extract_with_pdfminer(pdf_path)))
        if HAS_PDFPLUMBER:
            engines.append(("pdfplumber", lambda: _extract_with_pdfplumber(pdf_path, layout)))
    elif best_engine == "pdfplumber" and HAS_PDFPLUMBER:
        engines.append(("pdfplumber", lambda: _extract_with_pdfplumber(pdf_path, layout)))
        if HAS_PDFMINER:
            engines.append(("pdfminer", lambda: _extract_with_pdfminer(pdf_path)))
    else:
        if HAS_PDFMINER:
            engines.append(("pdfminer", lambda: _extract_with_pdfminer(pdf_path)))
        if HAS_PDFPLUMBER:
            engines.append(("pdfplumber", lambda: _extract_with_pdfplumber(pdf_path, layout)))

    if HAS_PYPDF:
        engines.append(("pypdf", lambda: _extract_with_pypdf(pdf_path)))

    for name, fn in engines:
        try:
            text = fn()
            if text and len(text.strip()) > 100:
                text = _post_process(text)
                return {"text": text, "layout": layout, "engine": name, "success": True}
        except Exception as e:
            print(f"  ⚠ {name} failed: {e}")

    return {"text": "", "layout": layout, "engine": "none", "success": False}