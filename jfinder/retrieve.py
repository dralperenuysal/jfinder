"""BM25 shortlist over the journal index (AGENTS.md §8).

Filters run before this (see data.apply_filters); BM25 ranks what survives.
"""

from __future__ import annotations

import pandas as pd
from rank_bm25 import BM25Okapi


def shortlist(df: pd.DataFrame, profile: dict[str, object], n: int = 40) -> pd.DataFrame:
    """Score journals with BM25 over name + topics; return the top n.

    The query comes from the profile's field, subfields and keywords. In
    offline mode the profile is built from the abstract's own words.
    """
    corpus = (df["name"] + " " + df["topics"].str.join(" ")).str.lower().str.split()
    bm25 = BM25Okapi(corpus.tolist())

    keywords = profile.get("keywords", [])
    keyword_list = [str(k) for k in keywords] if isinstance(keywords, list) else []
    subfields = profile.get("subfields", [])
    subfield_list = [str(s) for s in subfields] if isinstance(subfields, list) else []
    query_parts = [str(profile.get("field", "")), *subfield_list, *keyword_list]
    query = " ".join(query_parts).lower().split()

    scored = df.assign(_score=bm25.get_scores(query))
    return scored.nlargest(n, "_score")
