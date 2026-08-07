# TAOL Course & Pax — Year-wise, Apex-wise

Courses and participants for four apexes — **Karnataka, Telangana, Andhra Pradesh,
Tamil Nadu** — split into **Happiness / Rural / C&T / Other**, on either a calendar
or a financial year.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Live app: one section per apex, plus a combined table when more than one is
selected.

## What the numbers mean

All of it comes off the warehouse view `view_event`. No join to
`view_course_teacher`, so there is no pax fan-out across teachers and the
`refresh_type='D'` soft-delete defect does not apply — that column lives on the
teacher view. Cross-checked against the teacher-participants basis on Karnataka:
agrees to within 0.15%.

| | |
|---|---|
| **No. of Programs** | `COUNT(DISTINCT global_event_id)` — one course event counts once, however many teachers taught it |
| **No. of Participants** | `SUM(new_pax)` — new participants. `repeat_pax` is excluded; it is a rounding error in these apexes |
| **Apex** | `apex_name` — who **owns** the course |
| **Year** | from the course **start date**. Calendar = Jan–Dec; Financial = Apr–Mar |
| **Org** | `org_id`, defaulting to `TAOL` |
| **Excluded** | CRF not submitted, and cancelled events — the same rules the apex / trust / category reports use |

### Apex, not the state a course ran in

Geography is `apex_name`, never `course_event_state`. The difference is large
(TAOL, CY2025):

| Basis | Programs | Pax |
|---|---|---|
| apex = Karnataka | 8,579 | 66,561 |
| course_event_state = Karnataka | 9,806 | 118,279 |

**Pax nearly doubles on the held-in basis while the program count barely moves.**
The gap is Ashram Apex — courses held in Karnataka but owned by the ashram, ~28
participants each against ~4.8 for the Karnataka apex. Apex is the basis the state
reports use, so it is the only basis offered. `course_event_state` remains as the
"Held in state" filter, for "of our courses, which ran outside the state".

## The four program types — desk-first

Grouping is by **`desk_name`**, the desk that owns the program. It beats the
website tag file, which misfiles several:

| | Desk (used) | Tag (rejected) |
|---|---|---|
| YLTP / WLTP / OWLTP | Rural ✅ | Other ❌ |
| Yes! | C&T ✅ | Other ❌ |
| Happiness Program for Youth, OMBW for Youth | Other, via YES+ desk ✅ | Happiness ❌ |

`Happiness Program` desk → Happiness, `YLTP  DESK` (two spaces, as stored) →
Rural, `Children and Teens Desk` → C&T, everything else → Other. The two
groupings disagree on **58 of 366** course titles;
`data/program_bucket_map.csv` lists every title under both, for reference.

### The program type labels are dropdowns

Each program type in each apex section opens a list of its course names
(`name_en_gb`). Untick a course and that section's row and total move with it.

Eleven titles start unticked. They belong to their desk, but are not what people
mean by that program type, so the dashboard opens on the conservative number:

- **Happiness desk, not happiness programs** — Sudarshan Chakra Kriya (1,267
  programs / 31,921 pax), Deep Sleep & Anxiety Relief, SELP (23 programs but ~10k
  pax), Online HAMP
- **Covid-era campaigns** — Immunity Enhancement, Covid and Post-Covid Recovery,
  IDY 2021. Kept under Happiness because they were delivered as HP variants, off by
  default because they would otherwise inflate the older years
- **C&T by desk, Rural by name** — Rural ArtExcel, Rural YES

A program type showing "(n off)" has n courses unticked.

The sidebar carries only what changes the answer: calendar or financial year,
which years, and which held-in states. Org is fixed to TAOL, geography to apex,
grouping to course desk.

## Rebuilding the data

```bash
python3 build_state_data.py            # -> data/state_program.parquet + meta + title map
python3 build_state_data.py --raw      # diagnostic: no CRF / cancelled filters
```

**The build must run on the office network** — the warehouse is IP-allowlisted.
That is why the parquet is committed: a publicly hosted app can never query it.
The password comes from `~/.pgpass`, never from code.

Grain is (state, org, apex, desk, month, program). Month rather than year is what
lets one file serve both the calendar and financial year slices, and the month
range slider, without a rebuild.

## Open: the circulated Karnataka report

A report circulated 7 Aug 2026 shows Karnataka as 3,144 programs / 20,883 pax for
"2025", with a Happiness row of 1,807 / 9,305. Its scope is **apex Karnataka + org
TAOL** — that part is confirmed. The period is not:

| Definition | "2025" col | "2026" col | Error |
|---|---|---|---|
| Jan–Jun | 1,826 / 9,007 | 2,336 / 13,438 | **2.6%** |
| Calendar year | 3,823 / 18,869 | 2,628 / 14,726 | 60.8% |
| FY2024-25 vs FY2025-26 | 3,544 / 18,264 | 4,031 / 20,280 | 81.6% |

No full year — calendar or financial — comes close; our full-year figure is
roughly double theirs. Only a ~6-month window fits, and it fits all four numbers
with one parameter. Independently: their 2026 column *exceeds* their 2025 column
(+22% programs, +44% pax) when only ~7 months of 2026 exist, so both columns must
be the same partial window.

Ruled out along the way: `crf_consider = 1`, raw/unfiltered, the teacher-participant
basis, the desk grouping, the school/institutional exclusion, apex vs state, and
every course-type subset of the Happiness family. The Postgres staging base tables
(`event`, `course_teacher_fact`) reproduce `view_event` exactly.

**Resolving it needs the report's date range from whoever produced it.** If it
really is Jan–Dec, then that source is missing about half the courses the
warehouse holds, and the next step is an event-by-event diff for a single month.
