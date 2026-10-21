# Credit Bureau Database & Analytics App

A PostgreSQL database for consumer credit data, modeled on the structure of an
Experian-style credit report, plus a Flask web application on top of it with
full CRUD and 16 analytics reports.

Built by Henry Chvoy for CS 727, Relational Database Application &
Implementation, at Illinois Institute of Technology (2026).

**Stack:** PostgreSQL 16 · SQL / PL/pgSQL · Python 3 · Flask · psycopg 3 · Jinja2 · Bash

---

## What's in it

### The database (`schema/`)
- **9 normalized tables:** Consumer, Address, Creditor, Account,
  ConsumerAccount (junction for joint and authorized-user accounts),
  PaymentHistory, Inquiry, CreditScore, AccountAudit
- **Business rules in the schema:** CHECK constraints keep the data
  consistent (for example, a revolving account carries a credit limit and an
  installment loan carries an original amount, never both; an account with
  money past due can't be marked Current)
- **9 indexes**, including an expression index for case-insensitive name search
- **5 functions:** credit utilization, average account age, on-time payment
  percentage, score band, and account purge date
- **5 views**, including a one-row-per-consumer credit summary
- **4 triggers:** an audit trail that logs every changed column on an account
  update, account status synced from the latest payment, hard-inquiry
  expiration dates, and one current address per consumer
- **4 stored procedures:** opening a tradeline, recording a monthly payment,
  transferring an account to collections, and purging records past their
  reporting period, each as a single transaction
- **One-command build:** `schema/build.sh` creates everything in dependency order

### The application
- **CRUD for consumers and accounts.** New accounts go through the stored
  procedure, edits are audited by the trigger, and deletes show a count of
  every dependent row before they cascade.
- **16 analytics reports** covering set operations (UNION / INTERSECT /
  EXCEPT), correlated and nested subqueries, `> ALL` / `< SOME`, multi-step
  and recursive CTEs, ordered-set aggregates (`PERCENTILE_CONT`, `MODE`),
  `ROLLUP`, `CUBE`, and window functions (`RANK`, `NTILE`, `LAG`,
  `PERCENT_RANK`, running totals). Each report shows its results, the exact
  SQL that ran, and a CSV export.
- **Read-only SQL console** for running ad-hoc queries, with PostgreSQL's own
  error messages and a caret pointing at the problem.

### Security and reliability
- Every query is parameterized, so user input never becomes SQL text.
- The console runs in a `READ ONLY` transaction, so the database itself
  refuses writes (including ones hidden inside a CTE), plus a 5-second
  `statement_timeout` and a 500-row cap.
- Constraint violations are translated into plain-English messages.
- No credentials in the source; connection settings come from environment variables.
- Only the last four digits of an SSN are stored.

---

## Running it locally

You need PostgreSQL 16 and Python 3.

```bash
# 1. Build the database
createdb experian_credit
./schema/build.sh experian_credit

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
flask --app app run
```

Then open <http://127.0.0.1:5000>.

Connection settings use the standard PostgreSQL environment variables
(`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`). A default local
install needs no configuration.

## Project layout

| Path | What it is |
|---|---|
| `schema/` | SQL scripts for tables, seed data, indexes, functions, views, triggers, and procedures, plus `build.sh` |
| `app.py` | Flask routes |
| `queries.py` | The analytics report library: each report's SQL, inputs, and explanation |
| `db.py` | Connections, query helpers, read-only report runner, and error translation |
| `validation.py` | Form and report-input validation |
| `config.py` | Connection settings from environment variables |
| `templates/`, `static/` | Jinja2 templates and stylesheet (no CSS framework) |
| `docs/DEVELOPMENT_NOTES.md` | Detailed write-up: every report, every error case, design decisions, and testing |

## Notes

All names, addresses, phone numbers, and account numbers in the seed data are
fabricated. This is an academic project and is not affiliated with or endorsed
by Experian.
