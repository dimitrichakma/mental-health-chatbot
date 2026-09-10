from pinecone import Pinecone
import voyageai
from langchain_neo4j import Neo4jGraph
from dotenv import load_dotenv
import os

load_dotenv()

pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
index = pc.Index("cbt-mental-health")
vo = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])

graph = Neo4jGraph(
    url=os.environ["NEO4J_URI"],
    username=os.environ["NEO4J_USERNAME"],
    password=os.environ["NEO4J_PASSWORD"]
)

def naive_rag_retrieve(question, n=4, namespace="default"):
    result = vo.embed([question], model="voyage-3.5", input_type="query")
    results = index.query(vector=result.embeddings[0], top_k=n, namespace=namespace, include_metadata=True)
    return [match["metadata"]["text"] for match in results["matches"]]

# relations grouped by how specific a fact they carry, so retrieval can rank
# them: a "contraindication" edge is worth more in an answer than a vague
# "this disease is related to that disease" edge, which is worth more than a
# plain "X is a kind of Y" hierarchy edge.
SPECIFIC_RELATIONS = [
    "reflects", "reflects_fine", "exhibits", "triggers", "produces", "shapes",
    "has_symptom", "has_manifestation", "diagnostic_criteria_of", "has_diagnostic_criteria",
    "indication", "contraindication", "off-label use", "drug_effect", "treated_by",
    "co-occurs_with", "clinically_associated_with", "associated_with",
]
BROAD_RELATIONS = ["disease_disease", "disease_phenotype_positive", "clinically_similar"]
STRUCTURAL_RELATIONS = ["has_child_concept", "has_parent_concept", "has_narrower_concept", "has_broader_concept"]

# kaggle_mental_illness_survey is a generic symptom bag pinned onto every
# disorder (manic + psychotic + PTSD symptoms all at once). disease_protein
# is real but useless for a mental-health answer. both are excluded unless
# nothing else matches at all.
NOISY_ORIGINS = ["kaggle_mental_illness_survey"]
USELESS_RELATIONS = ["disease_protein"]

# nodes are matched by name-substring, either direction. the size guard stops
# 1-4 char node names matching almost everything. every node carries the
# :Entity label (see load_neo4j.py); a full-text index `entity_name_ft` also
# exists on :Entity(name) for a future perf pass if CONTAINS gets slow.
_ENTITY_MATCH = """
    toLower(a.name) CONTAINS toLower($entity_name)
    OR (size(a.name) > 4 AND toLower($entity_name) CONTAINS toLower(a.name))
"""


def _diversify(rows, entity_name, limit, max_per_relation=6):
    # rows arrive already ordered by relevance tier. group them by relation
    # (keeping that order), then fill the result round-robin: one edge from
    # every relation type, then a second from each, and so on. this guarantees
    # a rare-but-relevant relation (e.g. has_child_concept for a "related
    # disorders" question) gets a slot instead of being buried under 25 drug
    # contraindication edges. return readable strings so the grader and answer
    # model can parse the facts, not raw dicts.
    seen, groups, order = set(), {}, []
    for r in rows:
        key = (r["connected_entity"], r["relation"])
        if key in seen:
            continue
        seen.add(key)
        rel = r["relation"]
        if rel not in groups:
            groups[rel] = []
            order.append(rel)
        if len(groups[rel]) < max_per_relation:
            groups[rel].append(r["connected_entity"])

    out, depth = [], 0
    while len(out) < limit:
        progressed = False
        for rel in order:
            if depth < len(groups[rel]):
                out.append(f"{entity_name} — {rel.replace('_', ' ')} — {groups[rel][depth]}")
                progressed = True
                if len(out) >= limit:
                    break
        if not progressed:
            break
        depth += 1
    return out


def graph_rag_retrieve(entity_name, limit=25):
    if not entity_name:
        return []

    # primary: only meaningful relations, skip the noisy origin, and rank
    # specific facts above vague "related disease" links above plain hierarchy.
    # pull extra (LIMIT 60) so _diversify has room to balance relation types.
    primary = graph.query(
        f"""
        MATCH (a:Entity) WHERE {_ENTITY_MATCH}
        MATCH (a)-[r:RELATION]-(b)
        WHERE r.type IN $wanted AND NOT r.origin IN $noisy
        WITH b.name AS connected_entity, r.type AS relation, r.origin AS origin,
             toLower(a.name) = toLower($entity_name) AS exact
        RETURN DISTINCT connected_entity, relation, origin, exact
        ORDER BY
            CASE WHEN exact THEN 0 ELSE 1 END,
            CASE WHEN relation IN $specific THEN 0 WHEN relation IN $broad THEN 1 ELSE 2 END
        LIMIT 60
        """,
        params={
            "entity_name": entity_name,
            "wanted": SPECIFIC_RELATIONS + BROAD_RELATIONS + STRUCTURAL_RELATIONS,
            "specific": SPECIFIC_RELATIONS,
            "broad": BROAD_RELATIONS,
            "noisy": NOISY_ORIGINS,
        },
    )
    if len(primary) >= 3:
        return _diversify(primary, entity_name, limit)

    # entity matched but had few "good" edges. widen to any relation (still
    # skipping disease_protein and the noisy origin).
    fallback = graph.query(
        f"""
        MATCH (a:Entity) WHERE {_ENTITY_MATCH}
        MATCH (a)-[r:RELATION]-(b)
        WHERE NOT r.type IN $useless AND NOT r.origin IN $noisy
        WITH b.name AS connected_entity, r.type AS relation, r.origin AS origin,
             toLower(a.name) = toLower($entity_name) AS exact
        RETURN DISTINCT connected_entity, relation, origin, exact
        ORDER BY CASE WHEN exact THEN 0 ELSE 1 END
        LIMIT 60
        """,
        params={"entity_name": entity_name, "useless": USELESS_RELATIONS, "noisy": NOISY_ORIGINS},
    )
    if primary or fallback:
        return _diversify(primary + fallback, entity_name, limit)

    # nothing at all, allow even the noisy sources as a last resort
    last = graph.query(
        f"""
        MATCH (a:Entity) WHERE {_ENTITY_MATCH}
        MATCH (a)-[r:RELATION]-(b)
        RETURN DISTINCT b.name AS connected_entity, r.type AS relation, r.origin AS origin
        LIMIT 60
        """,
        params={"entity_name": entity_name},
    )
    return _diversify(last, entity_name, limit)


def retrieve_both(question, entity):
    """naive (vector) + graph retrieval concurrently - two independent network
    round-trips that were being done back-to-back on the "both" path."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        vec = pool.submit(naive_rag_retrieve, question)
        gr = pool.submit(graph_rag_retrieve, entity)
        return vec.result() + gr.result()
