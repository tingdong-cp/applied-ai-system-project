"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob
import re

# Minimum relevance score required to return a snippet.
# Snippets with a score at or below this threshold are treated as
# "no useful context found" and trigger the guardrail refusal.
MIN_SCORE_THRESHOLD = 0


class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory as (filename, text) pairs.
        self.documents = self.load_documents()

        # Explode each document into paragraph-level chunks for more
        # precise retrieval. Each chunk is (filename, paragraph_text).
        self.chunks = self._chunk_documents(self.documents)

        # Build a retrieval index over the chunks.
        self.index = self.build_index(self.chunks)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Paragraph Chunking (Part 3 improvement)
    # -----------------------------------------------------------

    def _chunk_documents(self, documents):
        """
        Splits each document into paragraph-level chunks.

        A paragraph is any block of text separated by one or more blank
        lines. Short paragraphs (fewer than 20 characters) are skipped
        because they rarely carry enough information on their own.

        Returns a flat list of (filename, paragraph_text) tuples.
        """
        chunks = []
        for filename, text in documents:
            # Split on one or more blank lines.
            paragraphs = re.split(r"\n\s*\n", text)
            for para in paragraphs:
                para = para.strip()
                if len(para) >= 20:
                    chunks.append((filename, para))
        return chunks

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def build_index(self, documents):
        """
        Builds a tiny inverted index mapping lowercase words to the
        (filename, text) chunks they appear in.

        Structure:
        {
            "token": [(filename, text), ...],
            "database": [(filename, text), ...]
        }

        Tokenisation: split on non-alphanumeric characters, lowercase,
        drop empty strings.
        """
        index = {}
        for filename, text in documents:
            words = set(re.split(r"\W+", text.lower()))
            for word in words:
                if not word:
                    continue
                if word not in index:
                    index[word] = []
                index[word].append((filename, text))
        return index

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------
    def score_document(self, query, text):
        STOP_WORDS = {
            "a", "an", "the", "is", "are", "was", "were", "to", "of", "in",
            "for", "on", "with", "at", "by", "from", "do", "how", "what",
            "where", "which", "there", "any", "all", "this", "that", "these",
            "those", "it", "its", "be", "has", "have", "does", "i", "if",
            "or", "and", "not", "my", "your", "can", "me"
        }
        query_words = re.split(r"\W+", query.lower())
        query_words = [w for w in query_words if w and w not in STOP_WORDS]
        text_lower = text.lower()
        score = sum(text_lower.count(word) for word in query_words)
        return score

    def retrieve(self, query, top_k=3):
        """
        Uses the index to find candidate chunks, scores each one, and
        returns the top_k results sorted by score descending.

        Returns a list of (filename, text) tuples.
        Chunks whose score is at or below MIN_SCORE_THRESHOLD are
        excluded (guardrail: avoids surfacing irrelevant noise).
        """
        # Use the inverted index to collect candidate chunks quickly.
        query_words = set(re.split(r"\W+", query.lower()))
        query_words.discard("")

        candidate_set = {}  # (filename, text) -> (filename, text)
        for word in query_words:
            for chunk in self.index.get(word, []):
                filename, text = chunk
                candidate_set[(filename, text)] = chunk

        if not candidate_set:
            return []

        # Score each candidate.
        scored = []
        for chunk in candidate_set.values():
            filename, text = chunk
            score = self.score_document(query, text)
            if score > MIN_SCORE_THRESHOLD:
                scored.append((score, filename, text))

        # Sort by score descending, then return top_k.
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [(fname, text) for _, fname, text in scored]
        return results[:top_k]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        Used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
