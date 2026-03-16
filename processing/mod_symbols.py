"""
mod_symbols.py — Symbol & Encoding Cleaning Module
Optimized for BERT training on scientific/biomedical text.

Removes:
  - URLs, DOIs, emails, links
  - Encoding artifacts, mojibake, control characters
  - Mathematical equations and notation
  - Decorative bullets and viñetas
  - Private-use Unicode characters
  - Zero-width and BOM characters

Preserves (important for BERT context):
  - Standard punctuation: () , . ; : % = < >
  - Hyphens in compound words: BERT-based, non-small
  - Citation markers [1] — signal evidence-backed claims
  - Basic math in context: p < 0.05, ± SD, 95%CI
"""

import re


# ═══════════════════════════════════════════════════════════════════════
# ENCODING & CONTROL CHARACTERS
# ═══════════════════════════════════════════════════════════════════════

# Control characters (non-printable)
CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Zero-width and invisible characters
INVISIBLE_CHARS = re.compile(
    r'[\ufeff'          # BOM
    r'\u200b'           # zero-width space
    r'\u200c'           # zero-width non-joiner
    r'\u200d'           # zero-width joiner
    r'\u200e'           # left-to-right mark
    r'\u200f'           # right-to-left mark
    r'\u00ad'           # soft hyphen
    r'\u2060'           # word joiner
    r'\ufffe'           # non-character
    r'\uffff]'          # non-character
)

# Private use area characters (bullets, symbols from PDFs)
PRIVATE_USE = re.compile(r'[\ue000-\uf8ff]')

# Common UTF-8 mojibake (garbled encoding)
MOJIBAKE = re.compile(
    r'â€™|â€œ|â€\x9d|â€"|â€"'     # smart quotes/dashes
    r'|Ã©|Ã¨|Ã´|Ã®|Ã§|Ã¼|Ã¶|Ã¤'  # accented chars
    r'|Â§|Â©|Â®|Â±|Â´|Â»|Â«'       # symbols
    r'|Ã\x83|Ã\x82'                  # double encoding
)

# pdfminer (cid:XX) artifacts
CID_ARTIFACT = re.compile(r'\(cid:\d+\)')


# ═══════════════════════════════════════════════════════════════════════
# LIGATURES
# ═══════════════════════════════════════════════════════════════════════

LIGATURES = {
    'ﬁ': 'fi',
    'ﬂ': 'fl',
    'ﬀ': 'ff',
    'ﬃ': 'ffi',
    'ﬄ': 'ffl',
    'ﬅ': 'st',
    'ﬆ': 'st',
}


# ═══════════════════════════════════════════════════════════════════════
# URLS, EMAILS, DOIs, LINKS
# ═══════════════════════════════════════════════════════════════════════

URLS = re.compile(
    r'https?://\S+'
    r'|ftp://\S+'
    r'|www\.\S+'
    r'|doi\.org/\S+'
    r'|DOI[\s:]+10\.\S+'
    r'|arxiv\.org/\S+'
    r'|github\.com/\S+',
    re.IGNORECASE
)

EMAILS = re.compile(
    r'\S+@\S+\.\S+'
)

# DOI patterns that might appear standalone
DOI_STANDALONE = re.compile(
    r'10\.\d{4,}/\S+',
    re.IGNORECASE
)


# ═══════════════════════════════════════════════════════════════════════
# MATHEMATICAL NOTATION & EQUATIONS
# ═══════════════════════════════════════════════════════════════════════

# Full equation lines (lines that are mostly math symbols)
EQUATION_LINE = re.compile(
    r'^\s*(?:'
    r'[A-Za-z]\s*[=<>≤≥≈∼]\s*[\d\w\+\-\*/\(\)\{\}\[\]\^_\\∑∏∫√∞∂∇].*'  # x = ...
    r'|\\(?:frac|sqrt|sum|prod|int|lim|log|sin|cos|tan)\b.*'              # LaTeX commands
    r'|[\∑∏∫√∞∂∇∈∉⊂⊃∪∩∧∨¬∀∃≡≠≤≥≈∼←→↔⇒⇔].*[\∑∏∫√∞∂∇∈∉⊂⊃∪∩∧∨¬∀∃≡≠≤≥≈∼←→↔⇒⇔]'
    r')\s*$',
    re.MULTILINE
)

# Inline math: heavy symbol sequences (3+ math symbols together)
HEAVY_MATH = re.compile(
    r'[\∑∏∫√∞∂∇∈∉⊂⊃∪∩∧∨¬∀∃≡≠≈∼←→↔⇒⇔]{2,}'
)

# LaTeX-style commands that survived PDF extraction
LATEX_COMMANDS = re.compile(
    r'\\(?:frac|sqrt|sum|prod|int|lim|log|sin|cos|tan|alpha|beta|gamma|'
    r'delta|epsilon|theta|lambda|mu|sigma|omega|pi|phi|chi|psi|rho|tau|'
    r'mathbb|mathbf|mathrm|mathit|mathcal|text|left|right|begin|end)\b'
)

# Superscript/subscript notation that's garbled
GARBLED_MATH = re.compile(
    r'[²³⁴⁵⁶⁷⁸⁹⁰₀₁₂₃₄₅₆₇₈₉]+'
)

# Fraction-like symbols
FRACTION_SYMBOLS = re.compile(
    r'[½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞]'
)

# Combined math expression: "√̅ ∑ ̅̅̅̅̅̅̅̅̅̅̅ n i=1 ∑ A2..."
COMPLEX_MATH_EXPR = re.compile(
    r'[\u0300-\u036f\u0305\u0332]'  # combining diacritical marks (overlines, underlines)
)


# ═══════════════════════════════════════════════════════════════════════
# DECORATIVE BULLETS & VIÑETAS
# ═══════════════════════════════════════════════════════════════════════

DECORATIVE_BULLETS = re.compile(
    r'[➢►▶▷●○◉◎■□◆◇▪▫▸▹◦★☆✓✗✦✧·»«†‡§¶‣⁃∙⦿⦾⊕⊖⊗⊘]'
)

# Arrow symbols
ARROWS = re.compile(
    r'[←→↑↓↔↕⇐⇒⇑⇓⇔⇕➜➝➞➡⬅⬆⬇⬈⬉⬊⬋]'
)


# ═══════════════════════════════════════════════════════════════════════
# MISCELLANEOUS NOISE
# ═══════════════════════════════════════════════════════════════════════

# Lines that are only symbols/noise (no actual words)
NOISE_LINE = re.compile(r'^\s*[^\w\s]{1,5}\s*$', re.MULTILINE)

# Excessive whitespace
MULTI_BLANK = re.compile(r'\n{3,}')

# Hyphenated line breaks: "signifi-\ncantly" → "significantly"
# Only rejoin if second part starts with lowercase (preserves "BERT-based")
HYPHEN_BREAK = re.compile(r'(\w)-\n\s*([a-z])')

# Repeated punctuation: ... is ok, but .... or --- or === is noise
REPEATED_PUNCT = re.compile(r'([=\-_\*\#\~])\1{3,}')

# Copyright and trademark symbols (noise in body text)
LEGAL_SYMBOLS = re.compile(r'[©®™]')


# ═══════════════════════════════════════════════════════════════════════
# UNICODE NORMALIZATION
# ═══════════════════════════════════════════════════════════════════════

def _normalize_unicode(text: str) -> str:
    """Normalize unicode to consistent forms for BERT."""
    replacements = {
        # Smart quotes → straight
        '\u2018': "'", '\u2019': "'",
        '\u201c': '"', '\u201d': '"',
        # Spaces
        '\u00a0': ' ',                  # non-breaking space
        '\u2002': ' ', '\u2003': ' ',   # en-space, em-space
        '\u2009': ' ',                  # thin space
        # Ellipsis
        '\u2026': '...',
        # Section sign → plus-minus (common pdfminer artifact)
        '\u00a7': '+/-',
        # Plus-minus
        '\u00b1': '+/-',
        # Multiplication
        '\u00d7': 'x',
        # Minus sign → hyphen
        '\u2212': '-',
        # En-dash, em-dash → hyphen (in non-range contexts)
        '\u2013': '-', '\u2014': '-',
        # Greek letters commonly used in stats (keep readable)
        '\u03b1': 'alpha', '\u03b2': 'beta',
        '\u03c7': 'chi', '\u03c3': 'sigma',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _fix_ligatures(text: str) -> str:
    """Replace PDF ligature characters with their expanded forms."""
    for lig, expanded in LIGATURES.items():
        text = text.replace(lig, expanded)
    return text


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════

def clean_symbols(text: str) -> str:
    """
    Full cleaning pipeline for BERT training on scientific text.

    Order matters:
      1. Fix encoding (ligatures, mojibake, unicode)
      2. Remove links, emails, DOIs
      3. Remove math notation and equations
      4. Remove decorative symbols
      5. Rejoin hyphenated words
      6. Clean noise lines
      7. Normalize whitespace
    """
    # ── Step 1: Encoding fixes ──
    text = _normalize_unicode(text)
    text = _fix_ligatures(text)
    text = CONTROL_CHARS.sub('', text)
    text = INVISIBLE_CHARS.sub('', text)
    text = PRIVATE_USE.sub('', text)
    text = MOJIBAKE.sub('', text)
    text = CID_ARTIFACT.sub('', text)
    text = COMPLEX_MATH_EXPR.sub('', text)

    # ── Step 2: Remove links, emails, DOIs ──
    text = URLS.sub('', text)
    text = EMAILS.sub('', text)
    text = DOI_STANDALONE.sub('', text)

    # ── Step 3: Remove math notation ──
    text = EQUATION_LINE.sub('', text)
    text = LATEX_COMMANDS.sub('', text)
    text = HEAVY_MATH.sub('', text)
    text = GARBLED_MATH.sub('', text)
    text = FRACTION_SYMBOLS.sub('', text)

    # ── Step 4: Remove decorative symbols ──
    text = DECORATIVE_BULLETS.sub('', text)
    text = ARROWS.sub('', text)
    text = LEGAL_SYMBOLS.sub('', text)
    text = REPEATED_PUNCT.sub('', text)

    # ── Step 5: Rejoin hyphenated line breaks ──
    text = HYPHEN_BREAK.sub(r'\1\2', text)

    # ── Step 6: Clean noise lines ──
    text = NOISE_LINE.sub('', text)
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Keep blank lines (paragraph separators)
        if not stripped:
            cleaned_lines.append('')
            continue
        # Remove lines with only 1-2 non-alphanumeric characters
        if len(stripped) <= 2 and not any(c.isalnum() for c in stripped):
            continue
        cleaned_lines.append(line)

    text = '\n'.join(cleaned_lines)

    # ── Step 7: Normalize whitespace ──
    text = MULTI_BLANK.sub('\n\n', text)

    return text