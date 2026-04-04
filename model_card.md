# DocuBot Model Card

---

## 1. System Overview

**What is DocuBot trying to do?**

DocuBot is a lightweight documentation assistant that answers developer questions about a codebase. It reads local markdown files, retrieves relevant snippets, and optionally uses an LLM to generate grounded answers. The goal is to reduce hallucinations compared to naive LLM generation by grounding responses in actual documentation.

**What inputs does DocuBot take?**

- A natural language question from the developer
- Markdown files in the `docs/` folder
- An optional `GEMINI_API_KEY` environment variable for LLM-powered modes

**What outputs does DocuBot produce?**

- Mode 1: A free-form LLM answer with no retrieval grounding
- Mode 2: Raw retrieved paragraph snippets with source filenames
- Mode 3: A synthesized LLM answer citing only the retrieved snippets, or an explicit refusal if evidence is insufficient

---

## 2. Retrieval Design

**How does your retrieval system work?**

- **Indexing:** Each document is split into paragraph-level chunks (separated by blank lines). An inverted index maps lowercase words to the chunks they appear in.
- **Scoring:** Each candidate chunk is scored by counting total occurrences of non-stop query words in the chunk text. Stop words (e.g. "the", "how", "is") are excluded so that common words don't inflate scores.
- **Selection:** Candidates are ranked by score descending. Chunks scoring at or below the threshold (≤1) are filtered out. The top 3 chunks are returned.

**What tradeoffs did you make?**

- Simplicity over accuracy: term-overlap scoring is fast and requires no external libraries, but misses synonyms and semantic similarity.
- Paragraph chunking improves precision over whole-document retrieval but can still return the wrong paragraph if query words appear in multiple places.
- Stop word filtering improves ranking but required manual tuning — removing "stored" from stop words was needed to surface the users table schema.

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**

- **Naive LLM mode:** Calls the LLM for every query using a generic prompt with no retrieved context. The LLM answers from its own training data.
- **Retrieval only mode:** Never calls the LLM. Returns raw retrieved snippets directly to the user.
- **RAG mode:** Calls the LLM only after retrieval. If no snippets pass the threshold, returns a hardcoded refusal without calling the LLM at all.

**What instructions do you give the LLM to keep it grounded?**

- Answer using only the provided snippets
- Do not invent functions, endpoints, or configuration values
- If snippets are insufficient, reply exactly: "I do not know based on the docs I have."
- Mention which files the answer is drawn from

---

## 4. Experiments and Comparisons

| Query | Naive LLM | Retrieval Only | RAG | Notes |
|-------|-----------|----------------|-----|-------|
| Where is the auth token generated? | ⚠️ Harmful — gave generic best practices, no reference to generate_access_token or auth_utils.py | ✅ Helpful — returned correct AUTH.md paragraphs with exact function name | ✅ Helpful — correct answer citing AUTH.md | RAG clearly best here |
| What environment variables are required for authentication? | ⚠️ Harmful — listed generic env var advice unrelated to this codebase | ⚠️ Partial — returned overview paragraph, not the actual variable list | ⚠️ Partial — found AUTH_SECRET_KEY but missed TOKEN_LIFETIME_SECONDS | Retrieval missed the specific section |
| Which endpoint lists all users? | ⚠️ Harmful — invented generic REST patterns, no reference to GET /api/users | ✅ Helpful — returned "Returns a list of all users. Only accessible to admins." from API_REFERENCE.md | ❌ Refused — retrieval missed the right paragraph on that run | Retrieval inconsistent across runs |
| How do I connect to the database? | ⚠️ Harmful — gave 5-language tutorial (PostgreSQL, MySQL, MongoDB) unrelated to this project | ✅ Helpful — returned DATABASE_URL snippet from DATABASE.md | ✅ Helpful — correct answer citing DATABASE.md | Mode 1 most obviously wrong here |
| Is there any mention of payment processing? | ⚠️ Harmful — asked for more info instead of refusing; would likely hallucinate if pushed | ⚠️ Partial — returned an unrelated SETUP.md snippet instead of refusing | ✅ Correct — refused with "I do not know" | Guardrail works in RAG but not retrieval |

**What patterns did you notice?**

- Naive LLM looks impressive but is completely ungrounded — for "How do I connect to the database?" it generated a multi-language tutorial with no relation to the actual project. It sounds authoritative but answers a different question than the one asked.
- Retrieval only is more trustworthy because you can see the source, but raw snippets are hard to interpret — "Returns a list of all users. Only accessible to admins." is accurate but doesn't tell you the endpoint path without reading around it.
- RAG is best when retrieval finds the right chunk. When it does, the LLM synthesizes a clean, cited answer. When retrieval fails or returns weak chunks, RAG correctly refuses rather than guessing — safer than Mode 1 but still unhelpful.

---

## 5. Failure Cases and Guardrails

**Failure case 1**

- Question: "What environment variables are required for authentication?"
- What happened: RAG returned only `AUTH_SECRET_KEY`, missing `TOKEN_LIFETIME_SECONDS`
- What should have happened: Both variables should have been listed (both appear in AUTH.md)
- Root cause: The retrieval returned a SETUP.md paragraph instead of the full AUTH.md environment variables section

**Failure case 2**

- Question: "Which endpoint lists all users?"
- What happened: RAG refused with "I do not know based on the docs I have"
- What should have happened: Should have returned `GET /api/users` from API_REFERENCE.md
- Root cause: The query word "lists" doesn't appear in the relevant paragraph, so the scoring missed it

**When should DocuBot say "I do not know"?**

- When no snippets score above the threshold — the topic is genuinely absent from the docs (e.g. payment processing)
- When retrieved snippets exist but don't contain enough specific information to answer confidently

**What guardrails were implemented?**

- Score threshold: chunks scoring ≤ 1 are discarded before reaching the LLM
- LLM prompt rule: explicit instruction to refuse rather than guess when evidence is weak
- Hard fallback: if `retrieve()` returns an empty list, the answer is a hardcoded refusal without any LLM call

---

## 6. Limitations and Future Improvements

**Current limitations**

1. Term-overlap scoring is brittle — synonyms and paraphrasing cause misses (e.g. "lists" vs "returns")
2. Paragraph chunking can split related content across chunks, losing context
3. The free-tier rate limit (5 requests/minute) makes running all sample queries in RAG mode impractical

**Future improvements**

1. Replace term-overlap scoring with sentence embeddings (e.g. using `sentence-transformers`) for semantic similarity
2. Add overlap between adjacent paragraphs when chunking so context isn't lost at paragraph boundaries
3. Add retry logic with exponential backoff to handle rate limit errors gracefully

---

## 7. Responsible Use

**Where could this system cause real-world harm if used carelessly?**

A developer could trust a confident-sounding RAG answer that is actually based on the wrong snippet. For example, if auth configuration instructions are outdated in the docs, DocuBot will confidently repeat the wrong values. Missing information (like `TOKEN_LIFETIME_SECONDS`) could lead to misconfigured security settings.

**What instructions would you give real developers who want to use DocuBot safely?**

- Always check the cited source file directly before acting on an answer
- Do not use DocuBot for security-critical configuration without human review
- Treat "I do not know" as a signal to search manually, not as confirmation the information doesn't exist
- Keep docs up to date — DocuBot is only as accurate as the files in the `docs/` folder
