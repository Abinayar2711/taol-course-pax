"""
TAOL Course & Pax — Year-wise, Apex-wise

Four apex sections: Karnataka, Telangana, Andhra Pradesh, Tamil Nadu. Each shows
programs and participants by program type, per year.

Fixed by decision, so they are not on screen as choices:
  org      TAOL
  geography apex_name (who owns the course), never course_event_state
  grouping  desk_name (the desk that owns the program)

Each program type label is a dropdown of its course names (name_en_gb). Untick a
course and that section's numbers move.

Data is prebuilt by build_state_data.py into ./data/. The warehouse is
IP-allowlisted to the office network, so a hosted app can never query it.
"""
import json
import os

import pandas as pd
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

ORG = "TAOL"
GEO = "apex"
BCOL = "desk_bucket"

st.set_page_config(page_title="TAOL Course & Pax — Year-wise, Apex-wise",
                   layout="wide")

# Blue, low-contrast. Nothing on this page is an error, so nothing is red.
st.markdown("""
<style>
:root {
  --brand:      #1f5fa9;
  --brand-soft: #eaf1f9;
  --muted:      #6b7a8c;
  --rule:       rgba(31,95,169,.16);
}
@media (prefers-color-scheme: dark) {
  :root { --brand:#7db3ea; --brand-soft:rgba(125,179,234,.10); --muted:#93a4b6;
          --rule:rgba(125,179,234,.22); }
}
.apex-title  { color:var(--brand); font-size:1.35rem; font-weight:700;
               margin:.6rem 0 .1rem; }
.apex-sub    { color:var(--muted); font-size:.82rem; margin:0 0 .5rem; }
.grouphead   { color:var(--muted); font-size:.72rem; font-weight:600;
               letter-spacing:.08em; text-transform:uppercase; text-align:center;
               padding:.15rem 0; background:var(--brand-soft); border-radius:4px; }
.colhead     { color:var(--muted); font-size:.78rem; font-weight:600;
               text-align:right; padding:.3rem 0; }
.cell        { text-align:right; font-variant-numeric:tabular-nums;
               padding:.34rem 0; }
.cell-total  { text-align:right; font-variant-numeric:tabular-nums;
               font-weight:700; color:var(--brand); padding:.4rem 0; }
.rowlabel    { padding:.34rem 0; }
.rowlabel-total { padding:.4rem 0; font-weight:700; color:var(--brand); }
.rule        { border-top:1px solid var(--rule); margin:.2rem 0 .1rem; }
div[data-testid="stPopover"] button { border:0; background:transparent;
    padding:.1rem 0; font-weight:400; text-align:left; justify-content:flex-start; }
div[data-testid="stPopover"] button:hover { color:var(--brand); }

/* Selected-course chips, and the radio / checkbox marks. Streamlit themes these
   from primaryColor (set to the same blue in .streamlit/config.toml); these
   rules are the belt to that braces, since the chip markup is BaseWeb's. */
span[data-baseweb="tag"] {
  background-color: var(--brand) !important;
  border-color: var(--brand) !important;
  color: #fff !important;
}
span[data-baseweb="tag"] svg { fill:#fff !important; }
div[data-baseweb="select"] > div:focus-within {
  border-color: var(--brand) !important;
  box-shadow: 0 0 0 1px var(--brand) !important;
}
li[role="option"][aria-selected="true"] { background-color: var(--brand-soft) !important; }
</style>
""", unsafe_allow_html=True)


PARQUET = os.path.join(DATA, "state_program.parquet")
META = os.path.join(DATA, "state_meta.json")


def _sig(path):
    st_ = os.stat(path)
    return (st_.st_mtime_ns, st_.st_size)


@st.cache_data
def load(sig):
    """`sig` is the files' (mtime, size). It is unused inside, and that is the
    point: st.cache_data keys on the arguments, not on file contents, so without
    it a server that was already running keeps serving the previous build's meta
    after a data refresh -- which silently ticked every course back on."""
    df = pd.read_parquet(PARQUET)
    with open(META) as fh:
        meta = json.load(fh)
    return df, meta


df, meta = load((_sig(PARQUET), _sig(META)))
df = df[df["org"] == ORG]
BUCKETS = meta["buckets"]
APEXES = [a for a in meta["default_apexes"] if a in set(df[GEO])]


def fy_key(fy):
    return int(fy[2:6])


# ---------------------------------------------------------------- sidebar
basis = st.sidebar.radio("Year", ["Calendar year", "Financial year"], key="basis")
YCOL = "cy" if basis == "Calendar year" else "fy"
years_all = (sorted(df["fy"].unique(), key=fy_key, reverse=True) if YCOL == "fy"
             else sorted(df["cy"].unique(), reverse=True))
year_sel = st.sidebar.multiselect(basis, years_all, default=years_all[:3])

held_all = sorted(df["state"].unique())
held_sel = st.sidebar.multiselect(
    "Course event state", held_all, default=held_all,
    help="course_event_state -- where the course physically ran. The rows above "
         "are by apex (who owns the course), so this narrows to the courses an "
         "apex ran in a given state.")

if st.sidebar.button("Reset course selection"):
    st.session_state.pop("excl", None)
    st.session_state.pop("excl_version", None)
    for k in [k for k in st.session_state if str(k).startswith("pick::")]:
        del st.session_state[k]
    st.rerun()

st.sidebar.caption(f"Warehouse build {meta['built_on']} · to {meta['asof']} · "
                   f"org {ORG} · apex-wise · by course desk")

if not year_sel or not held_sel:
    st.info("Pick at least one year and one state.")
    st.stop()

years = sorted(year_sel, key=fy_key) if YCOL == "fy" else sorted(year_sel)
scope = df[df[YCOL].isin(year_sel) & df["state"].isin(held_sel)]

# Course exclusions are remembered per apex and per program type, as an exclusion
# set rather than a selection, so a title that momentarily leaves the year scope
# comes back when it returns.
DEFAULTS = meta.get("default_excluded_by_bucket")
if DEFAULTS is None:
    st.info("This build has no default course selection — every course is "
            "counted. Rebuild with build_state_data.py to restore it.")
    DEFAULTS = {}

# Reseed whenever the build changes, so an open browser session does not keep a
# previous build's defaults (or lack of them).
seed_version = f"{meta['built_on']}::" + "::".join(
    f"{b}:{len(v)}" for b, v in sorted(DEFAULTS.items()))
if st.session_state.get("excl_version") != seed_version:
    st.session_state.pop("excl", None)
    for k in [k for k in st.session_state if str(k).startswith("pick::")]:
        del st.session_state[k]
    st.session_state["excl_version"] = seed_version

if "excl" not in st.session_state:
    seed = {b: set(v) for b, v in DEFAULTS.items()}
    st.session_state["excl"] = {}
    for a in APEXES:
        for b in BUCKETS:
            titles = set(df.loc[(df[GEO] == a) & (df[BCOL] == b), "program"])
            off = titles & seed.get(b, set())
            if off:
                st.session_state["excl"][(a, b)] = off


def _sync(apex, bucket, key, opts):
    st.session_state["excl"][(apex, bucket)] = set(opts) - set(st.session_state[key])


# ---------------------------------------------------------------- header
st.markdown("<div class='apex-title'>TAOL Course &amp; Pax</div>"
            "<div class='apex-sub'>Year-wise, apex-wise. Click a program type to "
            "choose which courses it counts.</div>", unsafe_allow_html=True)

WIDTHS = [2.6] + [1] * (len(years) * 2)


def header_row():
    top = st.columns([2.6, len(years), len(years)])
    top[1].markdown("<div class='grouphead'>No. of Programs</div>",
                    unsafe_allow_html=True)
    top[2].markdown("<div class='grouphead'>No. of Participants</div>",
                    unsafe_allow_html=True)
    cols = st.columns(WIDTHS)
    cols[0].markdown("<div class='colhead' style='text-align:left'>Program Type</div>",
                     unsafe_allow_html=True)
    for i, y in enumerate(years * 2):
        cols[i + 1].markdown(f"<div class='colhead'>{y}</div>",
                             unsafe_allow_html=True)


def section(apex):
    sub = scope[scope[GEO] == apex]
    st.markdown(f"<div class='apex-title'>{apex}</div>", unsafe_allow_html=True)
    header_row()
    st.markdown("<div class='rule'></div>", unsafe_allow_html=True)

    totals = {"programs": [0] * len(years), "pax": [0] * len(years)}
    rows = []
    for b in BUCKETS:
        pool = (sub[sub[BCOL] == b].groupby("program")["programs"].sum()
                .sort_values(ascending=False).index.tolist())
        key = f"pick::{apex}::{b}"
        excl = st.session_state["excl"].get((apex, b), set())
        st.session_state[key] = [t for t in pool if t not in excl]

        cols = st.columns(WIDTHS)
        with cols[0]:
            n_off = len(pool) - len(st.session_state[key])
            label = f"{b}" + (f"  ({n_off} off)" if n_off else "")
            with st.popover(label, width="stretch"):
                st.multiselect(f"Courses counted in {b} — {apex}", pool, key=key,
                               on_change=_sync, args=(apex, b, key, pool))
        kept = sub[(sub[BCOL] == b) & (sub["program"].isin(st.session_state[key]))]
        agg = kept.groupby(YCOL)[["programs", "pax"]].sum()
        row = {"Program Type": b}
        for i, y in enumerate(years):
            p = int(agg["programs"].get(y, 0))
            x = int(agg["pax"].get(y, 0))
            totals["programs"][i] += p
            totals["pax"][i] += x
            row[f"Programs {y}"] = p
            row[f"Participants {y}"] = x
            cols[i + 1].markdown(f"<div class='cell'>{p:,}</div>",
                                 unsafe_allow_html=True)
            cols[len(years) + i + 1].markdown(f"<div class='cell'>{x:,}</div>",
                                              unsafe_allow_html=True)
        rows.append(row)

    st.markdown("<div class='rule'></div>", unsafe_allow_html=True)
    cols = st.columns(WIDTHS)
    cols[0].markdown("<div class='rowlabel-total'>Total Programs</div>",
                     unsafe_allow_html=True)
    for i in range(len(years)):
        cols[i + 1].markdown(
            f"<div class='cell-total'>{totals['programs'][i]:,}</div>",
            unsafe_allow_html=True)
        cols[len(years) + i + 1].markdown(
            f"<div class='cell-total'>{totals['pax'][i]:,}</div>",
            unsafe_allow_html=True)

    total_row = {"Program Type": "Total Programs"}
    for i, y in enumerate(years):
        total_row[f"Programs {y}"] = totals["programs"][i]
        total_row[f"Participants {y}"] = totals["pax"][i]
    out = pd.DataFrame(rows + [total_row])
    st.download_button("CSV", out.to_csv(index=False).encode(),
                       file_name=f"taol_course_pax_{apex.lower().replace(' ', '_')}.csv",
                       mime="text/csv", key=f"dl::{apex}")


for apex in APEXES:
    section(apex)
    st.write("")
