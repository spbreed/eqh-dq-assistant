"""Steward review queue: the assistant's only write path, and it writes to the metadata store only.

approve / edit_approve -> asset.steward_description (+ column steward descriptions from the AI draft),
reject -> status 'rejected'. Every action writes a review_action row and re-embeds the asset.
"""
from __future__ import annotations

import hashlib
import json

from jobs.common import embed as E
from jobs.common import settings
from jobs.common.db import MetaDB


def queue(limit: int = 100) -> list[dict]:
    db = MetaDB(role="assistant")
    rows = db.query("""select asset_key, asset_type, business_domain, source_comment, ai_description, ai_meta,
                              updated_at from asset where ai_description_status = 'draft' and not is_deleted
                       order by business_domain nulls last, asset_key limit :n""", {"n": limit})
    for r in rows:
        r["ai_meta"] = r["ai_meta"] if isinstance(r["ai_meta"], dict) else json.loads(r["ai_meta"] or "{}")
        r["columns"] = db.query("""select c.column_name, c.data_type, c.source_comment, c.ai_description
                                   from asset_column c join asset a using (asset_id) where a.asset_key = :k
                                   order by c.ordinal""", {"k": r["asset_key"]})
    return rows


def act(asset_key: str, action: str, reviewer: str, text: str | None = None) -> dict:
    db = MetaDB(role="assistant")
    cur = db.query("select ai_description, steward_description, platform, asset_type, schema_name, object_name, "
                   "business_domain from asset where asset_key = :k", {"k": asset_key})
    if not cur:
        return {"error": "unknown asset"}
    a = cur[0]
    new = (text or a["ai_description"] or "").strip() if action != "reject" else None
    with db.transaction():
        if action == "reject":
            db.execute("update asset set ai_description_status = 'rejected', updated_at = now() where asset_key = :k",
                       {"k": asset_key})
        else:
            db.execute("""update asset set steward_description = :d, ai_description_status = 'approved',
                          updated_at = now() where asset_key = :k""", {"d": new, "k": asset_key})
            db.execute("""update asset_column set steward_description = ai_description
                          where asset_id = (select asset_id from asset where asset_key = :k)
                            and ai_description is not null and steward_description is null""", {"k": asset_key})
        db.execute("""insert into review_action(asset_key, action, reviewer, old_text, new_text)
                      values (:k, :a, :r, :o, :n)""",
                   {"k": asset_key, "a": action, "r": reviewer, "o": a["ai_description"], "n": new})
        db.execute("update enrichment_task set status = 'skipped', updated_at = now() where asset_key = :k "
                   "and status in ('pending','failed')", {"k": asset_key})
    reembedded = False
    if new:
        loc = ".".join(p for p in ("eqh" if a["platform"] == "redshift" else None, a["schema_name"], a["object_name"])
                       if p)
        content = f"{a['platform']} {a['asset_type']} {loc} (domain: {a['business_domain'] or 'unknown'})\n{new}"
        try:
            v = E.embed(content)
            h = hashlib.sha256(content.encode()).hexdigest()
            m = settings.get()["embed_model"]
            with db.transaction():
                db.execute("delete from embedding where asset_key = :k and chunk_type = 'asset' and model_id = :m",
                           {"k": asset_key, "m": m})
                db.execute("""insert into embedding(asset_key, chunk_type, chunk_ix, model_id, doc_hash, content,
                              embedding) values (:k, 'asset', 0, :m, :h, :c, :v::vector)""",
                           {"k": asset_key, "m": m, "h": h, "c": content, "v": E.vec(v)})
                db.execute("update asset set doc_hash = :h where asset_key = :k", {"h": h, "k": asset_key})
            reembedded = True
        except E.EmbeddingUnavailable:
            pass
    return {"ok": True, "asset_key": asset_key, "action": action, "reembedded": reembedded}
