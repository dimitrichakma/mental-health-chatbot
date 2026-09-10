import json
from pathlib import Path
from pinecone import Pinecone, ServerlessSpec
import voyageai
from dotenv import load_dotenv
import os

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

with open(DATA_DIR / "vector_chunks_final.json") as f:
    chunks = json.load(f)

pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
INDEX_NAME = "cbt-mental-health"

if INDEX_NAME not in [idx["name"] for idx in pc.list_indexes()]:
    pc.create_index(
        name=INDEX_NAME,
        dimension=1024,  # matches voyage-3.5's default output size
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1")
    )

index = pc.Index(INDEX_NAME)
vo = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])

vectors = []
# smaller batch: chunks now carry a contextual prefix and some (whole
# counsel_chat answers) are up to ~6k chars, so 32 keeps us well under
# Voyage's per-request token limit
batch_size = 32
for i in range(0, len(chunks), batch_size):
    batch = chunks[i:i+batch_size]
    # embed the prefixed text ("[title — section] ...") so a mid-document
    # chunk still retrieves on its source context; fall back to plain text
    # for any older json without the field
    texts = [c.get("embed_text", c["text"]) for c in batch]
    # input_type="document" tells Voyage these are being stored for retrieval,
    # not asked as a question, which measurably improves retrieval quality
    result = vo.embed(texts, model="voyage-3.5", input_type="document")
    for chunk, embedding in zip(batch, result.embeddings):
        vectors.append({
            "id": f"chunk_{len(vectors)}",
            "values": embedding,
            "metadata": {
                "source_title": chunk["source_title"],
                "section": chunk["section"],
                # store the clean text (no prefix) for the answer model;
                # 6000 chars is safe under Pinecone's 40KB metadata cap
                "text": chunk["text"][:6000],
                "origin": chunk["origin"],
                "url": chunk["url"]
            }
        })
    print(f"Embedded {min(i+batch_size, len(chunks))} / {len(chunks)}")

for i in range(0, len(vectors), 100):
    index.upsert(vectors=vectors[i:i+100], namespace="default")
    print(f"Uploaded {min(i+100, len(vectors))} / {len(vectors)}")

print(f"Done. Total vectors in index: {index.describe_index_stats()['total_vector_count']}")