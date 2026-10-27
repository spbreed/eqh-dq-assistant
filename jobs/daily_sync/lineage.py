"""View-definition lineage with sqlglot (Redshift dialect): table-level sources and column-level mappings.

Works for late-binding views (not in pg_depend), regular views and materialized views.
"""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

NO_BINDING = re.compile(r"\s*with\s+no\s+schema\s+binding\s*;?\s*$", re.IGNORECASE)
CREATE_PREFIX = re.compile(r"^\s*create\s+(or\s+replace\s+)?(materialized\s+)?view\s+[\w.\"]+\s+.*?\bas\b\s*",
                           re.IGNORECASE | re.DOTALL)


def clean(sql: str) -> str:
    sql = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    sql = NO_BINDING.sub("", sql.strip())
    sql = CREATE_PREFIX.sub("", sql, count=1)
    return sql.rstrip(";")


def _full(t: exp.Table, default_schema: str) -> str:
    return f"{(t.db or default_schema).lower()}.{t.name.lower()}"


def parse_view(sql: str, default_schema: str = "public") -> tuple[set[str], list[dict]]:
    """Return (source tables 'schema.table', column mappings [{src, src_col, dst_col}])."""
    try:
        tree = sqlglot.parse_one(clean(sql), read="redshift")
    except sqlglot.errors.ParseError:
        return set(), []
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    sources = {_full(t, default_schema) for t in tree.find_all(exp.Table)
               if t.name and t.name.lower() not in ctes}

    # alias -> set of physical tables (subquery aliases map to all tables inside them)
    alias: dict[str, set[str]] = {}
    for t in tree.find_all(exp.Table):
        if t.name.lower() in ctes:
            continue
        full = _full(t, default_schema)
        alias.setdefault((t.alias or t.name).lower(), set()).add(full)
    for sq in tree.find_all(exp.Subquery):
        if sq.alias:
            alias[sq.alias.lower()] = {_full(t, default_schema) for t in sq.find_all(exp.Table)
                                       if t.name.lower() not in ctes}

    outer = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    mappings = []
    if outer is not None:
        single = next(iter(sources)) if len(sources) == 1 else None
        for proj in outer.expressions:
            dst = proj.alias_or_name.lower()
            for col in proj.find_all(exp.Column):
                tabs = alias.get(col.table.lower(), set()) if col.table else ({single} if single else set())
                for src in tabs:
                    mappings.append({"src": src, "src_col": col.name.lower(), "dst_col": dst})
    return sources, mappings


def referenced_tables(sql: str) -> set[str]:
    """Tables/views a user query reads (for usage edges)."""
    try:
        trees = sqlglot.parse(sql, read="redshift")
    except sqlglot.errors.ParseError:
        return set()
    out = set()
    for tree in trees:
        if tree is None:
            continue
        ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
        out |= {_full(t, "public") for t in tree.find_all(exp.Table) if t.db and t.name.lower() not in ctes}
    return out
