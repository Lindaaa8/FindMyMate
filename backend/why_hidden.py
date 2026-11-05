"""Explain why one person does or doesn't appear in another person's Discover.

Usage (from the backend folder, with the app's database):
    python why_hidden.py "Isaac Liu" "Grace He"      # why is Grace (not) in Isaac's Discover?
    python why_hidden.py "Grace He" "Isaac Liu"      # and the other way round
"""
import os
import sys
from pathlib import Path

import ranking
from logic import Service, public_profile
from store import Store

BASE_DIR = Path(__file__).resolve().parent


def find(store, name):
    hits = [u for u in store.all_users() if (u["profile"].get("name") or "").strip().lower() == name.strip().lower()]
    if not hits:
        sys.exit(f"No user named {name!r}. Names: {', '.join(sorted(u['profile'].get('name') or '?' for u in store.all_users()))}")
    return hits[0]


def main(viewer_name, target_name):
    store = Store(os.environ.get("FYM_DB", str(BASE_DIR / "findyourmate.db")), seed_samples=False)
    svc = Service(store)
    viewer, target = find(store, viewer_name), find(store, target_name)
    vp, tp = viewer["profile"], target["profile"]
    print(f"Does {tp.get('name')} appear in {vp.get('name')}'s Discover?\n")

    liked_viewer = any(c["user_a"] == target["id"] for c in store.pending_for(viewer["id"]) if c["user_b"] == viewer["id"])
    checks = [
        (f"{tp.get('name')} is Single", svc.is_single(tp), f"status is {tp.get('marriageStatus')!r}"),
        (f"{tp.get('name')} saved their profile with gender and age (confirmed)", bool(tp.get("confirmed")),
         "open Me → ✏️ Edit Bio, fill gender + age, Save"),
        (f"{tp.get('name')} did “Verify it's me” (or liked {vp.get('name')})",
         bool(target["is_sample"] or tp.get("photoVerified") or liked_viewer), "not photo-verified"),
        (f"{tp.get('name')} isn't in an accepted connection with someone else",
         target["id"] not in store.active_user_ids() or
         (svc._other_id(store.active_connection(viewer["id"]), viewer["id"]) == target["id"]
          if store.active_connection(viewer["id"]) else False), "already chatting/dating someone"),
        (f"{vp.get('name')} hasn't pressed Not interested on {tp.get('name')}",
         target["id"] not in store.passes(viewer["id"]), "passed earlier (shown under Not interested)"),
    ]
    ok = True
    for label, passed, why in checks:
        ok &= passed
        print(f"  {'✓' if passed else '✗'} {label}" + ("" if passed else f"  — {why}"))

    missed = ranking.requirement_report(vp, {**public_profile(target), "ideal": tp.get("ideal", {})})
    print(f"\n  {vp.get('name')}'s must-match requirements:")
    if missed:
        ok = False
        for m in missed:
            print(f"  ✗ {m}")
    else:
        print("  ✓ all met")
    print(f"\n=> {'SHOWN' if ok else 'HIDDEN'}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
