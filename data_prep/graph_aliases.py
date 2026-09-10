"""Node-name canonicalization for the knowledge graph.

The source CSV has ~4,500 unique node names for maybe a third as many real
concepts - "Anxiety", "Anxiety Disorder", "Anxiety Disorders", "Anxiety State"
are four nodes. This map folds the clear synonyms / plurals / casing variants /
acronyms of the CORE concepts onto one canonical name so their edges
consolidate. Genuine subtypes (Generalized Anxiety Disorder, Separation
Anxiety Disorder, ...) are deliberately left alone.

Keys are matched case-insensitively against the whitespace-trimmed node name.
"""

NODE_ALIASES = {
    # --- anxiety (core concept) ---
    "anxiety": "Anxiety Disorder",
    "anxiety disorders": "Anxiety Disorder",
    "anxiety state": "Anxiety Disorder",
    "anxiety states, neurotic": "Anxiety Disorder",
    "anxiety and fear": "Anxiety Disorder",
    "anxiety attack": "Anxiety Disorder",
    "anxiety complex": "Anxiety Disorder",
    "neuroses, anxiety": "Anxiety Disorder",
    "anxiety neurosis": "Anxiety Disorder",

    # --- unipolar depression (core concept; bipolar-depression left separate) ---
    "depression": "Major Depressive Disorder",
    "depressive disorder": "Major Depressive Disorder",
    "unipolar depression": "Major Depressive Disorder",
    "endogenous depression": "Major Depressive Disorder",
    "mental depression": "Major Depressive Disorder",
    "clinical depression": "Major Depressive Disorder",
    "major depression": "Major Depressive Disorder",
    "major depression, single episode": "Major Depressive Disorder",
    "major depressive disorder, single episode": "Major Depressive Disorder",
    "affective depression": "Major Depressive Disorder",
    "depressive episode": "Major Depressive Disorder",

    # --- OCD (disorder; personality/trait variants left separate) ---
    "ocd": "Obsessive-Compulsive Disorder",
    "obsessive compulsive disorder": "Obsessive-Compulsive Disorder",
    "obsessive-compulsive behavior": "Obsessive-Compulsive Disorder",
    "obsessive compulsive behavior": "Obsessive-Compulsive Disorder",
    "obsessive-compulsive disorders and symptoms": "Obsessive-Compulsive Disorder",

    # --- PTSD ---
    "ptsd": "Post-Traumatic Stress Disorder",
    "posttraumatic stress disorder": "Post-Traumatic Stress Disorder",
    "post traumatic stress disorder": "Post-Traumatic Stress Disorder",

    # --- ADHD (inattentive-only "Attention Deficit Disorder" left separate) ---
    "adhd": "Attention Deficit Hyperactivity Disorder",
    "attention deficit hyperactivity disorder (adhd)": "Attention Deficit Hyperactivity Disorder",
    "attention deficit-hyperactivity disorder": "Attention Deficit Hyperactivity Disorder",
    "adult attention deficit hyperactivity disorder": "Attention Deficit Hyperactivity Disorder",

    # --- bipolar (core; current-episode subtypes left separate) ---
    "bipolar affective disorder": "Bipolar Disorder",
    "bipolar affective disorders": "Bipolar Disorder",
    "manic depressive disorder": "Bipolar Disorder",
    "manic-depressive disorder": "Bipolar Disorder",

    # --- social anxiety (synonyms) ---
    "social phobia": "Social Anxiety Disorder",
    "phobia, social": "Social Anxiety Disorder",

    # --- panic ---
    "panic attack": "Panic Attacks",
    "panic disorder without agoraphobia": "Panic Disorder",

    # --- schizophrenia (course/subtype variants left separate) ---
    "schizophrenic disorder": "Schizophrenia",
    "schizophrenic disorders": "Schizophrenia",
}
