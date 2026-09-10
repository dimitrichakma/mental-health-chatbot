import hashlib
import os

import voyageai
from dotenv import load_dotenv
from pinecone import Pinecone
from tavily import TavilyClient

from .grading import grade_relevance
from .semantic_chunk import semantic_chunk

load_dotenv()

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
index = pc.Index("cbt-mental-health")
vo = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])


def _stable_id(text):
    # a content hash, so re-ingesting the same passage overwrites the same
    # vector instead of creating a duplicate with a new random id every run
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return f"web_{digest}"


def web_search_and_ingest(question, max_results=3):
    """Live web search as a last resort in the corrective-retrieval flow.

    Pipeline stage (not an LLM tool):
        1. search the web
        2. worthiness check - does what came back actually answer the question?
        3. only if worthy: semantic chunk
        4. embed + upsert into Pinecone (best-effort, for future questions)
        5. return the chunk texts for use on THIS turn

    Returns [] if the search failed or the results were not worth using -
    nothing gets chunked or embedded in that case.
    """
    try:
        search_response = tavily_client.search(question, max_results=max_results)
    except Exception as e:
        print(f"web search failed: {e}")
        return []

    results = [r for r in search_response.get("results", []) if r.get("content", "").strip()]
    if not results:
        return []

    # step 2 - worthiness check on the RAW results, before we spend any effort
    # chunking or embedding. this is the last resort, so accept "ambiguous"
    # (partially on-topic) too; only a clear "incorrect" (off-topic / useless)
    # gets discarded. the synthesizer still says "I don't know" if the text
    # can't actually answer the question.
    raw_text = "\n\n".join(r["content"] for r in results)
    if grade_relevance(question, raw_text) == "incorrect":
        print("web results off-topic, discarding")
        return []

    # step 3 - now chunk the vetted results
    new_chunks = []
    for result in results:
        for piece in semantic_chunk(result["content"]):
            if not piece.strip():
                continue  # semantic_chunk can emit empty pieces; Voyage rejects them
            new_chunks.append({
                "source_title": result.get("title", "web_result"),
                "section": "web_fallback",
                "text": piece,
                "origin": "web_search",
                "url": result.get("url", ""),
            })

    if not new_chunks:
        return []

    chunk_texts = [c["text"] for c in new_chunks]

    # step 4 - best-effort: store for future queries, but don't fail the
    # request if embedding or upsert has a hiccup; we already have the text
    try:
        embed_results = vo.embed(chunk_texts, model="voyage-3.5", input_type="document")
        vectors = [
            {
                "id": _stable_id(chunk["text"]),
                "values": embedding,
                "metadata": {
                    "source_title": chunk["source_title"],
                    "section": chunk["section"],
                    "text": chunk["text"][:1000],
                    "origin": chunk["origin"],
                    "url": chunk["url"],
                },
            }
            for chunk, embedding in zip(new_chunks, embed_results.embeddings)
        ]
        index.upsert(vectors=vectors, namespace="default")
    except Exception as e:
        print(f"web result ingest failed (answer still uses the text): {e}")

    return chunk_texts
