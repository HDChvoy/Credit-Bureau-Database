"""
Database access layer.

Everything that talks to PostgreSQL goes through this file. Two jobs:

  1. Hand out connections and run queries. Every query is parameterized -
     values are passed to psycopg as a separate tuple and never formatted
     into the SQL string. This is what makes SQL injection impossible
     here, and it is the reason there is not a single f-string in any
     query in this project.

  2. Translate database errors into sentences a user can read. The D2
     schema enforces a lot of business rules in CHECK constraints and
     triggers, which means the database is where most invalid input gets
     caught. Postgres reports those by constraint name. Showing the user
     "chk_account_pastdue_agrees" is useless, so the names are mapped to
     explanations below.
"""

import psycopg
from psycopg.rows import dict_row

from config import DB_SETTINGS


# ---------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------

def get_connection():
    """Open a connection that returns rows as dictionaries.

    dict_row means a query result is accessed as row["FirstName"]
    instead of row[1], so the templates do not depend on column order.
    """
    return psycopg.connect(**DB_SETTINGS, row_factory=dict_row)


def query_all(sql, params=None):
    """Run a SELECT and return every row as a list of dicts."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def query_one(sql, params=None):
    """Run a SELECT and return the first row, or None if there wasn't one."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()


def execute(sql, params=None, returning=False):
    """Run an INSERT / UPDATE / DELETE.

    The `with conn` block commits if the body completes and rolls back if
    it raises, so a statement that trips a constraint never leaves a
    half-finished change behind.

    Returns the first row when returning=True (for INSERT ... RETURNING),
    otherwise the number of rows affected - which is how the update and
    delete routes tell "row not found" apart from "it worked".
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            if returning:
                return cur.fetchone()
            return cur.rowcount


def call_procedure(sql, params=None):
    """Run a CALL against one of the D2 stored procedures.

    Kept separate from execute() only to make it obvious at the call site
    that the work is happening inside the database rather than here.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())


# ---------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------

# Constraint name -> what the user did wrong. These names come straight
# out of 01_ddl.sql; if a constraint is renamed there it must be renamed
# here too, which is why the key is the constraint name and not a
# substring match on the message.
CONSTRAINT_MESSAGES = {
    # Consumer
    "chk_consumer_birthyear":
        "Year of birth must be between 1900 and the current year.",
    "chk_consumer_ssn_format":
        "SSN must be masked in the form XXX-XX-1234. Only the last four "
        "digits are ever stored.",
    "chk_consumer_freeze_date":
        "A security freeze needs a freeze start date, and an account "
        "without a freeze must not have one.",

    # Account
    "chk_account_category":
        "Account category must be Revolving, Installment, Open or Collection.",
    "chk_account_status":
        "Account status must be Open, Closed, Transferred or Paid.",
    "chk_account_amount_disjoint":
        "Revolving accounts carry a credit limit; installment accounts "
        "carry an original loan amount. An account cannot have both.",
    "chk_account_collection_origin":
        "A collection account must name the original creditor, and only a "
        "collection account may name one.",
    "chk_account_dates":
        "The closing date cannot be earlier than the date the account was opened.",
    "chk_account_not_future":
        "An account cannot be opened on a future date.",
    "chk_account_closed_has_date":
        "An account marked Closed needs a closing date.",
    "chk_account_amounts_nonneg":
        "Balances and limits cannot be negative.",
    "chk_account_pastdue_agrees":
        "An account with money past due cannot also be marked Current.",
    "uq_account_number":
        "That account number already exists for this creditor.",

    # Relationships
    "chk_ca_responsibility":
        "Responsibility must be Individual, Joint, Cosigner or Authorized User.",
    "chk_ca_dates":
        "The removal date cannot be earlier than the date the account was "
        "associated with the consumer.",
    "fk_account_creditor":
        "That creditor does not exist.",
    "fk_account_origcreditor":
        "The original creditor does not exist.",

    # Address
    "chk_address_type":
        "Address type must be Residential, Mailing, Business or PO Box.",
    "chk_address_dates":
        "The last reported date cannot be earlier than the first reported date.",
    "uq_one_current_address":
        "That consumer already has a current address.",
}


def friendly_error(exc):
    """Turn a psycopg exception into a sentence for the user.

    Falls back to the raw database message rather than a generic
    "something went wrong", because an unmapped constraint still tells
    the user more than silence does.
    """
    # A creditor that still has accounts cannot be deleted: the FK is
    # ON DELETE RESTRICT. Checked first because ForeignKeyViolation is a
    # subclass of IntegrityError.
    if isinstance(exc, psycopg.errors.ForeignKeyViolation):
        name = getattr(exc.diag, "constraint_name", None)
        if name in CONSTRAINT_MESSAGES:
            return CONSTRAINT_MESSAGES[name]
        return ("This record is still referenced by other records, so it "
                "cannot be removed or changed.")

    if isinstance(exc, (psycopg.errors.CheckViolation,
                        psycopg.errors.UniqueViolation)):
        name = getattr(exc.diag, "constraint_name", None)
        if name in CONSTRAINT_MESSAGES:
            return CONSTRAINT_MESSAGES[name]
        return f"That value breaks a database rule ({name})."

    if isinstance(exc, psycopg.errors.NotNullViolation):
        column = getattr(exc.diag, "column_name", "A required field")
        return f"{column} cannot be left empty."

    # RAISE EXCEPTION inside a stored procedure - sp_open_account raises
    # one of these for a security freeze. The message is already written
    # for a human, so it is passed through as-is.
    if isinstance(exc, psycopg.errors.RaiseException):
        return str(exc).split("\n")[0]

    if isinstance(exc, psycopg.errors.InvalidTextRepresentation):
        return "One of the values is not in the format the database expects."

    if isinstance(exc, psycopg.OperationalError):
        return ("Cannot reach the database. Check that PostgreSQL is running "
                "and that the experian_credit database exists.")

    return f"Database error: {exc}"


# ---------------------------------------------------------------------
# Deliverable #5: running analytics reports and console queries
# ---------------------------------------------------------------------

import time

# A report that runs longer than this is cancelled by PostgreSQL itself,
# so one bad console query cannot tie up the server.
STATEMENT_TIMEOUT_MS = 5000


def run_report(sql, params=None, max_rows=None):
    """Run a read-only query and return (columns, rows, elapsed_ms, truncated).

    Used by the Analytics pages and the SQL console. Three protections,
    all enforced by PostgreSQL rather than by inspecting the SQL text:

      * READ ONLY transaction - any INSERT, UPDATE, DELETE, DDL or
        data-modifying CTE is refused by the server with
        ReadOnlySqlTransaction, however it is spelled.
      * statement_timeout     - a runaway query is cancelled after
        STATEMENT_TIMEOUT_MS with QueryCanceled.
      * max_rows              - at most this many rows are fetched,
        so a huge result cannot exhaust the web process.

    Rows come back as plain tuples (not dicts) so the column order of the
    SELECT list is preserved exactly for the results table and the CSV.
    `params` of None means the SQL text is not scanned for placeholders,
    which is what lets console queries contain a literal % sign.
    """
    with psycopg.connect(**DB_SETTINGS) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            # set_config(..., true) is the parameterizable form of
            # SET LOCAL: it lasts only until this transaction ends.
            cur.execute("SELECT set_config('statement_timeout', %s, true)",
                        (str(STATEMENT_TIMEOUT_MS),))
            started = time.perf_counter()
            cur.execute(sql, params)
            elapsed_ms = (time.perf_counter() - started) * 1000

            if cur.description is None:
                # A statement that returns no result set (e.g. SET).
                return [], [], elapsed_ms, False

            columns = [col.name for col in cur.description]
            if max_rows is None:
                rows = cur.fetchall()
                truncated = False
            else:
                rows = cur.fetchmany(max_rows + 1)
                truncated = len(rows) > max_rows
                rows = rows[:max_rows]

    return columns, rows, elapsed_ms, truncated


def inline_params(sql, params):
    """Return the SQL with parameter values substituted, for display.

    Used only by "Open in SQL console", so a parameterized report can be
    edited as a complete statement. psycopg's ClientCursor.mogrify does
    the quoting, the same code path the driver uses for client-side
    binding, so a value containing a quote is escaped correctly. The
    console runs read-only regardless.
    """
    with psycopg.connect(**DB_SETTINGS) as conn:
        return psycopg.ClientCursor(conn).mogrify(sql, params)


# Error classes a console user is likely to hit, mapped to a short
# headline. The full PostgreSQL message is shown underneath.
SQL_ERROR_TITLES = [
    (psycopg.errors.SyntaxError,            "Syntax error"),
    (psycopg.errors.UndefinedTable,         "Unknown table or view"),
    (psycopg.errors.UndefinedColumn,        "Unknown column"),
    (psycopg.errors.UndefinedFunction,      "Unknown function or operator"),
    (psycopg.errors.AmbiguousColumn,        "Ambiguous column name"),
    (psycopg.errors.GroupingError,          "GROUP BY error"),
    (psycopg.errors.DatatypeMismatch,       "Type mismatch"),
    (psycopg.errors.InvalidTextRepresentation, "Value in the wrong format"),
    (psycopg.errors.DivisionByZero,         "Division by zero"),
    (psycopg.errors.CardinalityViolation,   "Subquery returned more than one row"),
    (psycopg.errors.ReadOnlySqlTransaction, "Read-only: this console cannot change data"),
    (psycopg.errors.QueryCanceled,          "Query took too long and was cancelled"),
    (psycopg.errors.InsufficientPrivilege,  "Permission denied"),
    (psycopg.OperationalError,              "Cannot reach the database"),
]


def sql_error_details(exc, sql_text=None):
    """Describe a failed query in enough detail to fix it.

    Returns a dict with a headline, PostgreSQL's own message, its hint
    and detail if it gave any, and - when PostgreSQL reported a character
    position - the offending line with a caret under the column, the way
    psql does it.
    """
    title = "Query failed"
    for cls, label in SQL_ERROR_TITLES:
        if isinstance(exc, cls):
            title = label
            break

    diag = getattr(exc, "diag", None)
    message = (getattr(diag, "message_primary", None)
               or str(exc).split("\n")[0])
    details = {
        "title": title,
        "message": message,
        "detail": getattr(diag, "message_detail", None),
        "hint": getattr(diag, "message_hint", None),
        "sqlstate": getattr(diag, "sqlstate", None),
        "line_no": None,
        "line": None,
        "caret": None,
    }

    if isinstance(exc, psycopg.errors.QueryCanceled):
        details["hint"] = (f"Queries are limited to "
                           f"{STATEMENT_TIMEOUT_MS // 1000} seconds. Add a "
                           f"WHERE clause or a LIMIT.")
    elif isinstance(exc, psycopg.errors.ReadOnlySqlTransaction):
        details["hint"] = ("The console runs every statement in a READ ONLY "
                           "transaction. Use the Consumers and Accounts pages "
                           "to make changes.")

    # statement_position is a 1-based character offset into the SQL.
    position = getattr(diag, "statement_position", None)
    if sql_text and position:
        try:
            offset = int(position) - 1
            before = sql_text[:offset]
            line_no = before.count("\n") + 1
            line_start = before.rfind("\n") + 1
            line_end = sql_text.find("\n", offset)
            if line_end == -1:
                line_end = len(sql_text)
            details["line_no"] = line_no
            details["line"] = sql_text[line_start:line_end]
            details["caret"] = " " * (offset - line_start) + "^"
        except (TypeError, ValueError):
            pass

    return details
