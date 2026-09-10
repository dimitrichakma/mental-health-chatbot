from langchain_neo4j import Neo4jGraph
from dotenv import load_dotenv
import os

from .graph_aliases import NODE_ALIASES

load_dotenv()

CSV_URL = "https://raw.githubusercontent.com/dimitrichakma/cbt-graph-data/main/graph_triples_rebalanced.csv"

# Tier 1 - drop at load time. The CSV stays the raw source of record; this
# script is the transform.
#   kaggle_mental_illness_survey  - generic symptom bag pinned to every disorder
#   disease_protein               - PrimeKG protein associations (~26% of the graph)
#   disease_phenotype_positive/negative - rare-genetic-syndrome phenotype links
#   drug_effect                   - drug -> side-effect, sparse and low value here
#   has_broader/has_narrower_concept - near-duplicates of has_parent/has_child
#   phenotype_phenotype, bioprocess_bioprocess, phenotype_protein - PrimeKG cruft
SKIP_ORIGINS = ["kaggle_mental_illness_survey"]
SKIP_RELATIONS = [
    "disease_protein",
    "disease_phenotype_positive",
    "disease_phenotype_negative",
    "drug_effect",
    "has_broader_concept",
    "has_narrower_concept",
    "phenotype_phenotype",
    "bioprocess_bioprocess",
    "phenotype_protein",
]

# --- load: Tier 1 filter, Tier 2 canonicalization, :Entity label ---
# canonical name = NODE_ALIASES[lower(trimmed name)] if present, else the
# trimmed name. self-loops created by canonicalization (or already in the
# data) are dropped.
load_query = """
LOAD CSV WITH HEADERS FROM $csv_url AS row
CALL (row) {
    WITH row
    WHERE NOT row.origin IN $skip_origins AND NOT row.relation IN $skip_relations
    WITH row,
         string.regexReplace(trim(row.source), ' +', ' ') AS s_raw,
         string.regexReplace(trim(row.target), ' +', ' ') AS t_raw
    WITH row,
         coalesce($aliases[toLower(s_raw)], s_raw) AS s_name,
         coalesce($aliases[toLower(t_raw)], t_raw) AS t_name
    WHERE s_name <> t_name AND s_name <> '' AND t_name <> ''
      // drop nodes with a lone unbalanced paren - these are comma-split
      // fragments from kaggle_disease_symptoms, e.g. "Medications (antidepressants"
      AND NOT ((s_name CONTAINS '(') XOR (s_name CONTAINS ')'))
      AND NOT ((t_name CONTAINS '(') XOR (t_name CONTAINS ')'))
    MERGE (a:Entity {name: s_name})
    MERGE (b:Entity {name: t_name})
    MERGE (a)-[r:RELATION {type: row.relation, origin: row.origin}]->(b)
    WITH a, b, row
    // native dynamic labels (SET n:$(...)) instead of the deprecated
    // apoc.create.addLabels procedure
    SET a:$(apoc.text.capitalize(replace(replace(row.source_type, ' ', '_'), '-', '_'))),
        b:$(apoc.text.capitalize(replace(replace(row.target_type, ' ', '_'), '-', '_')))
    RETURN a, b
} IN TRANSACTIONS OF 1000 ROWS
RETURN count(*) AS rows_loaded
"""


def main():
    graph = Neo4jGraph(
        url=os.environ["NEO4J_URI"],
        username=os.environ["NEO4J_USERNAME"],
        password=os.environ["NEO4J_PASSWORD"],
    )

    apoc = graph.query("RETURN apoc.version() AS version")
    print("APOC version:", apoc[0]["version"])

    # wipe first, so this is a clean reload rather than an additive MERGE.
    # the graph is small (~2k nodes) so a single DETACH DELETE is fine and
    # avoids the deprecated apoc.periodic.iterate.
    print("Clearing existing graph...")
    graph.query("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 5000 ROWS")
    graph.query("CALL apoc.schema.assert({}, {})")  # drop stale indexes/constraints
    print("Cleared.")

    result = graph.query(load_query, params={
        "csv_url": CSV_URL,
        "skip_origins": SKIP_ORIGINS,
        "skip_relations": SKIP_RELATIONS,
        "aliases": NODE_ALIASES,
    })
    print(f"Rows loaded (after filtering + canonicalization): {result[0]['rows_loaded']}")

    graph.query("CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)")
    graph.query("CREATE FULLTEXT INDEX entity_name_ft IF NOT EXISTS FOR (n:Entity) ON EACH [n.name]")
    graph.query("CALL db.awaitIndexes(300)")
    print("Indexes created.")

    nodes = graph.query("MATCH (n:Entity) RETURN count(n) AS c")[0]["c"]
    rels = graph.query("MATCH ()-[r:RELATION]->() RETURN count(r) AS c")[0]["c"]
    print(f"Graph: {nodes} nodes, {rels} relationships")
    for row in graph.query("MATCH ()-[r:RELATION]->() RETURN r.type AS t, count(*) AS c ORDER BY c DESC LIMIT 12"):
        print(f"  {row['t']:28} {row['c']}")
    print("Graph loaded")


if __name__ == "__main__":
    main()
