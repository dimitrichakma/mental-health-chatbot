import json
import os
from pathlib import Path

import pandas as pd
import voyageai
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

_vo = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])


class VoyageEmbeddings(Embeddings):
    """Thin adapter so SemanticChunker can use voyage-3.5.

    We chunk one document at a time, so each embed_documents call is only the
    sentences of that document (well within Voyage's batch limits). Using the
    same model as the vector store means the semantic breakpoints live in the
    same space the retriever searches.
    """

    model = "voyage-3.5"

    def embed_documents(self, texts):
        out = []
        for i in range(0, len(texts), 128):
            resp = _vo.embed(texts[i:i + 128], model=self.model, input_type="document")
            out.extend(resp.embeddings)
        return out

    def embed_query(self, text):
        return _vo.embed([text], model=self.model, input_type="query").embeddings[0]


semantic_splitter = SemanticChunker(
    VoyageEmbeddings(),
    breakpoint_threshold_type="percentile",
    breakpoint_threshold_amount=90,
)

# used for short pmc rows, and as a safety net to cap any oversized piece the
# semantic splitter returns for a document with no clear topic breaks
recursive_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)

WHOLE_ORIGINS = {"counsel_chat", "wikidoc"}  # short, self-contained; never split
SEMANTIC_MIN_CHARS = 3000                    # only long docs are worth semantic chunking
MAX_PIECE_CHARS = 2500                       # re-split anything larger than this
MIN_PIECE_CHARS = 100                        # merge fragments smaller than this

# section values that are structural placeholders, not real topics - drop them
# from the contextual prefix so it reads "[WHO depression]" not
# "[WHO depression — curated_source]"
JUNK_SECTIONS = {"curated_source", "wikidoc_qa", "", "nan"}


def context_prefix(title, section):
    section = "" if section is None else str(section).strip()
    if section and section.lower() not in JUNK_SECTIONS:
        return f"[{title} — {section.replace('_', ' ')}]"
    return f"[{title}]"


def _merge_tiny(pieces):
    # the semantic splitter occasionally emits 30-200 char fragments; fold each
    # into the previous piece so we don't index near-empty vectors
    merged = []
    for p in pieces:
        if merged and len(p) < MIN_PIECE_CHARS:
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged


def chunk_row(row):
    text = str(row["text"])
    if row["origin"] in WHOLE_ORIGINS:
        return [text]
    if len(text) >= SEMANTIC_MIN_CHARS:
        pieces = []
        for p in semantic_splitter.split_text(text):
            pieces.extend(recursive_splitter.split_text(p) if len(p) > MAX_PIECE_CHARS else [p])
        return _merge_tiny(pieces)
    return recursive_splitter.split_text(text)


def main():
    df = pd.read_csv(DATA_DIR / "vector_source_merged.csv")

    final_chunks = []
    for _, row in df.iterrows():
        for piece in chunk_row(row):
            if not piece.strip():
                continue
            title = row["source_title"]
            section = row["section"]
            # contextual prefix: this is what gets embedded, so a chunk taken
            # from the middle of a document still carries where it came from
            embed_text = f"{context_prefix(title, section)} {piece}"
            final_chunks.append({
                "source_title": title,
                "section": section,
                "text": piece,             # clean text, handed to the answer model
                "embed_text": embed_text,  # what build_vector_store.py embeds
                "origin": row["origin"],
                "url": row["url"] if pd.notna(row["url"]) else "",
            })

    print(f"Original rows: {len(df)}")
    print(f"Chunks after splitting: {len(final_chunks)}")
    by_origin = {}
    for c in final_chunks:
        by_origin[c["origin"]] = by_origin.get(c["origin"], 0) + 1
    print("Chunks by origin:", by_origin)

    with open(DATA_DIR / "vector_chunks_final.json", "w") as f:
        json.dump(final_chunks, f)


if __name__ == "__main__":
    main()
