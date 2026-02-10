from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from typing import List, Tuple

@dataclass
class RetrievedDoc:
    title: str
    content: str
    score: float

def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z_]+", text.lower()))

def _split_sections(md: str) -> list[Tuple[str, str]]:
    """Split markdown on H2 headings (##)."""
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


class SimpleRunbookRAG:
    """Keyword-overlap retrieval over markdown runbook sections."""
    def __init__(self, runbook_path: str):
        self.path = Path(runbook_path)
        self.sections = _split_sections(self.path.read_text(encoding="utf-8"))

    def retrieve(self, query: str, k: int = 2) -> List[RetrievedDoc]:
        q = _tokenize(query)
        scored = []
        for title, content in self.sections:
            doc_tokens = _tokenize(title + "\n" + content)
            overlap = len(q & doc_tokens)
            score = overlap / max(1, len(q))
            scored.append(RetrievedDoc(title=title, content=content, score=score))
        scored.sort(key=lambda d: d.score, reverse=True)
        return scored[:k]


def _embedding_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


class EmbeddingRunbookRAG(SimpleRunbookRAG):
    """
    Semantic retrieval using sentence embeddings when sentence-transformers is installed.
    Falls back to keyword overlap otherwise.
    """
    def __init__(self, runbook_path: str, use_embeddings: bool = True):
        super().__init__(runbook_path)
        self._embeddings: List[List[float]] | None = None
        self._model = None
        if use_embeddings and _embedding_available():
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("all-MiniLM-L6-v2")
                texts = [f"{t}\n{c}" for t, c in self.sections]
                self._embeddings = self._model.encode(texts, convert_to_numpy=True).tolist()
            except Exception:
                self._embeddings = None
                self._model = None

    def retrieve(self, query: str, k: int = 2) -> List[RetrievedDoc]:
        if self._embeddings is not None and self._model is not None:
            q_vec = self._model.encode([query], convert_to_numpy=True)[0].tolist()
            scores = []
            for i, emb in enumerate(self._embeddings):
                # cosine similarity (embeddings are typically L2-normalized by the model)
                dot = sum(a * b for a, b in zip(q_vec, emb))
                norm_q = (sum(x * x for x in q_vec)) ** 0.5
                norm_d = (sum(x * x for x in emb)) ** 0.5
                sim = dot / (norm_q * norm_d + 1e-9)
                scores.append((i, float(sim)))
            scores.sort(key=lambda x: x[1], reverse=True)
            return [
                RetrievedDoc(
                    title=self.sections[i][0],
                    content=self.sections[i][1],
                    score=score,
                )
                for i, score in scores[:k]
            ]
        return super().retrieve(query, k=k)