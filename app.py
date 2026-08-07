"""
TAOL Course & Pax — Year-wise, Apex-wise  (public dashboard)

Geography is APEX (who owns the course), never where it ran. Years slice as:
  Calendar year  (Jan-Dec)      Financial year (Apr-Mar, labelled FY2025-26)
and splits them into the four report rows: Happiness / Rural / C&T / Other.

Everything the app shows about *what is counted* is on the page itself, under
"What we count, and how" — the bucket rules, the full list of course titles in
each bucket, and the titles that carry no tag. That section is the point: the
numbers are only as trustworthy as the grouping behind them, so the grouping is
published alongside them rather than living in a script.

Data is prebuilt by build_state_data.py into ./data/state_program.parquet. It has
to be prebuilt: the warehouse is IP-allowlisted to the office network and a
publicly hosted app cannot reach it.

Run:  streamlit run state_app.py
"""
import json
import os

import pandas as pd
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

st.set_page_config(page_title="TAOL Course & Pax — Year-wise, Apex-wise",
                   layout="wide")


@st.cache_data
def load():
    df = pd.read_parquet(os.path.join(DATA, "state_program.parquet"))
    with open(os.path.join(DATA, "state_meta.json")) as fh:
        meta = json.load(fh)
    return df, meta


df, meta = load()
BUCKETS = meta["buckets"]


def fy_key(fy):
    return int(fy[2:6])


# ---------------------------------------------------------------- sidebar
st.sidebar.header("Period")
basis = st.sidebar.radio(
    "Count years as", ["Calendar year", "Financial year"], key="basis",
    help="Calendar year is Jan-Dec. Financial year is Apr-Mar, labelled by its "
         "starting year: FY2025-26 runs Apr 2025 to Mar 2026.",
)
YCOL = "cy" if basis == "Calendar year" else "fy"

if YCOL == "cy":
    all_years = sorted(df["cy"].unique(), reverse=True)
    year_label = "Calendar year"
else:
    all_years = sorted(df["fy"].unique(), key=fy_key, reverse=True)
    year_label = "Financial year"

n_default = st.sidebar.slider("How many recent years?", 1, min(10, len(all_years)),
                              min(3, len(all_years)))
year_sel = st.sidebar.multiselect(year_label, all_years,
                                  default=all_years[:n_default])

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
m_from, m_to = st.sidebar.select_slider(
    "Months included", options=MONTHS, value=("Jan", "Dec"), key="months",
    help="Narrow every year to the same window, so a part-year is compared "
         "against the same part of earlier years. The circulated Karnataka "
         "report is Jan-Jun.")
M_LO, M_HI = MONTHS.index(m_from) + 1, MONTHS.index(m_to) + 1
if M_LO > M_HI:
    st.sidebar.warning("Start month is after the end month; using the full year.")
    M_LO, M_HI = 1, 12

st.sidebar.header("Where")
# Geography is apex_name -- who OWNS the course -- and only that. It is the basis
# the state reports use. course_event_state (where the course physically ran) is
# still in the parquet and available as the cross-filter below, but it is
# deliberately not selectable as the headline basis: having two answers to
# "how big is Karnataka" was the thing causing arguments.
GEO = "apex"
geo_all = meta["apexes"]
geo_default = [g for g in meta["default_apexes"] if g in geo_all]
state_sel = st.sidebar.multiselect("Apex", geo_all, default=geo_default,
                                   help="The apex that owns the course.")

st.sidebar.header("Org")
org_sel = st.sidebar.multiselect(
    "Organisation", meta["orgs"], default=meta["default_orgs"],
    help="TAOL is The Art of Living. The others (VVMVP, SSIAST, VVKI) are "
         "sister orgs and are off by default — together about 1% of pax in "
         "these states.",
)
if not org_sel:
    st.warning("Pick at least one organisation.")
    st.stop()

# Optional cross-filter on where the course physically ran. Left alone it changes
# nothing; it is there for "of our courses, which ran outside the state".
OTHER = "state"
apex_pool = sorted(df[df[GEO].isin(state_sel) & df["org"].isin(org_sel)][OTHER]
                   .unique()) if state_sel else []
apex_sel = st.sidebar.multiselect(
    "Held in state", apex_pool, default=apex_pool,
    help="Cross-filter. Everything is on by default; the totals are the same "
         "as leaving it alone.",
)

st.sidebar.header("Programs")
# Two groupings. Course tag is the default and the one to quote. Course desk is
# kept because it is genuinely informative -- it is how the desks themselves are
# organised, and it is what first showed that the circulated report was cut on
# apex -- but it misfiles several programs, so selecting it raises a warning
# rather than silently changing every number on the page.
group_basis = st.sidebar.radio(
    "Group programs by", ["Course desk (recommended)", "Course tag (read the note)"],
    key="grouping",
    help="Course desk uses desk_name -- which desk owns the program. It is the "
         "default because it gets YLTP, Yes! and the youth programs right, where "
         "the website tag file does not. Course tag is kept for comparison.")
BCOL = "desk_bucket" if group_basis.startswith("Course desk") else "bucket"

drop_inst = st.sidebar.checkbox(
    "Exclude school / institutional programs", value=False,
    help="Course category 'Institutional Course' -- school and corporate "
         "batches. Few programs, very large pax (a School Utkarsha Yoga averages "
         "~70 participants against ~8 for the public version), so they dominate "
         "the C&T row.")

bucket_sel = st.sidebar.multiselect("Program type", BUCKETS, default=BUCKETS)
st.sidebar.caption("Unticking a type removes it from the totals too — the Total "
                   "row is always the sum of what is shown.")

st.sidebar.divider()
st.sidebar.caption(f"Data built {meta['built_on']} from the warehouse "
                   f"(`view_event`), latest month {meta['asof']}. "
                   f"Variant: **{meta['variant']}**.")

if not year_sel or not state_sel or not bucket_sel or not apex_sel:
    st.warning("Pick at least one year, state, apex and program type.")
    st.stop()

# ---------------------------------------------------------------- filter
scope = df[df[YCOL].isin(year_sel) & df[GEO].isin(state_sel)
           & df["org"].isin(org_sel) & df[OTHER].isin(apex_sel)
           & df["month"].dt.month.between(M_LO, M_HI)
           & df[BCOL].isin(bucket_sel)]
if drop_inst:
    scope = scope[~scope["institutional"]]

years = (sorted(year_sel, key=fy_key) if YCOL == "fy" else sorted(year_sel))
buckets = [b for b in BUCKETS if b in bucket_sel]

# ---------------------------------------------------------------- header
st.title("TAOL Course & Pax")
st.markdown("##### Year-wise, apex-wise — courses and participants by program type")
st.caption(
    f"**{', '.join(state_sel)} apex** — org **{', '.join(org_sel)}** — "
    f"by {basis.lower()}"
    + ("" if (M_LO, M_HI) == (1, 12) else f" — **{m_from}-{m_to} only**")
    + ("" if not drop_inst else " — **school/institutional excluded**")
    + ("" if BCOL == "bucket" else " — **grouped by DESK, not by tag**")
    + ("" if len(apex_sel) == len(apex_pool)
       else f" — limited to **{', '.join(apex_sel)}**") + ". "
    "*No. of Programs* is a count of distinct course events; "
    "*No. of Participants* is new participants (`new_pax`). "
    "Full definitions at the bottom of the page."
)

if BCOL == "bucket":
    st.warning(
        "**You are grouping by course tag, not by course desk.** The tag file is "
        "the website's course-title groupings, and on this data it misfiles "
        "several programs that the desks get right:\n\n"
        "- **YLTP**, **WLTP** and **OWLTP** fall into *Other* instead of *Rural*, "
        "though they are exactly the rural youth programs.\n"
        "- **Yes!** falls into *Other* instead of *C&T*, though it is the teen "
        "program.\n"
        "- **Happiness Program for Youth** and **OMBW for Youth** are counted as "
        "*Happiness*, though the YES+ desk runs them as youth programs.\n\n"
        "The two groupings disagree on **58 of 366** course titles. Quote the "
        "desk grouping unless you have a specific reason not to.",
        icon=":material/warning:")
    diff = (scope[scope["bucket"] != scope["desk_bucket"]]
            .groupby(["program", "bucket", "desk_bucket"])[["programs", "pax"]]
            .sum().reset_index().sort_values("programs", ascending=False))
    if len(diff):
        with st.expander(f"The {len(diff)} titles this moves, in your current "
                         f"selection — {int(diff['programs'].sum()):,} programs, "
                         f"{int(diff['pax'].sum()):,} participants"):
            st.dataframe(
                diff.rename(columns={"program": "Course title",
                                     "bucket": "By tag (standard)",
                                     "desk_bucket": "By desk (now)",
                                     "programs": "Programs", "pax": "Participants"}),
                width="stretch", hide_index=True,
                column_config={
                    "Programs": st.column_config.NumberColumn(format="%d"),
                    "Participants": st.column_config.NumberColumn(format="%d")})

# Per-bucket course-title picker. The buckets are our grouping, not gospel -- if
# someone disagrees that, say, Rural ArtExcel belongs under Rural, they can untick
# it here and every number on the page moves with them.
title_pool = {
    b: (scope[scope[BCOL] == b].groupby("program")["programs"].sum()
        .sort_values(ascending=False).index.tolist())
    for b in buckets
}
# What the user unticked is remembered as an EXCLUSION list, not as a selection.
# The option pool shrinks and grows as the sidebar changes, and a stored selection
# would silently lose titles that momentarily dropped out of scope and never get
# them back. An exclusion set survives that.
if "excluded" not in st.session_state:
    # Seed from the build's default-excluded list: titles that belong to a bucket
    # but that most people do not mean by it. They are in the dropdown, unticked.
    seed = set(meta.get("default_excluded", []))
    st.session_state["excluded"] = {}
    for _b in BUCKETS:
        _in_b = set(df.loc[df[BCOL] == _b, "program"]) & seed
        if _in_b:
            st.session_state["excluded"][_b] = _in_b
    st.session_state["default_excluded_seeded"] = True


def _sync(bucket, key, opts):
    """Runs on widget change, before the rerun, so `excluded` is never stale."""
    st.session_state["excluded"][bucket] = set(opts) - set(st.session_state[key])


title_sel = {}
with st.expander("Fine-tune what each program type contains "
                 "— untick anything you don't want counted"):
    st.caption("These lists are the grouping the report uses. Everything is "
               "ticked by default; untick a course and it leaves its row, the "
               "Total, and the tag split below. Only courses that actually ran "
               "in the current selection are listed.")
    cols = st.columns(min(2, max(1, len(buckets))))
    for i, b in enumerate(buckets):
        opts = title_pool[b]
        key = f"titles::{b}"
        excl = st.session_state["excluded"].get(b, set())
        st.session_state[key] = [t for t in opts if t not in excl]
        with cols[i % len(cols)]:
            title_sel[b] = st.multiselect(
                f"{b} — {len(opts)} course titles", opts, key=key,
                on_change=_sync, args=(b, key, opts))

keep = set().union(*title_sel.values()) if title_sel else set()
f = scope[scope["program"].isin(keep)]

DEFAULT_EXCL = set(meta.get("default_excluded", []))
off = {b: [t for t in title_pool[b] if t not in title_sel[b]] for b in buckets}
off = {b: v for b, v in off.items() if v}
non_default = {b: [t for t in v if t not in DEFAULT_EXCL] for b, v in off.items()}
non_default = {b: v for b, v in non_default.items() if v}
if non_default:
    st.warning(
        "**Non-standard selection — these are not the numbers to circulate.** "
        + "; ".join(f"{b}: {', '.join(v[:4])}"
                    + (f" and {len(v) - 4} more" if len(v) > 4 else "")
                    for b, v in non_default.items()) + " excluded by hand.",
        icon=":material/filter_alt:")
elif off:
    st.caption(
        "Excluded by default (tick them in the panel above to include): "
        + "; ".join(f"**{b}** — {', '.join(v)}" for b, v in off.items())
        + ". These belong to their desk, but are not what people usually mean "
          "by that program type.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Programs", f"{int(f['programs'].sum()):,}")
c2.metric("Participants", f"{int(f['pax'].sum()):,}")
c3.metric("Apexes", f"{f[GEO].nunique():,}")
c4.metric("Course titles", f"{f['program'].nunique():,}")

if YCOL == "cy" and max(years) == df["cy"].max():
    st.info(f"**{max(years)} is part-year** — data runs to {meta['asof']}. "
            "Don't read it as a full-year fall.", icon=":material/info:")

st.divider()


# ---------------------------------------------------------------- the table
def report_table(frame):
    """The screenshot's layout: bucket rows, Programs then Participants by year."""
    prog = (frame.groupby([BCOL, YCOL])["programs"].sum()
            .unstack(YCOL).reindex(index=buckets, columns=years).fillna(0).astype(int))
    pax = (frame.groupby([BCOL, YCOL])["pax"].sum()
           .unstack(YCOL).reindex(index=buckets, columns=years).fillna(0).astype(int))
    prog.loc["Total Programs"] = prog.sum()
    pax.loc["Total Programs"] = pax.sum()
    out = pd.concat(
        [prog.rename(columns=lambda y: f"Programs {y}"),
         pax.rename(columns=lambda y: f"Participants {y}")], axis=1)
    return out.reset_index().rename(columns={BCOL: "Program Type"})


def show(frame, key):
    t = report_table(frame)
    st.dataframe(
        t, width="stretch", hide_index=True,
        column_config={c: st.column_config.NumberColumn(format="%d")
                       for c in t.columns if c != "Program Type"},
    )
    st.download_button("Download CSV", t.to_csv(index=False).encode(),
                       file_name=f"taol_course_pax_{key}.csv",
                       mime="text/csv", key=f"dl_{key}")


# One section per apex, stacked rather than tabbed: the whole report should be
# readable in one scroll and screenshot-able section by section, without anyone
# having to remember to click through the other three tabs.
if len(state_sel) > 1:
    st.subheader("All apexes together")
    show(f, "all")
    st.divider()

for i, state in enumerate(state_sel):
    sub = f[f[GEO] == state]
    st.subheader(f"{state}")
    st.caption(f"{int(sub['programs'].sum()):,} programs, "
               f"{int(sub['pax'].sum()):,} participants across the selected years.")
    show(sub, state.lower().replace(" ", "_"))
    if i < len(state_sel) - 1:
        st.divider()

st.divider()

# ---------------------------------------------------------------- tag split
st.subheader("Tag-wise split")
st.caption("The same numbers one level down — every grouping tag inside each "
           "program type, so you can see what is driving a row.")

tag_metric = st.radio("Show", ["pax", "programs"], horizontal=True, key="tagmetric",
                      format_func=lambda m: "Participants" if m == "pax" else "Programs")
tag = (f.groupby([BCOL, "tag", YCOL])[tag_metric].sum()
       .unstack(YCOL).reindex(columns=years).fillna(0).astype(int).reset_index())
tag.insert(2, "TOTAL", tag[years].sum(axis=1))
tag[BCOL] = pd.Categorical(tag[BCOL], categories=buckets, ordered=True)
tag = tag.sort_values([BCOL, "TOTAL"], ascending=[True, False])
tag = tag.rename(columns={BCOL: "Program Type", "tag": "Tag"})
tag.columns = [str(c) for c in tag.columns]
st.dataframe(
    tag, width="stretch", hide_index=True,
    column_config={c: st.column_config.NumberColumn(format="%d")
                   for c in tag.columns if c not in ("Program Type", "Tag")},
)
st.download_button("Download tag split (CSV)", tag.to_csv(index=False).encode(),
                   file_name=f"tag_split_{tag_metric}.csv", mime="text/csv")

st.divider()

# ---------------------------------------------------------------- provenance
st.subheader("What we count, and how")
st.markdown(
    f"""
Source: the analytics warehouse view `view_event`, built {meta['built_on']},
covering course events up to **{meta['asof']}**.

| | |
|---|---|
| **No. of Programs** | `COUNT(DISTINCT global_event_id)` — one course event counts once, however many teachers taught it. |
| **No. of Participants** | `SUM(new_pax)` — new participants. Repeat participants (`repeat_pax`) are **excluded**; they are a rounding error in these states. |
| **Apex** | `apex_name` — who **owns** the course. The default basis, and the one the state reports use. Apex Tamil Nadu also owns courses held in Pondicherry and the Andamans. |
| **State** | `course_event_state` — where the course physically **ran**. Not the basis for any number here; available only as the "Held in state" cross-filter. Counting Karnataka that way roughly doubles its pax, because Ashram Apex courses held in Karnataka are very large (~28 pax each against ~4.8). |
| **Org** | `org_id`. Currently showing **{', '.join(org_sel)}**. TAOL is The Art of Living; VVMVP / SSIAST / VVKI are sister orgs, off by default. |
| **Year** | From the course **start date**. Calendar = Jan–Dec; Financial = Apr–Mar. |

**Rows excluded:** {', '.join(meta['filters']) if meta['filters'] else 'none — raw build'}.
These are the same rules the apex / trust / category reports use, so the totals agree with them.
""")

st.markdown("**How a course lands in a program type**")
for b in BUCKETS:
    st.markdown(f"- **{b}** — {meta['bucket_rules'][b]}")
st.caption("Rules are applied in that order, top down: the first one that matches wins.")

st.markdown("**Every course title we consider, by program type**")
try:
    with open(os.path.join(DATA, "program_bucket_map.csv"), "rb") as fh:
        st.download_button(
            "Download the full course-title → program-type map (CSV)", fh.read(),
            file_name="program_bucket_map.csv", mime="text/csv",
            help="Every name_en_gb in the data with its tag, its desk, and the "
                 "program type it falls under on both groupings. This is the "
                 "whole classification, in one file.")
except FileNotFoundError:
    pass
st.caption("Counts below are for the states and years selected in the sidebar. "
           "A title with 0 here simply did not run in that selection.")

titles = (f.groupby([BCOL, "tag", "program"])[["programs", "pax"]].sum()
          .reset_index().sort_values("programs", ascending=False))
for b in buckets:
    sub = titles[titles[BCOL] == b]
    with st.expander(f"{b} — {len(sub):,} course titles, "
                     f"{int(sub['programs'].sum()):,} programs, "
                     f"{int(sub['pax'].sum()):,} participants"):
        view = sub[["program", "tag", "programs", "pax"]].rename(columns={
            "program": "Course title", "tag": "Tag",
            "programs": "Programs", "pax": "Participants"})
        st.dataframe(view, width="stretch", hide_index=True,
                     column_config={
                         "Programs": st.column_config.NumberColumn(format="%d"),
                         "Participants": st.column_config.NumberColumn(format="%d")})

untag = (f[f["untagged"]].groupby("program")[["programs", "pax"]].sum()
         .reset_index().sort_values("programs", ascending=False))
if len(untag):
    st.warning(
        f"**{len(untag)} course titles have no entry in the grouping file** and "
        "therefore fall into *Other Programs* by default. They are counted in the "
        "totals — they are just not classified. Worth tagging.",
        icon=":material/warning:")
    st.dataframe(
        untag.rename(columns={"program": "Untagged course title",
                              "programs": "Programs", "pax": "Participants"}),
        width="stretch", hide_index=True,
        column_config={"Programs": st.column_config.NumberColumn(format="%d"),
                       "Participants": st.column_config.NumberColumn(format="%d")})

st.caption("Course titles are `name_en_gb` exactly as the warehouse stores them — "
           "the same string the tag file joins on and the app displays, with no "
           "derived or fuzzy matching. Groupings come from "
           "`website_grouping_tags.csv` (the website's own title → tag mapping) "
           "and from `desk_name`. To move a course between program types, change "
           "its tag there and rebuild.")
