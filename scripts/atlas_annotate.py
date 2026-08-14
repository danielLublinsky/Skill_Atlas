"""Shared Phase-2 derivation: category/tier annotation plus the derived
stat block, over registered skill records.

Two writers emit graph.json + catalog/: the full build (build_graph.py)
and the post-write refresh in categorize.py. Both derive the same fields
from the same curated files, so the derivation lives here once — the two
emission paths cannot drift (DESIGN §13.3).
"""

import atlas_categories


def annotate_skills(skills, categories, config) -> None:
    """Set categories, category_stale and searchable on every registered
    skill record from the curated files. Works on discovery records and
    graph nodes alike — graph nodes drop a falsy plugin_key, hence .get().
    A stale desc_hash keeps its labels in effect; an assignment whose skill
    left the graph is environmental drift, surfaced as orphan_assignments.
    """
    assignments = categories["assignments"]
    searchable_plugins = set(config["searchable_plugins"])
    for skill in skills:
        entry = assignments.get(skill["id"])
        skill["categories"] = list(entry["categories"]) if entry else []
        skill["category_stale"] = bool(entry) and (
            entry["desc_hash"] != atlas_categories.desc_hash(skill.get("description")))
        skill["searchable"] = (
            skill.get("scope") == "plugin"
            and (skill.get("plugin") in searchable_plugins
                 or skill.get("plugin_key") in searchable_plugins))


def phase2_stats(skills, categories, duplicate_names) -> dict:
    """The derived stat block over annotated skills: the categorization TODO
    counts plus the search-facing catalog rollup. The rollup covers tiers
    1+2 only (enabled or searchable) — tier-off skills are never
    search-visible. Zero-count categories are kept: the frozen taxonomy is
    a stable index shape."""
    orphan_assignments = atlas_categories.orphan_ids(
        categories["assignments"], {s["id"] for s in skills}, duplicate_names)
    catalog_skills = [s for s in skills if s.get("enabled") or s.get("searchable")]
    catalog_counts = {entry["name"]: 0 for entry in categories["taxonomy"]}
    for skill in catalog_skills:
        for label in skill["categories"]:
            catalog_counts[label] += 1
    return {
        "uncategorized": sum(1 for s in skills if not s["categories"]),
        "stale_categories": sum(1 for s in skills if s["category_stale"]),
        "searchable": sum(1 for s in skills if s["searchable"]),
        "orphan_assignments": orphan_assignments,
        "catalog": {
            "dormant": sum(1 for s in catalog_skills if not s.get("enabled")),
            "categories": catalog_counts,
            "uncategorized": sum(1 for s in catalog_skills
                                 if not s["categories"]),
        },
    }
