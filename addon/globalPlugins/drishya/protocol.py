"""Bounded requests and human-readable local model responses."""
import base64
import re

DETAILS = ("concise", "detailed")


def smol_request(png, detail):
    if detail not in DETAILS:
        raise ValueError("Choose concise or detailed descriptions.")
    if not png or len(png) > 16 * 1024 * 1024:
        raise ValueError("Image is empty or too large.")
    length = "2 to 4 sentences" if detail == "concise" else "one short paragraph of 5 to 7 sentences"
    prompt = ("Describe the visible image for a blind person in " + length + ". "
              "Mention the main subject, important details, colours and spatial layout. "
              "For a screenshot, describe the interface and readable text. "
              "Only describe what is visible. Do not guess unreadable text or hidden details.")
    return {
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}},
        ]}],
        "max_tokens": 140 if detail == "concise" else 220,
        "temperature": 0.0,
        "stream": False,
    }


def parse_smol(payload, detail=None):
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ValueError("The local model returned an invalid response. Try again.") from None
    if not isinstance(text, str) or not text.strip():
        raise ValueError("The local model returned an empty description. Try again.")
    text = text.strip()
    if detail is None:
        return text
    if detail not in DETAILS:
        raise ValueError("Invalid description style.")
    max_sentences, max_words = (4, 90) if detail == "concise" else (7, 160)
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    selected = []
    words = 0
    for sentence in sentences[:max_sentences]:
        if selected and (words + len(sentence.split()) > max_words or not sentence.rstrip('\"\u201d').endswith((".", "!", "?"))):
            break
        if len(sentence.split()) > max_words:
            selected.append(" ".join(sentence.split()[:max_words]) + "…")
            break
        selected.append(sentence)
        words += len(sentence.split())
    return " ".join(selected)
