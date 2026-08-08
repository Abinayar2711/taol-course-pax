# TAOL Course & Pax — Year-wise, Apex-wise

Courses and participants by apex — **Karnataka, Telangana, Andhra Pradesh** —
split into **Happiness / Rural / C&T / Sahaj Samadhi / Part 2 & DSN / Sri Sri
Yoga / Other**, on either a calendar or a financial year.

Tamil Nadu is held back for now. Its data is still built and still in the
parquet; `HIDDEN_APEXES` in `build_state_data.py` controls what the app shows, so
bringing it back is one line plus a rebuild.

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
| apex = Karnataka | 8,580 | 66,563 |
| course_event_state = Karnataka | 9,807 | 118,281 |

**Pax nearly doubles on the course-event-state basis while the program count
barely moves.**
The gap is Ashram Apex — courses held in Karnataka but owned by the ashram, ~28
participants each against ~4.8 for the Karnataka apex. Apex is the basis the state
reports use, so it is the only basis offered. `course_event_state` remains as the
"Course event state" filter, for "of our courses, which ran outside the state".

## The program types — desk-first

Grouping is by **`desk_name`**, the desk that owns the program. It beats the
website tag file, which misfiles several:

| | Desk (used) | Tag (rejected) |
|---|---|---|
| YLTP / WLTP / OWLTP | Rural ✅ | Other ❌ |
| Yes! | C&T ✅ | Other ❌ |
| Happiness Program for Youth, OMBW for Youth | Other, via YES+ desk ✅ | Happiness ❌ |

Desk names are spelled exactly as the warehouse stores them, so `DESK_BUCKETS` is
a lookup and never a match — odd capitalisation and all:

| Row | `desk_name` |
|---|---|
| Happiness | `Happiness Program` |
| Rural | `YLTP  DESK` (two spaces, as stored) |
| C&T | `Children and Teens Desk` |
| Sahaj Samadhi | `Sahaj Samadhi Meditation Desk` |
| Part 2 & DSN | `PART 2 and DSN DESK` |
| Sri Sri Yoga | `Sri Sri yoga DESK` **and** `Sri Sri School of Yoga` |
| Other | everything else — YES+ (the largest left), TTP, VTP, Pran, Prison Smart, Eternity, Wellness, Ayurveda Cooking, Vedic Math, MSME, Spine, GEP |

The School of Yoga is the judgement call: a second, much smaller yoga desk (218
programs all-time) where 215 are ordinary Deep Dive and kids' yoga classes, titles
that also appear under `Sri Sri yoga DESK`. Only a 200H and a 300H Yoga Teacher
Training sit oddly. Move that one line to Other if the yoga row should be classes
only.

The two groupings disagree on **129 of 366** course titles — but 71 of those are
just the Sahaj, Part 2 & DSN and Sri Sri Yoga titles, which the tag grouping has
no row for. On the original four rows it is **58 of 366**, unchanged.
`data/program_bucket_map.csv` lists every title under both, for reference.

### The program type labels are dropdowns

Each program type in each apex section opens a list of its course names
(`name_en_gb`). Untick a course and it leaves that program type's row — but it is
**counted under *Other Programs*** instead of disappearing, so the Total is
always the apex's full activity. Untick it a second time in Other and it leaves
the Total too; that is the only way to drop a course entirely.

Other's dropdown therefore lists its own desks' courses plus everything rolled in
from above, with a note saying how many rolled in.

What starts ticked, per bucket:

| Bucket | Default |
|---|---|
| **Happiness** | Only *Happiness Program (3 Days)*, *Online Meditation and Breath Workshop*, *Happiness Program*. The other 18 titles in the desk — Sudarshan Chakra Kriya, Deep Sleep, SELP, the Covid-era campaigns, the Spl AoL programs, Part I Course — start off. |
| **Rural** | Only *Rural Happiness Program* and *YLTP*. Online YLTP, OWLTP, WLTP, AMP - Rural, Online Rural Happiness Program and Project Bharat start off. |
| **C&T** | Everything except the school batches, the KYC/KYT parenting courses, the special-needs batches and the Smart programs — titles matching `school`, `govt`, `ssrvm`, `kyc`, `kyt`, `know your child/teen`, `deaf`, `blind` or `smart`. 46 titles start off. It cannot key off `course_category`: that flags Art Excel, Utkarsha Yoga and Yes! as institutional too. |
| **Sahaj Samadhi** | Everything on — all four titles. Note *Sahaj Samadhi Dhyana Yoga 1on1* and its online form are one participant per program by definition: 1,134 programs all-time but only 1,133 pax, so they lift the program count far more than the pax. Untick them if a row of group courses is what is wanted. |
| **Part 2 & DSN** | Everything on. |
| **Sri Sri Yoga** | Everything on. |
| **Other** | Everything on, including the courses unticked above. |

Note *Part I Course* and *3 Days Part I Course* are the Happiness Program under
its old name. They are off by default and effectively dormant anyway — 3,806
programs in 2013, under 25 a year from 2015 — but pick a year before 2015 and
Happiness will read low until you tick them back on.

A program type showing "(n off)" has n courses unticked.

The sidebar carries only what changes the answer: calendar or financial year,
which years, and which course event states. Org is fixed to TAOL, geography to apex,
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

## Next

- **Decide `TAOL Yoga and Meditation Program for Educators`.** The Children and
  Teens desk owns it, so it counts in C&T, but it is an adult course for school
  teachers (32 programs / 943 pax all-time, 15 / 407 in 2025). Leaning toward
  default-unticked. Same for `Online TAOL Yoga & Meditation Program for Educators`.
- **Refresh is manual.** `build_state_data.py` must run on the office network,
  then commit and push. No timer here yet, unlike the teacher dashboard.
