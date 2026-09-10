from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings

# all-MiniLM-L6-v2 is a small, public sentence-transformer. It needs no API
# token, so we don't call huggingface_hub.login() here. The model is loaded
# lazily the first time semantic_chunk() runs, not at import time, so simply
# importing this module (which the router does, indirectly) stays cheap.

_chunker = None


def _get_chunker():
    global _chunker
    if _chunker is None:
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        _chunker = SemanticChunker(
            embeddings=embeddings,
            breakpoint_threshold_type="percentile",
            breakpoint_threshold_amount=90,
            min_chunk_size=150,
        )
    return _chunker


def semantic_chunk(text):
    docs = _get_chunker().create_documents([text])
    return [doc.page_content for doc in docs]
