"""
mod_sections.py — Section & Noise Removal Module
Removes: acknowledgements, references, bibliography, figure captions,
         author blocks, headers, footers, and other non-content sections.

Key feature: AUTOMATIC detection of repeated headers/footers.
  - Lines that appear 3+ times in the document are headers/footers
  - Catches journal names, author lines, page numbers regardless of format
"""

import re
from collections import Counter


# ═══════════════════════════════════════════════════════════════════════
# SECTION HEADING PATTERNS (trigger removal to next heading or EOF)
# ═══════════════════════════════════════════════════════════════════════

DISCARD_SECTIONS = re.compile(
    r'^\s*(?:\d+[\.\)]?\s*)?'  # optional numbering
    r'(?:'
    r'REFERENCES|References|BIBLIOGRAPHY|Bibliography|'
    r'ACKNOWLEDGMENTS?|Acknowledgments?|ACKNOWLEDGEMENTS?|Acknowledgements?|'
    r'FUNDING|Funding|COMPETING\s+INTERESTS?|Competing\s+interests?|'
    r'CONFLICT\s+OF\s+INTEREST|Conflict\s+of\s+interest|'
    r'DECLARATION\s+OF\s+(?:COMPETING\s+)?INTERESTS?|Declaration\s+of\s+(?:competing\s+)?interests?|'
    r'AUTHOR\s+CONTRIBUTIONS?|Author\s+contributions?|'
    r'CRediT\s+authorship\s+contribution\s+statement|'
    r'DATA\s+AVAILABILITY|Data\s+availability|'
    r'SUPPLEMENTARY\s+(?:MATERIALS?|DATA|INFORMATION)|'
    r'Supplementary\s+(?:materials?|data|information)|'
    r'ETHICS\s+STATEMENT|Ethics\s+statement|'
    r'ABBREVIATIONS?|Abbreviations?|'
    r'FUNDING\s+INFORMATION|Funding\s+information'
    r'Declaration\s+of\s+interests'
    r'Funding\s+information'
    r'Supplementary\s+materials'
    r'CRediT\s+authorship\s+contribution\s+statement'
    r')\s*$',
    re.MULTILINE
)

# Pattern to detect a new major section heading (signals end of discarded block)
NEW_SECTION = re.compile(
    r'^\s*(?:\d+[\.\)]?\s+)?[A-Z][A-Za-z\s]{3,50}$'
)

# ═══════════════════════════════════════════════════════════════════════
# INLINE NOISE PATTERNS
# ═══════════════════════════════════════════════════════════════════════

# ── Figure captions: ONLY lines that START with Fig/Figure ──
FIGURE_CAPTION = re.compile(
    r'^\s*(?:Fig(?:ure)?|FIG(?:URE)?)\s*[\.\:]?\s*\d+[\.\:\)]?\s.*$',
    re.MULTILINE | re.IGNORECASE
)

# Multi-line figure captions
FIGURE_CAPTION_BLOCK = re.compile(
    r'(?:^|\n)\s*(?:Fig(?:ure)?|FIG(?:URE)?)\s*[\.\:]?\s*\d+[\.\:\)]?\s.*?(?=\n\s*\n|\Z)',
    re.DOTALL | re.IGNORECASE
)

# ── Static header/footer patterns (known formats) ──
HEADER_FOOTER_STATIC = re.compile(
    r'^\s*(?:'
    r'(?:Page\s+)?\d+\s+of\s+\d+|'                  # "Page X of Y"
    r'(?:https?://)?doi\.org/\S+|'                    # DOI links
    r'DOI[\s\:]+\S+|'                                 # DOI: prefix
    r'\u00a9\s*\d{4}|'                                # copyright
    r'ISSN[\s\:]+[\d\-]+|'                            # ISSN
    r'Volume\s+\d+|'                                  # Volume numbers
    r'www\.\S+|'                                      # URLs
    r'Available\s+online\s+(?:at|\d)|'                # "Available online at..."
    r'Contents\s+lists\s+available|'                  # "Contents lists available..."
    r'journal\s+homepage|'                             # "journal homepage..."
    r'ScienceDirect|'                                 # ScienceDirect header
    r'Received[\s\:].*?(?:Accepted|Published).*|'     # date lines
    r'[A-Z][A-Za-z\s]+Journal\b.*$'                   # journal name lines
    r')',
    re.MULTILINE | re.IGNORECASE
)

# Email lines
EMAIL_LINE = re.compile(r'^\s*\S+@\S+\.\S+', re.MULTILINE)

# Affiliations
AFFILIATION = re.compile(
    r'^\s*\d?\s*(?:Department|School|Faculty|Institute|University|'
    r'Center|Centre|Laboratory|Hospital|College)\b.*$',
    re.MULTILINE | re.IGNORECASE
)

# Article info blocks
ARTICLE_INFO = re.compile(
    r'^\s*(?:'
    r'A\s*R\s*T\s*I\s*C\s*L\s*E|'                   # A R T I C L E
    r'I\s*N\s*F\s*O|'                                 # I N F O
    r'A\s*B\s*S\s*T\s*R\s*A\s*C\s*T|'               # A B S T R A C T
    r'Keywords?\s*:|'                                  # Keywords:
    r'Article\s+[Hh]istory|'                          # Article History
    r'Received\s+\d|'                                  # Received 15 March...
    r'Revised\s+\d|'                                   # Revised 17 July...
    r'Accepted\s+\d|'                                  # Accepted 14 August...
    r'Available\s+online\s+\d'                         # Available online 22 August...
    r')\s*',
    re.MULTILINE | re.IGNORECASE
)


# ═══════════════════════════════════════════════════════════════════════
# AUTOMATIC REPEATED LINE DETECTION
# ═══════════════════════════════════════════════════════════════════════

def _find_repeated_headers(text: str, min_occurrences: int = 3) -> set:
    """
    Automatically detect repeated headers/footers.

    Strategy:
      1. Normalize each line (strip, collapse spaces)
      2. Count occurrences
      3. Lines appearing 3+ times are headers/footers

    This catches:
      - "SLAS Technology 32 (2025) 100285"
      - "E.Grolleau,S.Couraud,E.JupinDelevauxetal."
      - "Respiratory Medicine and Research 86 (2024) 101136"
      - "Predicting the stability of mutant proteins... 13"
      - "Zheng et al."
      - Any other repeated line regardless of format
    """
    lines = text.split('\n')
    # Normalize for comparison: strip, collapse multiple spaces
    normalized = {}
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip very long lines (likely paragraphs, not headers)
        if len(stripped) > 100:
            continue
        # Skip very short lines (could be legit content like "Results")
        if len(stripped) < 5:
            continue
        # Normalize spaces for comparison
        key = re.sub(r'\s+', ' ', stripped)
        if key not in normalized:
            normalized[key] = 0
        normalized[key] += 1

    # Collect lines that appear too many times
    repeated = set()
    for key, count in normalized.items():
        if count >= min_occurrences:
            repeated.add(key)

    return repeated


def _remove_repeated_lines(text: str, repeated: set) -> str:
    """Remove lines that match any repeated header/footer pattern."""
    if not repeated:
        return text

    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        # Normalize for comparison
        key = re.sub(r'\s+', ' ', stripped)
        if key in repeated:
            continue  # skip this repeated header/footer
        result.append(line)

    return '\n'.join(result)


# ═══════════════════════════════════════════════════════════════════════
# TITLE/AUTHOR LINE AT PAGE TOPS
# ═══════════════════════════════════════════════════════════════════════

def _find_author_et_al_patterns(text: str) -> set:
    """
    Find "Author et al." patterns that appear multiple times.
    These are running headers in many journals.
    """
    # Find all "Name et al." patterns
    et_al_pattern = re.compile(r'^\s*[A-Z][\w\.\-]+(?:\s*,\s*[A-Z][\w\.\-]+)*\s+et\s+al\.?\s*$', re.MULTILINE)
    matches = et_al_pattern.findall(text)

    # Count and return those that appear 2+ times
    counts = Counter(m.strip() for m in matches)
    return {m for m, c in counts.items() if c >= 2}


# ═══════════════════════════════════════════════════════════════════════
# BARE PAGE NUMBERS
# ═══════════════════════════════════════════════════════════════════════

BARE_PAGE_NUMBER = re.compile(r'^\s*\d{1,4}\s*$', re.MULTILINE)


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════

def remove_discard_sections(text: str) -> str:
    """Remove entire sections like References, Acknowledgements, etc."""
    lines = text.split("\n")
    result = []
    discarding = False

    for line in lines:
        if DISCARD_SECTIONS.match(line):
            discarding = True
            continue
        if discarding and NEW_SECTION.match(line) and not DISCARD_SECTIONS.match(line):
            discarding = False
        if not discarding:
            result.append(line)

    return "\n".join(result)


def remove_figures(text: str) -> str:
    """
    Remove figure captions only. Preserves inline references to figures
    within paragraphs (e.g., 'as shown in Fig. 2, the results...').
    """
    text = FIGURE_CAPTION_BLOCK.sub("", text)
    text = FIGURE_CAPTION.sub("", text)
    return text


def remove_headers_footers(text: str) -> str:
    """
    Remove headers, footers, page numbers.

    Two strategies:
      1. Static patterns (known formats)
      2. Automatic detection of repeated lines (catches everything else)
    """
    # Static patterns
    text = HEADER_FOOTER_STATIC.sub("", text)
    text = ARTICLE_INFO.sub("", text)
    text = BARE_PAGE_NUMBER.sub("", text)

    # Automatic: find and remove repeated lines
    repeated = _find_repeated_headers(text, min_occurrences=3)
    if repeated:
        text = _remove_repeated_lines(text, repeated)

    # Also remove "Author et al." running headers (may appear only 2x)
    et_al_patterns = _find_author_et_al_patterns(text)
    if et_al_patterns:
        lines = text.split('\n')
        result = []
        for line in lines:
            if line.strip() in et_al_patterns:
                continue
            result.append(line)
        text = '\n'.join(result)

    return text


def remove_author_block(text: str) -> str:
    """Remove author names, affiliations, and emails from top of article."""
    lines = text.split("\n")
    clean = []
    for i, line in enumerate(lines):
        if i < 40 and (EMAIL_LINE.match(line) or AFFILIATION.match(line)):
            continue
        clean.append(line)
    return "\n".join(clean)


def remove_front_matter_info_block(text: str) -> str:
    """
    Remove keyword/info blocks that often appear between the title/authors and
    the first real paragraph in publisher-exported PDFs.
    """
    lines = text.split("\n")
    clean = []
    skipping_info = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        if i < 80 and re.fullmatch(r'I\s+N\s+F\s+O', stripped, re.IGNORECASE):
            skipping_info = True
            continue

        if skipping_info:
            # The first long prose line marks the real start of the article body.
            if len(stripped) >= 80 and re.search(r'[a-z]{3,}.*\s[a-z]{3,}', stripped, re.IGNORECASE):
                skipping_info = False
                clean.append(line)
            continue

        clean.append(line)

    return "\n".join(clean)


def final_noise_scrub(text: str) -> str:
    """
    Remove stubborn table-of-contents and publisher metadata lines that can
    survive the broader section cleaning when PDF extraction merges blocks.
    """
    cleaned_lines = []
    drop_toc_block = False
    drop_reference_block = False
    reference_rows_seen = 0

    toc_entry = re.compile(
        r'^\s*(?:\d+(?:\.\d+)*\.?\s+)?[A-Za-z][^\n]{0,180}\.{8,}\s*\d+\s*$'
    )
    dangling_section_page = re.compile(
        r'^\s*(?:Declaration of competing interest|Data availability|Funding|References)\s*\.{4,}\s*\d+\s*$',
        re.IGNORECASE,
    )
    noise_line = re.compile(
        r'^\s*(?:'
        r'Contents|'
        r'(?:\*|∗)\s*Corresponding author\b.*|'
        r'E-?mail address\s*:.*|'
        r'\d+\s+Research Scholar\b.*|'
        r'I\s+N\s+F\s+O|'
        r'\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s*$|'
        r'\d{4}[-/]\d{2,}.*Published by|'
        r'.*Published by Elsevier.*|'
        r'.*open access article.*license.*|'
        r'\(http://creativecommons\.org/licenses/[^\s]+\)\.?|'
        r'\(continued on next page ?\)|'
        r'at ScienceDirect'
        r')\s*$',
        re.IGNORECASE,
    )
    bracket_reference_row = re.compile(r'^\s*\[\d+\](?:\s+.*)?$')
    section_heading = re.compile(r'^\s*\d+(?:\.\d+)*\.?\s+[A-Z]', re.IGNORECASE)

    for line in text.split("\n"):
        stripped = line.strip()

        if not stripped:
            if not drop_toc_block and not drop_reference_block:
                cleaned_lines.append(line)
            continue

        if stripped.lower() == "contents":
            drop_toc_block = True
            continue

        if bracket_reference_row.match(stripped):
            drop_reference_block = True
            reference_rows_seen += 1
            continue

        if drop_toc_block:
            if toc_entry.match(stripped) or dangling_section_page.match(stripped) or noise_line.match(stripped):
                continue
            drop_toc_block = False

        if drop_reference_block:
            if section_heading.match(stripped):
                drop_reference_block = False
                reference_rows_seen = 0
                cleaned_lines.append(line)
                continue
            if bracket_reference_row.match(stripped):
                reference_rows_seen += 1
                continue
            if reference_rows_seen >= 2:
                continue
            drop_reference_block = False
            reference_rows_seen = 0

        if toc_entry.match(stripped):
            continue
        if dangling_section_page.match(stripped):
            continue
        if noise_line.match(stripped):
            continue

        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def clean_all_sections(text: str) -> str:
    """Apply all section-level cleaning in order."""
    text = remove_discard_sections(text)
    text = remove_figures(text)
    text = remove_headers_footers(text)
    text = remove_author_block(text)
    text = remove_front_matter_info_block(text)
    text = final_noise_scrub(text)
    return text
