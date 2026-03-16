"""
mod_tables.py — Table Detection & Marking Module
Detects tables in extracted text and wraps them with tokens:
  <<TABLE_START>> ... <<TABLE_END>>
The second cleaning script will strip everything between these markers.

Detection strategy:
  1. Primary: Caption-anchored (Table X) + line-length analysis
     - Paragraphs have consistent line lengths (50-80 chars)
     - Tables have short, irregular lines (mostly < 45 chars)
  2. Secondary: Orphan blocks of short lines with numeric content
"""

import re
from typing import List


# ═══════════════════════════════════════════════════════════════════════
# TABLE CAPTION PATTERN
# ═══════════════════════════════════════════════════════════════════════

TABLE_LABEL = re.compile(
    r'^\s*(?:TABLE|Table|Tabla)\s+[IVXLC\d]+[\.\:\)]?(?:\s.*)?$',
    re.MULTILINE
)

# ═══════════════════════════════════════════════════════════════════════
# LINE-LENGTH BASED TABLE DETECTION
# ═══════════════════════════════════════════════════════════════════════

# Threshold: lines shorter than this are "short" (table-like)
SHORT_LINE_THRESHOLD = 45

# If this percentage of non-blank lines in a window are short -> table
SHORT_LINE_RATIO = 0.60

# Minimum non-blank lines needed to evaluate a block
MIN_BLOCK_LINES = 2


def _is_paragraph_line(line: str) -> bool:
    """
    Check if a line looks like it belongs to a paragraph.
    Paragraph lines are typically 55+ chars.
    """
    stripped = line.strip()
    if not stripped:
        return False
    return len(stripped) > 55


def _is_section_heading(line: str) -> bool:
    """Detect numbered section headings like '4.3. Follow-up' or '5. Discussion'."""
    stripped = line.strip()
    if not stripped:
        return False
    # Numbered: "4.3. Follow-up", "5. Discussion", "2.1 Methods"
    # Must have a letter after the number pattern to distinguish from "97.8 % (44/45)"
    if re.match(r'^\d+\.\d*[\.\s]+[A-Za-z]', stripped):
        return True
    # Single number: "5. Discussion" (but NOT "5.47" or "5.00")
    if re.match(r'^\d+\.\s+[A-Za-z]', stripped):
        return True
    return False


def _is_end_signal(line: str) -> bool:
    """
    Strong signals that a table region has ended.
    These override line-length analysis.
    """
    stripped = line.strip()
    if not stripped:
        return False
    # Numbered section heading
    if _is_section_heading(stripped):
        return True
    return False


def _block_is_tabular(lines: List[str]) -> bool:
    """
    Analyze a block of lines to determine if they look tabular.
    Uses the key insight: table lines are mostly short (< 45 chars),
    while paragraph lines are consistently long (50-80 chars).
    """
    non_blank = [l for l in lines if l.strip()]
    if len(non_blank) < MIN_BLOCK_LINES:
        return False

    lengths = [len(l.strip()) for l in non_blank]
    short_count = sum(1 for l in lengths if l < SHORT_LINE_THRESHOLD)
    short_ratio = short_count / len(non_blank)

    return short_ratio >= SHORT_LINE_RATIO


# ═══════════════════════════════════════════════════════════════════════
# CONTENT-BASED TABLE LINE DETECTION (for orphan tables)
# ═══════════════════════════════════════════════════════════════════════

# Statistical values: "97.8 % (44/45)"
STAT_VALUE = re.compile(r'^\s*\d+[\.\,]?\d*\s*%?\s*(?:\([\d\s/]+\))?\s*$')

# CI range: "94 % - 100 %"
CI_RANGE = re.compile(r'^\s*\d+[\.\,]?\d*\s*%?\s*[-\u2013\u2014]\s*\d+[\.\,]?\d*\s*%\s*$')

# Bare numbers: "160", "63.76", "808.00"
BARE_NUMBER = re.compile(r'^\s*\d+[\.\,]?\d*\s*$')

# Row with multiple columns separated by spaces
MULTI_COLUMN_ROW = re.compile(
    r'^[\s]*[\w\.\-\+\u00b1\%\(\)]+(?:\s{2,}[\w\.\-\+\u00b1\%\(\)]+){2,}\s*$'
)

# Table separator
TABLE_SEPARATOR = re.compile(r'^[\s]*[-\u2500\u2550_]{5,}[\s]*$')


def _is_table_content_line(line: str) -> bool:
    """Check if a line has table-like content (numbers, stats, separators)."""
    stripped = line.strip()
    if not stripped:
        return False
    if TABLE_SEPARATOR.match(stripped):
        return True
    if STAT_VALUE.match(stripped):
        return True
    if CI_RANGE.match(stripped):
        return True
    if BARE_NUMBER.match(stripped):
        return True
    if MULTI_COLUMN_ROW.match(stripped):
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════

def mark_tables(text: str) -> str:
    """
    Scan text for table regions and wrap them with <<TABLE_START>> / <<TABLE_END>>.

    Strategy:
      Pass 1 -- Caption-anchored tables:
        Find "Table X" captions, then scan downward.
        Use LINE-LENGTH ANALYSIS to determine where the table ends:
        - Table regions have mostly short lines (< 45 chars)
        - End when we hit a section heading OR a block of long paragraph lines
        - Include the caption + description in the marked region

      Pass 1.5 -- Expand regions forward through short-line blocks

      Pass 2 -- Orphan tabular blocks:
        Find blocks of 3+ consecutive short lines with numeric/tabular content
        that weren't caught by Pass 1.
    """
    lines = text.split("\n")
    marked = [False] * len(lines)

    # ── Pass 1: Caption-anchored tables ──
    for i, line in enumerate(lines):
        if TABLE_LABEL.match(line):
            start = i
            j = i + 1
            blank_streak = 0
            recent_long_lines = 0

            while j < len(lines):
                stripped = lines[j].strip()

                # Track blank lines
                if not stripped:
                    blank_streak += 1
                    if blank_streak > 4:
                        break
                    j += 1
                    continue

                blank_streak = 0

                # ── Hard stop: section heading ──
                if _is_end_signal(lines[j]):
                    break

                # ── Hard stop: another Table caption ──
                if TABLE_LABEL.match(lines[j]) and j > start + 1:
                    break

                # ── Paragraph detection using line length ──
                # Key: only start checking for paragraph re-entry AFTER
                # we've moved past the caption description area.
                # The first ~4 lines after "Table X" can be long (caption text).
                # After that, if we see 2+ consecutive long lines, it's a paragraph.
                lines_from_caption = j - start
                if _is_paragraph_line(lines[j]) and lines_from_caption > 4:
                    recent_long_lines += 1
                    if recent_long_lines >= 2:
                        # Backtrack: don't include these paragraph lines
                        j -= recent_long_lines
                        break
                else:
                    recent_long_lines = 0

                j += 1

            # Mark the region if substantial
            if j - start >= 2:
                for k in range(start, j):
                    marked[k] = True

    # ── Pass 1.5: Expand caption-anchored regions ──
    # After Pass 1, the marked region might stop at the end of labels
    # but the numeric values follow after blank lines. Expand forward
    # while lines remain short (table-like).
    i = 0
    while i < len(lines):
        # Find the end of a marked region
        if marked[i]:
            # Skip to end of marked region
            while i < len(lines) and marked[i]:
                i += 1
            # Now i is the first unmarked line after a marked region
            # Try to expand forward through short lines
            j = i
            blank_streak = 0
            while j < len(lines):
                stripped = lines[j].strip()
                if not stripped:
                    blank_streak += 1
                    if blank_streak > 4:
                        break
                    j += 1
                    continue
                blank_streak = 0
                # Stop at section headings
                if _is_end_signal(lines[j]):
                    break
                # Stop at next table caption
                if TABLE_LABEL.match(lines[j]):
                    break
                # Stop when we see paragraph text (2+ long lines)
                if _is_paragraph_line(lines[j]):
                    # Check if the next non-blank line is also long
                    next_non_blank = None
                    for k in range(j + 1, min(j + 3, len(lines))):
                        if lines[k].strip():
                            next_non_blank = lines[k]
                            break
                    if next_non_blank and _is_paragraph_line(next_non_blank):
                        break
                    # Single long line might be a table note -- allow it
                j += 1
            # Mark the expanded region
            if j > i:
                for k in range(i, j):
                    marked[k] = True
            i = j
        else:
            i += 1

    # ── Pass 2: Orphan tabular blocks ──
    # Find blocks of short lines with numeric content, not near any caption
    i = 0
    while i < len(lines):
        if not marked[i] and _is_table_content_line(lines[i]):
            # Found a potential table content line -- expand the block
            block_start = i
            j = i
            while j < len(lines) and (
                _is_table_content_line(lines[j]) or
                not lines[j].strip() or  # blank lines within block
                (lines[j].strip() and len(lines[j].strip()) < SHORT_LINE_THRESHOLD)
            ):
                # Stop if we hit a section heading
                if _is_end_signal(lines[j]):
                    break
                # Stop if we hit a paragraph line
                if _is_paragraph_line(lines[j]):
                    break
                j += 1

            # Count actual content lines
            content_lines = [
                lines[k] for k in range(block_start, j)
                if _is_table_content_line(lines[k])
            ]

            # Only mark if we have 3+ content lines (avoid false positives)
            if len(content_lines) >= 3:
                # Verify the block is actually tabular using line-length analysis
                block = [lines[k] for k in range(block_start, j)]
                if _block_is_tabular(block):
                    for k in range(block_start, j):
                        marked[k] = True

            i = j if j > i else i + 1
        else:
            i += 1

    # ── Build output with markers ──
    result = []
    in_table = False
    for i, line in enumerate(lines):
        if marked[i] and not in_table:
            result.append("<<TABLE_START>>")
            in_table = True
        elif not marked[i] and in_table:
            result.append("<<TABLE_END>>")
            in_table = False
        result.append(line)

    if in_table:
        result.append("<<TABLE_END>>")

    return "\n".join(result)