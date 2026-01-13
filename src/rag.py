from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Tuple

@dataclass
class RetrievedDoc:
    title: str
    content: str
    score: float
    
def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z_]+", text.lower()))

class SimpleRunbookRAG:
    
    """
    Minimal retrival: keyword overlap over markdown sections.
    upgrade later to include advanced embedding + vectorDB, e.g. FAISS
    """
    def __init__(self, runbook_path: str):
        self.path = Path(runbook_path)
        self.sections = self._split_sections(self.path.read_text(encoding="utf-8"))

    def _split_sections(self, md: str) -> list[Tuple[str, str]]:
        # split on H2 headings: "##"
        parts = re.split(r"\n##\s+", "\n" + md)
        sections = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            lines = p.splitlines()
            title = lines[0].strip()
            content = "\n".join(lines[1:]).strip()
            sections.append((title, content))
            
        return sections
    
    def retrieve(self, query: str, k: int = 2) -> list[RetrievedDoc]:
        q = _tokenize(query)
        scored = []
        for title, content in self.sections:
            doc_tokens = _tokenize(title + "\n" + content)
            overlap = len(q & doc_tokens)
            score = overlap / max(1, len(q))
            scored.append(RetrievedDoc(title=title, content=content, score=score))
        scored.sort(key=lambda d: d.score, reverse=True)
        return scored[:k]