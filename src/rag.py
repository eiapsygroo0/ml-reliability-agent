"""Runbook RAG (keyword + optional embedding) and optional RAGEngine (hybrid + rerank + Gemini) for pre-built indices."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi
import google.generativeai as genai



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


# Shared embedding model (EmbeddingRunbookRAG and RAGEngine)
RUNBOOK_EMBED_MODEL = "all-MiniLM-L6-v2"


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
                self._model = SentenceTransformer(RUNBOOK_EMBED_MODEL)
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


# --- RAGEngine (optional: hybrid retrieval + rerank + Gemini) ---

RAG_ENGINE_INDEX_PATH = "index.faiss"
RAG_ENGINE_META_PATH = "chunks.npy"
RAG_ENGINE_EMBED_MODEL = RUNBOOK_EMBED_MODEL
RAG_ENGINE_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RAG_ENGINE_GEMINI_MODEL = "gemini-2.5-flash"
HYBRID_ALPHA = 0.6
RERANK_CANDIDATE_MULTIPLIER = 3


class RAGEngine:
    """Hybrid (dense + sparse) retrieval with reranking and Gemini for answer generation. Requires pre-built FAISS index and chunks."""

    def __init__(
        self,
        index_path: str = RAG_ENGINE_INDEX_PATH,
        meta_path: str = RAG_ENGINE_META_PATH,
    ):
        if not _RAG_ENGINE_DEPS:
            raise ImportError(
                "RAGEngine requires numpy, faiss-cpu, sentence-transformers, rank-bm25, google-generativeai. "
                f"Install them or see: {_RAG_ENGINE_IMPORT_ERROR}"
            ) from _RAG_ENGINE_IMPORT_ERROR
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("RAGEngine requires GEMINI_API_KEY for answer() and _self_check.")
        genai.configure(api_key=api_key)

        self.embed_model = SentenceTransformer(RAG_ENGINE_EMBED_MODEL)
        self.index = faiss.read_index(index_path)
        self.chunks: List[Dict] = np.load(meta_path, allow_pickle=True).tolist()
        self._build_bm25()
        self.reranker = CrossEncoder(RAG_ENGINE_RERANK_MODEL)
        self.llm = genai.GenerativeModel(RAG_ENGINE_GEMINI_MODEL)
        
    def _tokenize(self, text:str) -> List[str]:
        return text.lower().split()
    
    def _build_bm25(self):
        self.bm25_corpus_tokens: List[List[str]] = []
        for ch in self.chunks:
            tokens = self._tokenize(ch["text"])
            self.bm25_corpus_tokens.append(tokens)
        self.bm25 = BM25Okapi(self.bm25_corpus_tokens)

    def embed_query(self, query: str) -> "np.ndarray":
        emb = self.embed_model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(emb)
        return emb
    
    # ------------- Dense retrieval -------------
    def retrieve_dense(self, query: str, k: int = 30) -> List[Dict]:
        q_embed = self.embed_query(query)
        D, I = self.index.search(q_embed, k)
        idxs, ds = I[0], D[0]
        
        results = []
        for rank, (i, score) in enumerate(zip(idxs, ds), start=1):
            if i == -1: continue
            chunk = self.chunks[i]
            results.append({
                "idx": i,
                "rank_dense":rank,
                "score_dense": float(score),
                "text": chunk["text"],
                "source_path": chunk["source_path"],
                "chunk_id": chunk["chunk_id"]
            })
            
        return results
    # ------------- Sparse retrieval (BM25) -------------
    def retrieve_sparse(self, query: str, k: int = 30) -> List[Dict]:
        query_tokens = self._tokenize(query)
        scores = self.bm25.get_scores(query_tokens)
        
        idxs = np.argsort(scores)[::-1][:k]
        results = []
        
        for rank, i in enumerate(idxs, start=1):
            score = float(scores[i])
            if (score <= 0): continue
            chunk = self.chunks[i]
            results.append({
                "idx": int(i),
                "rank_sparse": rank,
                "score_sparse": score,
                "text": chunk["text"],
                "source_path": chunk["source_path"],
                "chunk_id": chunk["chunk_id"],
            })
        return results
    
    #------------------ Hybrid fusion + reranking --------------
    
    def retrieve_hybrid(self, 
                        query:str,
                        k_dense:int = 30,
                        k_sparse:int = 30,
                        final_k: int = 10
                        ) -> List[Dict]:
        dense = self.retrieve_dense(query, k=k_dense)
        sparse = self.retrieve_sparse(query, k=k_sparse)
        
        candidates: Dict[int, Dict] = {}
        
        def add_results(res_list, mode:str):
            for r in res_list:
                idx = r["idx"]
                if idx not in candidates:
                    candidates[idx] = {
                        "idx":idx,
                        "text": r["text"],
                        "source_path": r["source_path"],
                        "chunk_id": r["chunk_id"],
                        "score_dense": 0.0,
                        "score_sparse": 0.0,
                    }
                candidates[idx][f"score_{mode}"] = r[f"score_{mode}"]
        
        add_results(dense, "dense")
        add_results(sparse, "sparse")
        
        # Normalize scores separately (avoid dominance)
        dense_scores = [c["score_dense"] for c in candidates.values()]
        sparse_scores = [c["score_sparse"] for c in candidates.values()]
        
        def normalize(scores):
            arr = np.array(scores, dtype=np.float32)
            if arr.max() == arr.min():
                return np.zeros_like(arr)
            return (arr - arr.min()) / (arr.max() - arr.min())
        
        norm_dense = normalize(dense_scores)
        norm_sparse = normalize(sparse_scores)
        
        for (c, nd, ns) in zip(candidates.values(), norm_dense, norm_sparse):
            c["score_fused"] = HYBRID_ALPHA * float(nd) + (1.0 - HYBRID_ALPHA) * float(ns)

        fused_score_sorted = sorted(candidates.values(), key=lambda x: x["score_fused"], reverse=True)
        fused_score_sorted = fused_score_sorted[: max(final_k * RERANK_CANDIDATE_MULTIPLIER, final_k)]
        
        fused_score_sorted = self._rerank(query, fused_score_sorted, top_k=final_k)
        
        for rank, c in enumerate(fused_score_sorted, start=1):
            c["rank"] = rank
        
        return fused_score_sorted
        
    def _rerank(self, query:str, candidates:List[Dict], top_k:int = 10) -> List[Dict]:
        if not candidates: return []
        
        pairs = [[query, c["text"]] for c in candidates]
        scores = self.reranker.predict(pairs)
        
        for c, s in zip(candidates, scores):
            c["score_rerank"] = float(s)
            
        reranked = sorted(candidates, key=lambda x: x["score_rerank"], reverse=True)
        return reranked[:top_k]
    
    def build_prompt(self, query:str, contexts:List[Dict]) -> str:
        context_strs = []
        for i, ctx in enumerate(contexts, start=1):
            context_strs.append(
                f"[{i}] Source: {ctx['source_path']}\n{ctx['text']}\n"
            )
            
        context_block = "\n".join(context_strs)
        
        prompt = f"""
        You are a careful assistant. Answer questions ONLY using the provided context.
        If the answer cannot be clearly found in the context, say:
        "I don't know based on the provided documents."

        CONTEXT:
        {context_block}

        ---

        Question: {query}

        In your answer:
        - Use natural language.
        - Do NOT introduce facts that are not supported by the context.
        - At the end of each sentence that uses specific info from a chunk, add the citation like [1], [2], etc.
        """
        return prompt.strip()
    
    def _self_check(self, query:str, answer:str, contexts:List[Dict]) -> str:
        context_strs = []
        for i, ctx in enumerate(contexts, start=1):
            context_strs.append(
                f"[{i}] Source: {ctx['source_path']}\n{ctx['text']}\n"
            )
            
        context_block = "\n".join(context_strs)
        critique_prompt = f"""
        You are a strict verifier.

        Given:
        - The user's question
        - The retrieved context
        - An answer that was generated using that context

        Task:
        1. Identify any statements in the answer that are NOT clearly supported by the context or that seem speculative.
        2. If everything is well-supported, say "All major statements are supported by the context."

        Question:
        {query}

        CONTEXT:
        {context_block}

        ANSWER:
        {answer}

        Now provide your critique:
        """
        resp = self.llm.generate_content(
            critique_prompt,
            generation_config={"temperature": 0.0},
        )
        return resp.text
    
    def answer(self, query: str, k: int = 5, do_self_check: bool = True) -> Dict:
        # 1. Hybrid + rerank retrieval
        contexts = self.retrieve_hybrid(query, final_k= k)
        # 2. Build prompt
        prompt = self.build_prompt(query, contexts)
        # 3. Call Gemini
        response = self.llm.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1
            }
        )
        answer_text = response.text
        critique_text = None
        if do_self_check:
            critique_text = self._self_check(query, answer_text, contexts)

        return {
            "answer": answer_text,
            "contexts": contexts,
            "critique": critique_text,
        }