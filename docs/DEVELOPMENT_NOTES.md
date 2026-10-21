# Deliverable #5 - Extended application: complex SQL and analytics

Henry Chvoy, CS727

This extends the Deliverable #4 CRUD application over the Experian consumer
credit database (Deliverable #2). Deliverable #5 adds:

- **An Analytics section** of 16 live reports covering every
  technique in the brief: set operations, set membership, set comparison,
  subqueries using `WITH` (including `WITH RECURSIVE`), advanced aggregate
  functions, and OLAP (`ROLLUP`, `CUBE`, window functions).
- **A read-only SQL console** for running and editing any query, with
  PostgreSQL's own error messages shown clearly, caret under the error.
- **A reworked interface**: an icon navigation bar with an Analytics dropdown
  menu, a category sidebar, Run / CSV / Edit-in-console buttons on every
  report, highlighted SQL, a Copy button, and icons throughout the CRUD pages.
- **CSV export** of any report.

Python 3, Flask, psycopg 3, PostgreSQL 16. Everything from Deliverable #4
(CRUD through `sp_open_account`, the audit trigger, error translation) is
unchanged and still works.

## The analytics reports

Every report page leads with the plain-English question, the inputs (where
it has any) with a **Run query** button, and the results table with row count
and execution time. Below the results, two collapsible panels (native HTML
`<details>`, so they work by click or keyboard with no JavaScript) hold the
**exact SQL that ran**, taken verbatim from `queries.py`, and an explanation
of the technique. They start closed so the page leads with the answer.

| Category | Report | Techniques |
|---|---|---|
| Set operations | Every creditor on one credit file | `UNION`, `three-way union`, `duplicate elimination` |
| Set operations | Behind on payments and still applying | `INTERSECT`, `WITH`, `scalar subqueries` |
| Set operations | Applications that never became accounts | `EXCEPT`, `composite-key set difference`, `WITH` |
| Set membership | Consumers by creditor industry | `IN`, `nested IN subqueries`, `correlated scalar subquery` |
| Set membership | Consumers with no open revolving credit | `NOT EXISTS`, `correlated subquery`, `D2 function` |
| Set membership | Creditors that never furnished a tradeline | `NOT IN`, `the NULL trap`, `IS NOT NULL guard` |
| Set comparison | Scores above every delinquent consumer | `> ALL`, `DISTINCT ON`, `WITH`, `D2 function` |
| Set comparison | Clean files scoring below a delinquent one | `< SOME / ANY`, `WITH`, `correlated count` |
| WITH subqueries | Consumer risk tiers | `multiple CTEs`, `CTE chaining`, `FILTER`, `CASE` |
| WITH subqueries | Monthly late-payment calendar | `WITH RECURSIVE`, `gap filling`, `LEFT JOIN`, `FILTER` |
| Advanced aggregates | Creditor portfolio scorecard | `FILTER`, `HAVING`, `STRING_AGG DISTINCT`, `AVG`, `ratio` |
| Advanced aggregates | Score distribution by birth decade | `PERCENTILE_CONT`, `MODE()`, `STDDEV_SAMP`, `WITHIN GROUP` |
| OLAP | Open balances with subtotals (ROLLUP) | `GROUP BY ROLLUP`, `GROUPING()`, `hierarchical subtotals` |
| OLAP | Inquiries cross-tab (CUBE) | `GROUP BY CUBE`, `GROUPING()`, `COUNT DISTINCT` |
| OLAP | Debt ranking (window functions) | `RANK()`, `NTILE()`, `PERCENT_RANK()`, `SUM() OVER`, `named WINDOW` |
| OLAP | Score movement (LAG, PARTITION BY) | `LAG()`, `PARTITION BY`, `FIRST_VALUE()`, `DENSE_RANK()` |

### Where each required topic is demonstrated

- **Set operations** - `UNION` (three-way, with duplicate elimination),
  `INTERSECT` (delinquent AND applying for credit), `EXCEPT` on a composite
  key (inquiries that never became accounts).
- **Set membership** - three nested `IN` subqueries, a correlated
  `NOT EXISTS`, and `NOT IN` with the NULL trap explained and guarded against.
- **Set comparison** - `> ALL` and `< SOME` against a subquery of delinquent
  consumers' scores.
- **WITH** - a four-CTE pipeline where the last CTE reads the first three,
  and a `WITH RECURSIVE` calendar that fills months with no data. Several
  other reports also use `WITH`.
- **Advanced aggregates** - `FILTER (WHERE ...)`, `HAVING`,
  `STRING_AGG(DISTINCT ...)`, and the ordered-set aggregates
  `PERCENTILE_CONT ... WITHIN GROUP`, `MODE()` and `STDDEV_SAMP`.
- **OLAP** - `GROUP BY ROLLUP` and `GROUP BY CUBE` with `GROUPING()` labels;
  window functions `RANK`, `DENSE_RANK`, `NTILE`, `PERCENT_RANK`, `LAG`,
  `FIRST_VALUE`, `SUM() OVER` for share-of-total and running totals,
  `PARTITION BY`, and a named `WINDOW` clause.

The D2 database objects are used inside the analytics too:
`fn_credit_utilization`, `fn_score_band` and `vw_consumer_credit_summary`
appear in reports and in the console's default query.

### How the reports are built

`queries.py` is the single source of truth. Each report is a dictionary: id,
category, title, question, parameters, SQL and explanation. The routes in
`app.py` are generic - look up the report, validate its inputs, run it, render
it - so adding a report is adding a dictionary, not writing a route.

Output columns use quoted aliases (`AS "Total balance"`) so the column headers
come straight from the SQL. A column aliased `"_level"` holds a `GROUPING()`
bitmask; the table hides it and uses it to style subtotal and grand-total rows.

## Using the interface

| Element | What it does |
|---|---|
| Top bar | Icons + labels for Dashboard, Consumers, Accounts, Analytics, SQL console, Audit trail. The current section is highlighted. |
| Analytics menu | Dropdown listing all six categories with report counts. Opens on hover **and** on keyboard focus (Tab), no JavaScript needed. |
| Dashboard tiles | One tile per analytics category plus the console. |
| Report sidebar | Every report grouped by category; current one highlighted. |
| Inputs | Dropdowns for consumers and industries (only valid values offered); text box for numbers, validated on the server. |
| Run query | Re-runs with the chosen inputs. Inputs travel in the URL, so a result can be bookmarked or shared. |
| CSV | Downloads the same result as a spreadsheet. |
| Edit in console | Opens the report's SQL in the console with the inputs filled in, ready to modify. |
| Show SQL / How it works | Expand the statement that ran and an explanation of it. |
| Copy | Copies the SQL to the clipboard. |
| Previous / next | Steps through the reports in a category. |
| Console | Ctrl+Enter runs; "Load a report" drops any report's SQL into the editor. |
| Console templates | One-click starter queries (SELECT, JOIN, GROUP BY, UNION, IN subquery, > ALL, WITH, Recursive, ROLLUP, Window). Each runs as-is against the schema and has a comment marking what to change. Defined in `queries.CONSOLE_TEMPLATES`. |

## Error handling

| Case | What happens |
|---|---|
| Report input not a number (`months=abc`) | "Months to show must be a whole number (you entered "abc")" - report runs with the default instead of failing |
| Report input out of range (`months=500`) | "must be between 1 and 84" |
| Consumer that does not exist (`consumer_id=999`) | "There is no consumer #999." |
| Industry not in the allowed list (hand-edited URL) | Rejected with the list of valid values |
| Unknown report URL | 404 page |
| Console syntax error / unknown column / unknown table | Headline ("Unknown column"), PostgreSQL's message, the offending line with a `^` under the exact character, PostgreSQL's hint, and the SQLSTATE code |
| Missing GROUP BY, division by zero, type mismatch, subquery returning 2+ rows | Each has its own headline, plus PostgreSQL's message |
| Console `INSERT` / `UPDATE` / `DELETE` / DDL | Refused with an explanation before it is sent |
| A write hidden in a CTE (`WITH x AS (DELETE ...) SELECT ...`) or `EXPLAIN ANALYZE DELETE` | Sent, and refused **by PostgreSQL** because the transaction is `READ ONLY` |
| Two statements separated by `;` | Refused: one statement at a time |
| Query running over 5 seconds (`SELECT pg_sleep(10)`) | Cancelled by PostgreSQL's `statement_timeout`, with a hint to add a WHERE or LIMIT |
| Huge result | Capped at 500 rows, with a notice that it was truncated |
| Empty result | "The query ran successfully and returned no rows" - distinct from an error |
| Database down | "Cannot reach the database" on every page instead of a stack trace |

## Data security

- **Every report value is a bound parameter** (`%(consumer_id)s`). On screen
  these markers are highlighted and labelled as parameters, so the viewer can
  see the value never enters the SQL text. There are no f-strings building SQL
  anywhere in the project.
- **The console cannot change data.** It does not rely on spotting the word
  DELETE: the connection is opened with `read_only = True`, so PostgreSQL
  itself refuses any write, however it is phrased. The keyword check exists
  only to give a friendlier message sooner.
- **Resource limits.** `statement_timeout` (set per transaction with
  `set_config(..., true)`, so it cannot leak to other connections) and a
  500-row fetch cap stop one query from tying up the server or the page.
- **No credentials in source**; connection settings come from environment
  variables (see below). SSNs are stored as last-four only (D2 schema).

## Testing

Run against a fresh build of the D2 database before submission:

- All 14 D4 CRUD pages, plus 404 handling.
- Each of the 16 reports: page renders with results, CSV
  download, and Edit-in-console pre-fill. Row counts were checked against the
  seed data by hand (e.g. EXCEPT returns the five rate-shopping inquiries,
  ROLLUP's grand total of 18 open accounts / $725,760.78 matches
  `SELECT SUM(CurrentBalance) FROM Account WHERE AccountStatus = 'Open'`).
- Every input-validation path in the table above.
- 16 console cases: valid query, `%` literal, syntax error, unknown column and
  table, plain DELETE, DELETE inside a CTE, `EXPLAIN ANALYZE DELETE`,
  multiple statements, missing GROUP BY, division by zero, `pg_sleep` timeout,
  large result, empty input, and the NOT IN NULL trap returning zero rows.
- Row counts in Consumer and AccountAudit confirmed unchanged after all the
  write attempts.

## Files

| File | What it is |
|---|---|
| `app.py` | Flask routes: D4 CRUD, plus D5 analytics, CSV, console and template filters |
| `queries.py` | **D5** - the analytics query library: SQL, inputs and explanations |
| `db.py` | Connections, query helpers, error translation; D5 adds `run_report` (read-only, timeout, row cap) and `sql_error_details` |
| `validation.py` | Form validation; D5 adds report-input and console validation |
| `config.py` | Connection settings from environment variables |
| `templates/` | Jinja2 templates. D5 adds `analytics_home`, `analytics_report`, `console`, `_results` and `_icons` |
| `static/style.css` | Stylesheet, no framework |
| `schema/` | The D2 SQL scripts, so this folder can build its own database |

---

# Deliverable #4 foundation (CRUD) - unchanged

## Running it

Needs a PostgreSQL 16 server and the D2 scripts, which are included here under
`schema/` so this folder builds a database on its own.

```bash
# 1. build the database (skip if experian_credit already exists)
createdb experian_credit
./schema/build.sh experian_credit

# 2. install dependencies
pip install -r requirements.txt

# 3. run
flask --app app run
```

Then open <http://127.0.0.1:5000>.

Connection settings come from the standard PostgreSQL environment variables,
so on a local install with default settings nothing needs configuring. Override
any of them if your setup differs:

```bash
export PGHOST=localhost
export PGPORT=5432
export PGDATABASE=experian_credit
export PGUSER=postgres
export PGPASSWORD=...      # only if your server requires one
```

No credentials are in the source tree. `config.py` reads the environment and
sends a password only when one was actually supplied, because a trust-auth
local install rejects the connection if an empty string is passed.

## Files

| File | What it is |
|---|---|
| `app.py` | Flask routes. One function per URL, all the SQL |
| `db.py` | Connections, query helpers, and the error translation table |
| `validation.py` | Form validation, run before anything reaches the database |
| `config.py` | Connection settings from environment variables |
| `templates/` | Jinja2 templates, one per page |
| `static/style.css` | Stylesheet, no framework |
| `schema/` | The D2 SQL scripts, so this folder can build its own database |

## What the application does

**Consumers** - the straightforward entity. Create, list, search by name, view a
credit file, edit, delete. Deleting reaches five tables through
`ON DELETE CASCADE`, so the confirmation page counts the dependent rows first.

**Accounts** - the entity that exercises the schema. Created through
`sp_open_account`, reached through the `ConsumerAccount` junction rather than a
foreign key, and audited on update.

**Audit trail** - the contents of `AccountAudit`. Nothing in the Python writes
to that table; every row is the trigger's work.

## SQL integration

### Parameterized queries, everywhere

Every value reaches PostgreSQL as a parameter, never as part of the query text:

```python
db.query_all("""
    SELECT c.ConsumerID, c.FirstName, c.LastName
      FROM Consumer c
     WHERE UPPER(c.LastName) LIKE UPPER(%s)
""", (f"{search}%",))
```

The `%s` is a psycopg placeholder, not Python string formatting - the tuple is
sent separately and the driver never builds a query string out of it. There is
no f-string anywhere in this project that produces SQL. That is what makes SQL
injection impossible here: typing `'; DROP TABLE Consumer; --` into the search
box searches for a consumer with that name and finds nobody.

The search uses `UPPER(LastName)` specifically because `03_indexes.sql` builds
`idx_consumer_lastname_upper` as an expression index on `UPPER(LastName)`. A
case-insensitive search written any other way would not be able to use it.

### Calling the D2 stored procedure

The new-tradeline form does not `INSERT INTO Account`. It calls:

```python
db.call_procedure("""
    CALL sp_open_account(%(consumer_id)s, %(creditor_id)s,
                         %(account_number_masked)s, %(account_category)s,
                         %(account_type)s, %(date_opened)s,
                         %(limit_or_amount)s, %(monthly_payment)s,
                         %(responsibility_type)s, %(terms_months)s)
""", values)
```

Opening a tradeline is two inserts that must both happen: the `Account` row and
the `ConsumerAccount` row that attaches it to a credit file. An `Account` with
no owner appears on nobody's report, so committing the first without the second
loses data silently. D2 already wrapped both in a procedure with its own
transaction, so the application calls it instead of reimplementing it.

The procedure also refuses to open a tradeline for a consumer with a security
freeze, raising an exception with a message written for a human. The application
displays that message as-is.

Note the form has one amount field, not two. The procedure decides from the
category whether it becomes `CreditLimit` or `OriginalLoanAmount`, which is what
keeps `chk_account_amount_disjoint` satisfied.

### Reading through the D2 functions

The consumer page selects the functions rather than recomputing them:

```sql
SELECT c.*,
       fn_credit_utilization(c.ConsumerID)         AS utilization,
       fn_average_account_age_months(c.ConsumerID) AS avg_age_months,
       fn_on_time_payment_pct(c.ConsumerID)        AS on_time_pct
  FROM Consumer c
 WHERE c.ConsumerID = %s
```

`fn_account_purge_date` and `fn_score_band` are selected the same way in the
account and score listings. Utilization has real logic in it - open revolving
accounts only, `NULL` rather than zero when there is no revolving credit - and
a second implementation in Python would be a second thing to keep correct.

### Letting the trigger do the auditing

The edit form issues a plain `UPDATE Account`. It never touches `AccountAudit`.
`trg_account_audit` fires on the update and writes one row per changed column,
which is what the audit trail page displays. Changing a balance and a status in
one submission produces two audit rows.

This is the point of putting the rule in a trigger rather than in the
application: it holds no matter which program does the writing. A second
application against this database, or somebody typing `UPDATE` into psql, gets
audited identically.

### Translating constraint violations

The schema enforces business rules in `CHECK` constraints, so the database is
where most invalid input is caught, and Postgres reports it by constraint name.
`db.py` maps those names onto sentences:

```python
CONSTRAINT_MESSAGES = {
    "chk_account_pastdue_agrees":
        "An account with money past due cannot also be marked Current.",
    "chk_account_amount_disjoint":
        "Revolving accounts carry a credit limit; installment accounts carry "
        "an original loan amount. An account cannot have both.",
    ...
}
```

`friendly_error()` reads `exc.diag.constraint_name` off the psycopg exception and
looks it up. Unmapped constraints fall through to the raw database message
rather than a generic failure, because the constraint name still tells the user
more than "something went wrong" does.

`validation.py` checks the same rules before the statement is sent. That is not
redundancy for its own sake: a `CHECK` can only reject the whole statement, so
pre-validating is how the user gets "Year of birth must be a whole number"
attached to the field they got wrong. The database checks remain the actual
guarantee. Anything that gets past the Python layer is still caught by Postgres
and translated.

## Error handling and edge cases

| Case | What happens |
|---|---|
| Blank required field | Named in the error list, form redisplays what was typed |
| Text in a number field | "Current balance must be a number" |
| Year of birth 1850 or 3000 | Rejected against `chk_consumer_birthyear`'s range |
| Full SSN typed in | Rejected. Four bare digits are masked to `XXX-XX-1234` instead |
| Security freeze with no start date | Rejected before the statement is sent |
| Duplicate account number for one creditor | `uq_account_number` caught and explained |
| Tradeline for a frozen consumer | The procedure's own message is shown |
| Account marked Closed with no closing date | Rejected |
| Closing date before opening date | Caught by `chk_account_dates`, translated |
| Negative balance or limit | Rejected before the statement is sent |
| URL for a record that does not exist | 404 page, not a stack trace |
| Record deleted in another window | `rowcount == 0` is detected and reported |
| Database down | "Cannot reach the database" with what to check |

Deletes are two steps. The confirmation page counts what will cascade, because
a cascade the user did not expect is the worst kind of data loss, and the
counts come from the database rather than from an assumption about the schema.

## Data security

- Parameterized queries throughout, so user input is never executable.
- No credentials in the source tree; connection settings come from the
  environment.
- The schema stores only the last four digits of an SSN. If a full SSN is
  typed into the form it is rejected rather than truncated, and
  `chk_consumer_ssn_format` would refuse it even if the application let it
  through.
- Four bare digits are masked rather than bounced. The rule exists so that full
  SSNs are never stored, and helping the user comply serves that better than a
  refusal does.
- `debug=True` is only set under `if __name__ == "__main__"`, so the
  interactive debugger is not exposed when run through `flask run`.

## Notes

**psycopg lowercases column names.** PostgreSQL folds unquoted identifiers to
lower case, so `SELECT FirstName` comes back as the key `firstname`, not
`FirstName`. The templates use the lowercase form throughout. Aliasing a column
with `AS utilization` makes the key predictable, which is why the computed
columns are all aliased.

**`PaymentStatus` and `PastDueAmount` are deliberately not editable.**
`trg_sync_account_status` derives both from the newest `PaymentHistory` row.
Anything the form wrote to them would be overwritten the next time a payment
was reported, and setting `PastDueAmount` by hand can violate
`chk_account_pastdue_agrees`. Reporting a payment is what changes them, and
that is `sp_record_monthly_payment`'s job, not this form's.

**Account category cannot be changed after opening.** The category decides
which of `CreditLimit` and `OriginalLoanAmount` is legal, and
`chk_account_amount_disjoint` says an account cannot have both. Moving a value
between them would need two statements against a constraint that forbids the
intermediate state.

**Collection accounts cannot be opened from the new-tradeline form.**
`sp_open_account` has no `OriginalCreditorID` parameter, and
`chk_account_collection_origin` requires one for a collection. That is correct:
a collection is not a new tradeline, it is an existing debt changing hands,
which is `sp_transfer_to_collections`. The form says so instead of failing on
the constraint.

**Consumer IDs are shown next to holder names** in the account list. The D2 seed
data contains a father and son with the same name at the same address - the
mixed-file pair Q20 of Deliverable #3 detects - and without the ID a joint
account between them reads as one person listed twice.

## Testing

Every route and every error path above was exercised against a live database
before submission: 56 checks covering the four CRUD operations on both entities,
each validation rule, each mapped constraint violation, the stored procedure's
security-freeze exception, the audit trigger firing on update, and the cascade
counts on both delete confirmations.
