# Assistant benchmark: the owner's real questions

The questions the owner wrote by hand on the requirements sheet (section 12, "AI Agent - Real Questions", 4 Nov
2026), plus the sheet's five printed examples, as 21 cases. Each case says what a right answer must hold. That
check is worked out from the ERP itself when the benchmark runs, so it holds on any site and on any day.

Code: `apps/imed_erp/imed_erp/assistant/benchmark/` (`cases.py` holds the questions and their answer checks;
`run.py` runs and scores them).

## The questions

Each handwritten line is shown as it was read. **(?)** marks a reading to confirm with the owner before trusting
that case's score.

| Case | Handwriting, as read | Question asked | Kind | What the ERP holds |
|---|---|---|---|---|
| H01 | مين بيشتغل ومين مش بيشتغل | مين بيشتغل ومين مش بيشتغل النهارده؟ | unavailable | no attendance (no HR app) |
| H02 | كام كتاب اتباع للدكتور ايمن كتاب bio | كام كتاب اتباع للدكتور أيمن، كتاب البيو؟ | facts | Book Edition sold quantities |
| H03 **(?)** | الناس النهاردة حجم اساعة كام | الناس النهارده حجزت الساعة كام؟ | list | today's held bookings and their times |
| H04 | مين اتأخر بعد ٩ ونص | مين اتأخر بعد ٩ ونص؟ | unavailable | no attendance |
| H05 | الأحبار والورق فيها مخزون كام | الأحبار والورق فيها مخزون كام؟ | facts | paper in sheets and boxes; ink not a stock item |
| H06 | الأحبار اتحطت فين | الأحبار اتحطت فين؟ | unavailable | ink not stocked (becomes "list" once it is) |
| H07 | كام كارتونة ورق متبقية | كام كرتونة ورق متبقية؟ | facts | paper ÷ 2,500 sheets a box |
| H08 | حساب كامل لكل مكان لوحده | عايز حساب كامل لكل مكان لوحده. | facts | revenue, expenses and net per business, this month |
| H09 | كام واحد حجز الاستوديو النهاردة | كام واحد حجز الاستوديو النهارده؟ | facts | today's studio bookings, distinct customers |
| H10 **(?)** | الحجوزات اللي اتعملت وواحد لنفس… اخد كام ساعة | الحجوزات اللي اتعملت النهارده، وكل واحد خد كام ساعة؟ | facts | hours per customer today |
| H11 **(?)** | اعد فلوسك والحسابات بالنسبة للاستوديو | فلوس الاستوديو وحساباته الشهر ده عاملة إيه؟ | facts | studio revenue, expenses, net; XStudio due and paid shown apart |
| H12 **(?)** | هيثم دفع | هيثم دفع؟ | facts | App Payments of a student, or collections of a doctor, named Haitham |
| H13 | كام مدرس عمل كام طالب | كام مدرس، وكل مدرس عنده كام طالب؟ | facts | active App Courses: teachers and students |
| H14 | المكتبة بيدخل رصيد الحبر على السيستم حطيناه امتى | رصيد الحبر في المكتبة اتحط على السيستم امتى؟ | unavailable | ink not stocked |
| H15 | معدل طبيعي الأحبار هتخلص امتى | معدل استهلاك الأحبار الطبيعي قد إيه، والأحبار هتخلص امتى؟ | unavailable | ink not stocked |
| H16 | لما المخزون يخلص يدي انذار | لما المخزون يخلص ابعتلي إنذار. | readonly | a request: reorder alerts exist; the assistant sets nothing |
| T01 | (sheet example) | إيرادات النهارده كام؟ | facts | today's income in the ledger |
| T02 | (sheet example) | مين أكتر مكان كسب الشهر ده؟ | list | the business with the most income this month |
| T03 | (sheet example) | مصروفات الاستوديو الشهر ده كام؟ | facts | the studio's expenses this month |
| T04 | (sheet example) | إيه الحجوزات بتاعة بكرة؟ | list | tomorrow's held bookings |
| T05 | (sheet example) | إيه المنتجات اللي قربت تخلص؟ | list | items at or below their reorder level |

The owner's answer on the sheet to "can we see real examples of the reports you use?" was "مفيش" (none), so no
case is built on an existing report format.

## How an answer is scored

Every run gets three scores from 0 to 1, plus its timings.

| Score | What it measures |
|---|---|
| **correct** | **facts:** every figure of the check appears in the answer (counts exactly, money within 1%; Arabic digits and thousands separators read). **list:** every item named. **unavailable:** the answer says the ERP does not hold it, and gives no figure for it. **readonly:** it says it only reads, and where the thing is done. **No records** (a figure of zero with nothing behind it): the answer must say the data is missing, not present the zero as a result. |
| **grounded** | It read a source that holds the answer: one of the case's expected tools, such as `list_records` or `run_report`. |
| **style** | Arabic, spoken Egyptian (not standard Arabic), plain text with no markdown. Each part weighs a quarter. |
| **timings** | When the first words appear (streamed), the whole answer, and the time in planning and in answering. |

The summary reports:
- the mean of each score;
- how many answers were fully correct;
- honesty when there is no data;
- first-words and whole-answer times at the median and the 90th percentile;
- reads that failed, and questions that crashed;
- the correct score by category (staff, library, library-stock, bookings, studio, accounts, ba-plus);
- a line per case with what was missing.

These checks are mechanical, so they err strict. An answer that gives the right figure in words ("ستة") rather than
digits counts as missing it. Read the notes column and the full answers in `results.csv` before quoting a score.

## Running it (not run yet)

It calls the configured models (Claude, and nothing else), so it costs money. It refuses to run without
`paid_calls`:

```
bench --site <site> execute imed_erp.assistant.benchmark.run.run --kwargs '{"paid_calls": 1}'
# one or a few cases, or each question several times (the models do not answer the same way twice):
bench --site <site> execute imed_erp.assistant.benchmark.run.run --kwargs '{"paid_calls": 1, "only": "H02,H07", "repeat": 3}'
```

What a run does:
- **User:** the questions are asked as `owner@imed.local`, through the real flow: planner, then reads, then answer.
- **Nothing kept:** a fresh memory for each question, so nothing is saved, and the reads are read-only.
- **Results:** they go to `sites/<site>/private/assistant-benchmark/<time>/`:
  - `results.json`: every run in full: the plan, each read and its result, the answer, the timings, the scores and
    the check's values;
  - `results.csv`: one line per run;
  - `summary.md`: the numbers.

**Cost:** about 2 model calls a question and about 3,000 to 8,000 characters in, so 21 cases cost roughly the price
of 42 short calls (one Haiku 5.5 plan and one Sonnet 4.6 answer each).

**Where to run it:** on a copy with real data, for meaningful figures (the local sites hold almost no ledger data).
On production it only reads, but it does spend the model budget.

## What the cases already show, before any run

- **Attendance (H01, H04):** no attendance or check-in data in the ERP. The right answer today is "not recorded";
  the data would need an attendance system first.
- **Ink (H05, H06, H14, H15):** not a stock item, only a cost per sheet. Where it is, when it was entered and when it
  runs out cannot be answered until ink is received and issued as stock, like paper.
- **The alert (H16):** a feature, not a question. Reorder alerts already notify when a stocked item reaches its
  reorder level (`imederp/stock_reorder.py`). Ink would get the same once it is stocked.
