"""
mod_chunker.py — BERT-Compatible Text Chunker
Splits cleaned text into chunks of ~506 tokens with overlap.
Uses word-based approximation (1 word ≈ 1.3 BERT tokens).
If transformers is available, uses BertTokenizer for precision.
"""

import re
from typing import List

# ── Try loading BERT tokenizer, fallback to word approximation ──
try:
    from transformers import BertTokenizerFast
    _tokenizer = BertTokenizerFast.from_pretrained("bert-base-uncased")
    USE_BERT = True
except Exception:
    _tokenizer = None
    USE_BERT = False

# Constants
TARGET_TOKENS = 506
OVERLAP_TOKENS = 50
BERT_RATIO = 1.3  # average: 1 word ≈ 1.3 BERT subword tokens


def _count_tokens(text: str) -> int:
    """Count tokens using BERT tokenizer or word approximation."""
    if USE_BERT:
        return len(_tokenizer.encode(text, add_special_tokens=False))
    return int(len(text.split()) * BERT_RATIO)


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences (preserves paragraph breaks as boundaries)."""
    # Split on sentence-ending punctuation followed by space/newline
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_text(text: str, target: int = TARGET_TOKENS, overlap: int = OVERLAP_TOKENS) -> List[str]:
    """
    Split text into chunks of approximately `target` tokens.
    Chunks break at sentence boundaries with `overlap` token overlap.
    """
    sentences = _split_into_sentences(text)
    if not sentences:
        return []

    chunks = []
    current_sentences = []
    current_count = 0

    for sent in sentences:
        sent_tokens = _count_tokens(sent)

        # If single sentence exceeds target, add as its own chunk
        if sent_tokens > target:
            if current_sentences:
                chunks.append(" ".join(current_sentences))
                current_sentences = []
                current_count = 0
            chunks.append(sent)
            continue

        if current_count + sent_tokens > target and current_sentences:
            chunks.append(" ".join(current_sentences))

            # Build overlap from end of current chunk
            overlap_sents = []
            overlap_count = 0
            for s in reversed(current_sentences):
                s_tok = _count_tokens(s)
                if overlap_count + s_tok > overlap:
                    break
                overlap_sents.insert(0, s)
                overlap_count += s_tok

            current_sentences = overlap_sents
            current_count = overlap_count

        current_sentences.append(sent)
        current_count += sent_tokens

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return chunks