#!/usr/bin/env python3
"""
Summarization utility for TTS optimization.
Converts verbose responses into concise speaking versions.
Gospel: 60-75% credit reduction, <2% failure rate, listenable while driving.
"""

import re
from typing import Dict, Tuple

def strip_markdown(text: str) -> str:
    """Remove markdown formatting (headers, bullets, code blocks, emojis)."""
    # Remove markdown headers
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    # Remove markdown bullets
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove inline code
    text = re.sub(r'`[^`]*`', '', text)
    # Remove emojis
    text = re.sub(r'[\U0001F300-\U0001F9FF]', '', text)
    # Remove bold/italic
    text = re.sub(r'\*\*|__|_|\*', '', text)
    # Remove links
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Clean up excess whitespace
    text = re.sub(r'\n\n+', '\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def extract_sentences(text: str) -> list:
    """Split text into sentences, handling abbreviations."""
    # Simple sentence split (handles sentence-ending punctuation)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def score_sentence_importance(sentence: str, position: int, total: int) -> float:
    """
    Score importance of a sentence for TTS summarization.
    Gospel: First sentence usually most important, avoid filler.
    """
    score = 0.0
    
    # Position bonus: first sentence(s) are usually key
    if position == 0:
        score += 2.0  # First sentence, important
    elif position == 1:
        score += 1.5  # Second sentence
    elif position <= total // 3:
        score += 1.0  # Early third of response
    
    # Action words bonus (verbs that convey meaning)
    action_words = ['is', 'are', 'run', 'deploy', 'build', 'create', 'add', 'fix', 'use', 'enable', 'configure']
    if any(word in sentence.lower() for word in action_words):
        score += 0.5
    
    # Penalty for filler sentences
    filler_patterns = [
        r'^(note|however|also|additionally|for example)',
        r'(please|kindly|thank you)',
        r'(hope|think|believe) ',
        r'^(that|this|it) ',
    ]
    if any(re.match(pattern, sentence.lower()) for pattern in filler_patterns):
        score -= 0.5
    
    # Penalty for very short sentences (usually not informative)
    if len(sentence.split()) < 3:
        score -= 0.3
    
    # Bonus for containing numbers/specifics (concrete info)
    if re.search(r'\d+', sentence):
        score += 0.3
    
    return max(0, score)  # Never negative

def summarize_for_tts(text: str, max_sentences: int = 3) -> Tuple[str, Dict]:
    """
    Convert verbose response to TTS-friendly summary.
    Returns: (summary_text, metadata)
    """
    # Parse response type if present
    response_type = "generic"
    if "[TYPE:" in text:
        match = re.search(r'\[TYPE:\s*(\w+)\]', text)
        if match:
            response_type = match.group(1)
        text = re.sub(r'\[TYPE:\s*\w+\]', '', text)
    
    # Strip markdown
    cleaned = strip_markdown(text)
    
    # Extract sentences
    sentences = extract_sentences(cleaned)
    
    # If already short, return as-is
    if len(sentences) <= max_sentences:
        summary = ' '.join(sentences)
        return summary, {
            'type': response_type,
            'original_chars': len(text),
            'summary_chars': len(summary),
            'reduction_percent': 0,
            'sentences_kept': len(sentences),
            'failure': False
        }
    
    # Score sentences
    scored = [
        (score_sentence_importance(s, i, len(sentences)), i, s)
        for i, s in enumerate(sentences)
    ]
    
    # Sort by score, keep top N, then re-order by position
    top_sentences = sorted(scored, key=lambda x: -x[0])[:max_sentences]
    top_sentences = sorted(top_sentences, key=lambda x: x[1])  # Re-order by original position
    
    summary = ' '.join([s[2] for s in top_sentences])
    
    # Calculate metrics
    original_chars = len(text)
    summary_chars = len(summary)
    reduction = round(100 * (1 - summary_chars / original_chars)) if original_chars > 0 else 0
    
    return summary, {
        'type': response_type,
        'original_chars': original_chars,
        'summary_chars': summary_chars,
        'reduction_percent': reduction,
        'sentences_kept': len(top_sentences),
        'failure': False
    }

def estimate_tts_credits(text: str, provider: str = "elevenlabs") -> int:
    """
    Estimate ElevenLabs credits for TTS.
    ElevenLabs: ~$0.075 per 1000 characters = ~0.075 credits per char
    """
    chars = len(text)
    if provider == "elevenlabs":
        return max(1, round(chars * 0.075 / 1000 * 100))  # Convert to API cost units
    return 1

# Test
if __name__ == "__main__":
    test_response = """
## Timeline Analysis
- The timeline is achievable in 2-3 weeks
- Cloudflare + ElevenLabs setup adds 1-2 hours
- Risk-first execution saves 2-3 weeks of potential rework

### Why This Matters
This approach is pragmatic and based on proven patterns. You'll have working infrastructure without waiting weeks for edge cases.

Note: However, extensive testing will be required.
"""
    
    summary, meta = summarize_for_tts(test_response)
    print(f"Original ({meta['original_chars']} chars):\n{test_response}\n")
    print(f"Summary ({meta['summary_chars']} chars, {meta['reduction_percent']}% reduction):\n{summary}\n")
    print(f"Metadata: {meta}")
    print(f"Credits estimate: {estimate_tts_credits(summary)}")
