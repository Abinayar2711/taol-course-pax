"""
Build the state Program Performance dataset from the warehouse.

Feeds state_app.py (the public dashboard). The public app can NEVER query the
warehouse -- it is IP-allowlisted to the office network -- so everything it needs
is baked into one parquet here and committed, exactly like build_from_warehouse.py
does for the teacher dashboard.

Grain: one row per (state, apex, org, month, program). Month, not year, is
deliberate: it is what lets the app slice by calendar year AND financial year off
the same file without a rebuild. org_id and apex_name are carried because the
report the boss circulated is a narrower scope than "all events held in the state"
and those are the two dimensions that can narrow it.

Metrics come off view_event only:
    programs = COUNT(DISTINCT global_event_id)
    pax      = SUM(new_pax)
No join to view_course_teacher, so there is no pax fan-out across teachers and the
refresh_type='D' soft-delete defect does not apply (that column is on the teacher
view, not this one). Cross-checked against the teacher-participants basis on
Karnataka: agrees to within 0.15%.

Filters are the published "parity" rules: CRF submitted, not cancelled. --raw
drops them, to show what they cost.

Usage:  python3 build_state_data.py [--raw] [--all-states]
"""
import argparse
import json
import os
import re
from datetime import date

import pandas as pd
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
GROUPING = os.path.join(HERE, "website_grouping_tags.csv")
DB = dict(host="65.0.186.33", port=5432, dbname="analytics_dev", user="aolt_user")

# The four the boss asked for. --all-states widens it; the app's default stays these.
STATES = ["Karnataka", "Telangana", "Andhra Pradesh", "Tamil Nadu"]
# The apexes of the same name. Rows are kept if EITHER matches, so both bases are
# complete: apex Tamil Nadu owns courses held in Pondicherry and the Andamans, and
# Ashram Apex owns courses held in Karnataka.
APEXES = STATES

# Which apexes the dashboard actually shows. Tamil Nadu is held back for now
# (7 Aug 2026) -- its data is still built and still in the parquet, so putting it
# back is this one line plus a rebuild, and does not need the warehouse.
HIDDEN_APEXES = ["Tamil Nadu"]
SHOW_APEXES = [a for a in APEXES if a not in HIDDEN_APEXES]

# The app opens on TAOL only. The others (VVMVP, SSIAST, VVKI...) are still in the
# parquet so they can be ticked back on -- in these four states they are ~1% of pax.
DEFAULT_ORGS = ["TAOL"]

# ---------------------------------------------------------------- buckets
# The four rows of the Program Performance Report, expressed in the website
# grouping file's own tag vocabulary. Nothing is invented here.
CT_TAGS = ["C&T-PY-Institutional", "C&T-PY-NonInstitutional", "C&T-PY-Special",
           "C&T-PY2-NonInstitutional", "C&T-UY-MY-Institutional",
           "C&T-UY-MY-NonInstitutional", "KYC-KYT", "UY_MY Upgrade", "IP repeaters"]
HP_TAGS = ["HP"]

BUCKETS = ["Happiness Programs", "Rural Programs", "C&T Programs", "Other Programs"]

# The same four rows, cut by course desk instead of by tag. Every other desk
# (Sahaj, Sri Sri Yoga, Part 2 & DSN, YES+, TTP, VTP, Pran, Prison Smart,
# Eternity, Wellness, Spine) falls to Other.
DESK_BUCKETS = {
    "Happiness Program": "Happiness Programs",
    "YLTP  DESK": "Rural Programs",          # note the double space, as stored
    "Children and Teens Desk": "C&T Programs",
}

RURAL = re.compile(r"\brural\b", re.I)

BUCKET_RULES = {
    "Happiness Programs": "Programs owned by the Happiness Program desk.",
    "Rural Programs": "Programs owned by the YLTP desk.",
    "C&T Programs": "Programs owned by the Children and Teens desk.",
    "Other Programs": (
        "Every other desk — Sahaj, Sri Sri Yoga, Part 2 & DSN, YES+, TTP, VTP, "
        "Pran, Prison Smart, Eternity, Wellness, Spine — plus any course "
        "unticked under the three named types, so the Total stays complete."),
}

# What each program type counts BY DEFAULT. Everything else in the bucket is
# still listed in the app's dropdown, just unticked, so the opening number is the
# one people mean and anything extra has to be asked for. Decided with Abinaya,
# 7 Aug 2026.
#
# Happiness and Rural are whitelists -- only these titles start ticked.
DEFAULT_SELECTED = {
    "Happiness Programs": [
        "Happiness Program (3 Days)",
        "Online Meditation and Breath Workshop",
        "Happiness Program",
    ],
    "Rural Programs": [
        "Rural Happiness Program",
        "YLTP",
    ],
}

# C&T is a rule instead of a list -- the bucket has ~120 titles. Off by default:
#   school / govt / ssrvm  the school batches. This cannot key off
#                          course_category, which flags Art Excel, Utkarsha Yoga
#                          and Yes! as institutional too, so it keys off the
#                          title. SSRVM is an Art of Living school chain.
#   kyc / kyt              Know Your Child and Know Your Teen are courses for
#                          parents, not children's programs.
#   deaf / blind           the special-needs batches.
#   smart                  Smart Excel and SMART YES!.
CT_OFF = re.compile(
    r"school|govt|ssrvm|\bkyc\b|\bkyt\b|know your (child|teen)"
    r"|deaf|blind|smart", re.I)
RULE_EXCLUDED = {"C&T Programs": lambda title: bool(CT_OFF.search(title))}

# "Other Programs" has no default exclusions: everything in it starts ticked. It
# is also where the app puts the titles listed above -- unticking a course moves
# it to Other rather than dropping it, so the Total is the apex's real activity.


def default_excluded_titles(df):
    """Per bucket, the titles that start UNTICKED in the app."""
    out = {}
    for bucket, keep in DEFAULT_SELECTED.items():
        titles = set(df.loc[df["desk_bucket"] == bucket, "program"])
        off = sorted(titles - set(keep))
        if off:
            out[bucket] = off
    for bucket, rule in RULE_EXCLUDED.items():
        titles = set(df.loc[df["desk_bucket"] == bucket, "program"])
        off = sorted(t for t in titles if rule(t))
        if off:
            out[bucket] = off
    return out


def bucket_of(program, tag):
    if RURAL.search(program or ""):
        return "Rural Programs"
    if tag in HP_TAGS:
        return "Happiness Programs"
    if tag in CT_TAGS:
        return "C&T Programs"
    return "Other Programs"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="store_true",
                    help="drop the CRF / cancelled filters (diagnostic)")
    ap.add_argument("--all-states", action="store_true",
                    help="build every state, not just the four")
    args = ap.parse_args()

    filt = "" if args.raw else (
        "  AND e.crf_consider IS NOT NULL\n"
        "  AND COALESCE(e.event_status, '') <> 'Cancelled'")
    where_state = ("e.course_event_state IS NOT NULL" if args.all_states
                   else "(e.course_event_state IN %(states)s "
                        "OR e.apex_name IN %(apexes)s)")

    sql = f"""
SELECT COALESCE(e.course_event_state, '(not set)')              AS state,
       COALESCE(e.org_id, '(none)')                             AS org,
       COALESCE(e.apex_name, '(none)')                          AS apex,
       COALESCE(e.desk_name, '(none)')                          AS desk,
       COALESCE(e.course_category, '(none)')                    AS course_category,
       DATE_TRUNC('month', e.course_event_start_date)::date     AS month,
       TRIM(e.name_en_gb)                                       AS program,
       COUNT(DISTINCT e.global_event_id)                        AS programs,
       COALESCE(SUM(e.new_pax), 0)                              AS pax,
       COALESCE(SUM(e.repeat_pax), 0)                           AS repeat_pax
FROM view_event e
WHERE {where_state}
  AND e.course_event_start_date IS NOT NULL
{filt}
GROUP BY 1, 2, 3, 4, 5, 6, 7
"""
    print(f"connecting to {DB['dbname']}@{DB['host']} ...", flush=True)
    conn = psycopg2.connect(connect_timeout=20,
                            application_name="taol-state-build", **DB)
    try:
        params = (None if args.all_states else
                  {"states": tuple(STATES), "apexes": tuple(APEXES)})
        df = pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()
    print(f"  {len(df):,} (state, month, program) rows")

    g = pd.read_csv(GROUPING)
    tagmap = dict(zip(g["name_en_gb"].astype(str).str.strip(), g["tag"]))
    df["tag"] = df["program"].map(tagmap)
    df["untagged"] = df["tag"].isna()
    df["tag"] = df["tag"].fillna("(untagged)")
    df["bucket"] = [bucket_of(p, t) for p, t in zip(df["program"], df["tag"])]
    # Second, independent grouping: the course desk that owns the program. Cheaper
    # to explain to a desk head than a tag list, and it is how the circulated
    # Karnataka report appears to be cut.
    df["desk_bucket"] = df["desk"].map(DESK_BUCKETS).fillna("Other Programs")

    df["month"] = pd.to_datetime(df["month"])
    df["cy"] = df["month"].dt.year
    # Financial year: April-March, labelled FY2025-26.
    fy_start = df["month"].dt.year.where(df["month"].dt.month >= 4,
                                         df["month"].dt.year - 1)
    df["fy"] = "FY" + fy_start.astype(str) + "-" + ((fy_start + 1) % 100).map("{:02d}".format)

    for c in ("programs", "pax", "repeat_pax"):
        df[c] = df[c].astype(int)

    os.makedirs(DATA, exist_ok=True)
    out = os.path.join(DATA, "state_program.parquet")
    # School / corporate courses. They are few but carry huge pax (a School
    # Utkarsha Yoga averages ~70 participants against ~8 for the public version),
    # so they distort any per-program average. The app can exclude them.
    df["institutional"] = df["course_category"] == "Institutional Course"
    cols = ["state", "org", "apex", "desk", "institutional", "month", "cy", "fy", "bucket",
            "desk_bucket", "tag", "program", "untagged", "programs", "pax",
            "repeat_pax"]
    df[cols].to_parquet(out, index=False)
    print(f"  wrote {out}  {df.shape}")

    # One row per course title, so "what counts as Happiness?" is answerable by
    # opening a file rather than by reading this script. name_en_gb is the key --
    # the same string the warehouse stores, the tag file joins on, and the app
    # displays. No derived or fuzzy names anywhere.
    title_map = (df.groupby(["program", "tag", "desk", "bucket", "desk_bucket",
                             "institutional"], dropna=False)
                 [["programs", "pax"]].sum().reset_index()
                 .rename(columns={"program": "name_en_gb",
                                  "bucket": "bucket_by_tag",
                                  "desk": "desk_name",
                                  "desk_bucket": "bucket_by_desk",
                                  "programs": "programs_all_years",
                                  "pax": "pax_all_years"})
                 .sort_values(["bucket_by_tag", "programs_all_years"],
                              ascending=[True, False]))
    tm = os.path.join(DATA, "program_bucket_map.csv")
    title_map.to_csv(tm, index=False)
    print(f"  wrote {tm}  ({len(title_map):,} course titles)")

    meta = {
        "built_on": date.today().isoformat(),
        "asof": df["month"].max().strftime("%Y-%m"),
        "variant": "raw (no CRF/cancelled filter)" if args.raw else "parity",
        "states": sorted(df["state"].unique().tolist()),
        "default_states": STATES,
        "apexes": sorted(df["apex"].unique().tolist()),
        "default_apexes": SHOW_APEXES,
        "orgs": sorted(df["org"].unique().tolist()),
        "default_orgs": [o for o in DEFAULT_ORGS if o in set(df["org"])],
        "buckets": BUCKETS,
        "bucket_rules": BUCKET_RULES,
        "desk_buckets": DESK_BUCKETS,
        "default_excluded_by_bucket": default_excluded_titles(df),
        "default_selected": DEFAULT_SELECTED,
        "desks": sorted(df["desk"].unique().tolist()),
        "ct_tags": CT_TAGS,
        "filters": ([] if args.raw else
                    ["CRF submitted (crf_consider IS NOT NULL)",
                     "event status is not 'Cancelled'"]),
    }
    with open(os.path.join(DATA, "state_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    print(f"  wrote {DATA}/state_meta.json")

    recent = df[df["cy"] >= df["cy"].max() - 2]
    print("\n=== programs / pax by state and calendar year ===")
    print(recent.groupby(["state", "cy"])[["programs", "pax"]].sum().to_string())
    n_untagged = df.loc[df["untagged"], "program"].nunique()
    print(f"\n{n_untagged} course titles carry no tag in website_grouping_tags.csv "
          f"(they land in Other Programs; the app lists them).")


if __name__ == "__main__":
    main()
