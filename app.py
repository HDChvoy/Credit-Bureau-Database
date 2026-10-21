"""
Deliverable #5 - Experian consumer credit database application
Henry Chvoy, CS727

Deliverable #5 adds the Analytics section (reports defined in queries.py),
a read-only SQL console and CSV export; The "Deliverable #5" sections
are near the bottom of this file. The Deliverable #4 CRUD routes are unchanged.

Deliverable #4:

A Flask web application providing Create, Read, Update and Delete against
the PostgreSQL database built in Deliverable #2. Two entities are exposed:

    Consumer - the simple case. A standalone row with CHECK constraints
               and a cascade that reaches five other tables on delete.

    Account  - the interesting case. It is created through the D2 stored
               procedure sp_open_account rather than a bare INSERT, it is
               reached through the ConsumerAccount junction table rather
               than a foreign key, and updating it fires the D2 audit
               trigger, so every edit made in this app leaves a row in
               AccountAudit.

Every SQL statement in this file is parameterized: values travel to
psycopg in a separate tuple and are never formatted into the query text.

Run with:  flask --app app run
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal

from flask import (Flask, render_template, request, redirect,
                   url_for, flash, abort, Response)
from markupsafe import Markup, escape
import psycopg

import config
import db
import queries
import validation

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY


# =====================================================================
# Dashboard
# =====================================================================

@app.route("/")
def index():
    """Landing page: row counts and the most recent audit activity."""
    try:
        counts = db.query_one("""
            SELECT (SELECT COUNT(*) FROM Consumer)        AS consumers,
                   (SELECT COUNT(*) FROM Account)         AS accounts,
                   (SELECT COUNT(*) FROM Creditor)        AS creditors,
                   (SELECT COUNT(*) FROM PaymentHistory)  AS payment_rows,
                   (SELECT COUNT(*) FROM AccountAudit)    AS audit_rows
        """)
        recent_audit = db.query_all("""
            SELECT aa.AuditID, aa.AccountID, aa.ChangedColumn,
                   aa.OldValue, aa.NewValue, aa.ChangedAt,
                   cr.CreditorName
              FROM AccountAudit aa
              JOIN Account a  ON a.AccountID  = aa.AccountID
              JOIN Creditor cr ON cr.CreditorID = a.CreditorID
             ORDER BY aa.ChangedAt DESC, aa.AuditID DESC
             LIMIT 5
        """)
    except psycopg.Error as exc:
        flash(db.friendly_error(exc), "error")
        return render_template("index.html", counts=None, recent_audit=[])

    return render_template("index.html", counts=counts,
                           recent_audit=recent_audit)


# =====================================================================
# Consumer - READ
# =====================================================================

@app.route("/consumers")
def consumer_list():
    """List consumers, optionally filtered by name.

    The search uses UPPER(LastName) because 03_indexes.sql builds
    idx_consumer_lastname_upper as an expression index on exactly that,
    so a case-insensitive search can still use the index.
    """
    search = (request.args.get("q") or "").strip()

    try:
        if search:
            rows = db.query_all("""
                SELECT c.ConsumerID, c.FirstName, c.LastName, c.YearOfBirth,
                       c.SSN_Masked, c.SecurityFreezeFlag, c.FraudAlertFlag,
                       c.DeceasedFlag,
                       COUNT(ca.AccountID) AS account_count
                  FROM Consumer c
                  LEFT JOIN ConsumerAccount ca ON ca.ConsumerID = c.ConsumerID
                 WHERE UPPER(c.LastName)  LIKE UPPER(%s)
                    OR UPPER(c.FirstName) LIKE UPPER(%s)
                 GROUP BY c.ConsumerID
                 ORDER BY c.LastName, c.FirstName
            """, (f"{search}%", f"{search}%"))
        else:
            rows = db.query_all("""
                SELECT c.ConsumerID, c.FirstName, c.LastName, c.YearOfBirth,
                       c.SSN_Masked, c.SecurityFreezeFlag, c.FraudAlertFlag,
                       c.DeceasedFlag,
                       COUNT(ca.AccountID) AS account_count
                  FROM Consumer c
                  LEFT JOIN ConsumerAccount ca ON ca.ConsumerID = c.ConsumerID
                 GROUP BY c.ConsumerID
                 ORDER BY c.LastName, c.FirstName
            """)
    except psycopg.Error as exc:
        flash(db.friendly_error(exc), "error")
        rows = []

    return render_template("consumers.html", consumers=rows, search=search)


@app.route("/consumers/<int:consumer_id>")
def consumer_detail(consumer_id):
    """One consumer, with their accounts, scores and derived figures.

    The four fn_* calls are the D2 functions. Calling them here rather
    than recomputing the same logic in Python is the whole point of
    having put them in the database.
    """
    try:
        consumer = db.query_one("""
            SELECT c.*,
                   fn_credit_utilization(c.ConsumerID)        AS utilization,
                   fn_average_account_age_months(c.ConsumerID) AS avg_age_months,
                   fn_on_time_payment_pct(c.ConsumerID)       AS on_time_pct
              FROM Consumer c
             WHERE c.ConsumerID = %s
        """, (consumer_id,))

        if consumer is None:
            abort(404)

        accounts = db.query_all("""
            SELECT a.AccountID, a.AccountNumberMasked, a.AccountCategory,
                   a.AccountType, a.AccountStatus, a.PaymentStatus,
                   a.CurrentBalance, a.CreditLimit, a.OriginalLoanAmount,
                   a.PastDueAmount, a.DateOpened,
                   cr.CreditorName,
                   ca.ResponsibilityType,
                   fn_account_purge_date(a.AccountID) AS purge_date
              FROM Account a
              JOIN ConsumerAccount ca ON ca.AccountID  = a.AccountID
              JOIN Creditor cr        ON cr.CreditorID = a.CreditorID
             WHERE ca.ConsumerID = %s
             ORDER BY a.DateOpened DESC
        """, (consumer_id,))

        scores = db.query_all("""
            SELECT ScoreModel, ScoreValue, ScoreDate,
                   fn_score_band(ScoreValue) AS band
              FROM CreditScore
             WHERE ConsumerID = %s
             ORDER BY ScoreDate DESC, ScoreModel
        """, (consumer_id,))

        addresses = db.query_all("""
            SELECT AddressID, StreetLine1, StreetLine2, City, StateCode,
                   PostalCode, AddressType, IsCurrent,
                   FirstReportedDate, LastReportedDate
              FROM Address
             WHERE ConsumerID = %s
             ORDER BY IsCurrent DESC, LastReportedDate DESC
        """, (consumer_id,))

        inquiries = db.query_all("""
            SELECT i.InquiryID, i.InquiryDate, i.InquiryType, i.PurposeType,
                   i.RemovalDate, cr.CreditorName
              FROM Inquiry i
              JOIN Creditor cr ON cr.CreditorID = i.CreditorID
             WHERE i.ConsumerID = %s
             ORDER BY i.InquiryDate DESC
        """, (consumer_id,))

    except psycopg.Error as exc:
        flash(db.friendly_error(exc), "error")
        return redirect(url_for("consumer_list"))

    return render_template("consumer_detail.html", consumer=consumer,
                           accounts=accounts, scores=scores,
                           addresses=addresses, inquiries=inquiries)


# =====================================================================
# Consumer - CREATE
# =====================================================================

@app.route("/consumers/new", methods=["GET", "POST"])
def consumer_new():
    """Add a consumer.

    On a validation failure the submitted values are handed back to the
    template so the user does not have to retype the form.
    """
    if request.method == "GET":
        return render_template("consumer_form.html", consumer={},
                               errors=[], mode="new")

    values, errors = validation.validate_consumer(request.form)

    if errors:
        return render_template("consumer_form.html", consumer=request.form,
                               errors=errors, mode="new"), 400

    try:
        row = db.execute("""
            INSERT INTO Consumer
                (FirstName, MiddleName, LastName, Suffix, SSN_Masked,
                 YearOfBirth, PrimaryPhone, EmailAddress,
                 SecurityFreezeFlag, FreezeStartDate,
                 FraudAlertFlag, DeceasedFlag)
            VALUES (%(first_name)s, %(middle_name)s, %(last_name)s,
                    %(suffix)s, %(ssn_masked)s, %(year_of_birth)s,
                    %(primary_phone)s, %(email_address)s,
                    %(security_freeze_flag)s, %(freeze_start_date)s,
                    %(fraud_alert_flag)s, %(deceased_flag)s)
            RETURNING ConsumerID
        """, values, returning=True)
    except psycopg.Error as exc:
        return render_template("consumer_form.html", consumer=request.form,
                               errors=[db.friendly_error(exc)],
                               mode="new"), 400

    flash(f"Created consumer #{row['consumerid']}: "
          f"{values['first_name']} {values['last_name']}.", "success")
    return redirect(url_for("consumer_detail", consumer_id=row["consumerid"]))


# =====================================================================
# Consumer - UPDATE
# =====================================================================

@app.route("/consumers/<int:consumer_id>/edit", methods=["GET", "POST"])
def consumer_edit(consumer_id):
    """Edit a consumer."""
    if request.method == "GET":
        consumer = db.query_one(
            "SELECT * FROM Consumer WHERE ConsumerID = %s", (consumer_id,))
        if consumer is None:
            abort(404)
        return render_template("consumer_form.html", consumer=consumer,
                               errors=[], mode="edit")

    values, errors = validation.validate_consumer(request.form)
    values["consumer_id"] = consumer_id

    if errors:
        return render_template("consumer_form.html", consumer=request.form,
                               errors=errors, mode="edit",
                               consumer_id=consumer_id), 400

    try:
        rowcount = db.execute("""
            UPDATE Consumer
               SET FirstName          = %(first_name)s,
                   MiddleName         = %(middle_name)s,
                   LastName           = %(last_name)s,
                   Suffix             = %(suffix)s,
                   SSN_Masked         = %(ssn_masked)s,
                   YearOfBirth        = %(year_of_birth)s,
                   PrimaryPhone       = %(primary_phone)s,
                   EmailAddress       = %(email_address)s,
                   SecurityFreezeFlag = %(security_freeze_flag)s,
                   FreezeStartDate    = %(freeze_start_date)s,
                   FraudAlertFlag     = %(fraud_alert_flag)s,
                   DeceasedFlag       = %(deceased_flag)s
             WHERE ConsumerID = %(consumer_id)s
        """, values)
    except psycopg.Error as exc:
        return render_template("consumer_form.html", consumer=request.form,
                               errors=[db.friendly_error(exc)], mode="edit",
                               consumer_id=consumer_id), 400

    # rowcount of 0 means the WHERE matched nothing: somebody deleted the
    # consumer between loading the form and submitting it.
    if rowcount == 0:
        flash("That consumer no longer exists - it may have been deleted "
              "in another window.", "error")
        return redirect(url_for("consumer_list"))

    flash("Consumer updated.", "success")
    return redirect(url_for("consumer_detail", consumer_id=consumer_id))


# =====================================================================
# Consumer - DELETE
# =====================================================================

@app.route("/consumers/<int:consumer_id>/delete", methods=["GET", "POST"])
def consumer_delete(consumer_id):
    """Delete a consumer, after showing what else will go with them.

    Address, ConsumerAccount, Inquiry and CreditScore are all
    ON DELETE CASCADE from Consumer, so this one statement removes rows
    from five tables. The confirmation page counts them first, because a
    cascade the user did not expect is the worst kind of data loss.

    Account rows themselves survive: an account can appear on more than
    one credit file, so deleting one file must not delete the tradeline.
    """
    consumer = db.query_one(
        "SELECT * FROM Consumer WHERE ConsumerID = %s", (consumer_id,))
    if consumer is None:
        abort(404)

    if request.method == "GET":
        cascade = db.query_one("""
            SELECT (SELECT COUNT(*) FROM Address
                     WHERE ConsumerID = %(id)s) AS addresses,
                   (SELECT COUNT(*) FROM ConsumerAccount
                     WHERE ConsumerID = %(id)s) AS account_links,
                   (SELECT COUNT(*) FROM Inquiry
                     WHERE ConsumerID = %(id)s) AS inquiries,
                   (SELECT COUNT(*) FROM CreditScore
                     WHERE ConsumerID = %(id)s) AS scores
        """, {"id": consumer_id})
        return render_template("consumer_delete.html", consumer=consumer,
                               cascade=cascade)

    try:
        rowcount = db.execute(
            "DELETE FROM Consumer WHERE ConsumerID = %s", (consumer_id,))
    except psycopg.Error as exc:
        flash(db.friendly_error(exc), "error")
        return redirect(url_for("consumer_detail", consumer_id=consumer_id))

    if rowcount == 0:
        flash("That consumer no longer exists.", "error")
    else:
        flash(f"Deleted {consumer['firstname']} {consumer['lastname']} "
              f"and all associated addresses, inquiries and scores.",
              "success")
    return redirect(url_for("consumer_list"))


# =====================================================================
# Account - READ
# =====================================================================

@app.route("/accounts")
def account_list():
    """List tradelines with their creditor and the consumers on them."""
    status_filter = (request.args.get("status") or "").strip()

    sql = """
        SELECT a.AccountID, a.AccountNumberMasked, a.AccountCategory,
               a.AccountType, a.AccountStatus, a.PaymentStatus,
               a.CurrentBalance, a.CreditLimit, a.OriginalLoanAmount,
               a.PastDueAmount, a.DateOpened,
               cr.CreditorName,
               COUNT(ca.ConsumerID) AS holder_count,
               -- The consumer ID is appended because the seed data
               -- deliberately contains a father and son with the same
               -- name at the same address. Without the ID, a joint
               -- account between them reads as the same person twice.
               STRING_AGG(co.FirstName || ' ' || co.LastName
                          || ' (#' || co.ConsumerID || ')', ', '
                          ORDER BY co.LastName) AS holders
          FROM Account a
          JOIN Creditor cr        ON cr.CreditorID = a.CreditorID
          LEFT JOIN ConsumerAccount ca ON ca.AccountID = a.AccountID
          LEFT JOIN Consumer co   ON co.ConsumerID = ca.ConsumerID
    """
    params = ()
    if status_filter:
        sql += " WHERE a.AccountStatus = %s"
        params = (status_filter,)
    sql += """
         GROUP BY a.AccountID, cr.CreditorName
         ORDER BY a.DateOpened DESC
    """

    try:
        rows = db.query_all(sql, params)
    except psycopg.Error as exc:
        flash(db.friendly_error(exc), "error")
        rows = []

    return render_template("accounts.html", accounts=rows,
                           status_filter=status_filter,
                           statuses=validation.ACCOUNT_STATUSES)


@app.route("/accounts/<int:account_id>")
def account_detail(account_id):
    """One tradeline, with its holders, recent payment history and audit trail."""
    try:
        account = db.query_one("""
            SELECT a.*, cr.CreditorName, cr.BusinessType,
                   orig.CreditorName AS OriginalCreditorName,
                   fn_account_purge_date(a.AccountID) AS purge_date
              FROM Account a
              JOIN Creditor cr        ON cr.CreditorID = a.CreditorID
              LEFT JOIN Creditor orig ON orig.CreditorID = a.OriginalCreditorID
             WHERE a.AccountID = %s
        """, (account_id,))

        if account is None:
            abort(404)

        holders = db.query_all("""
            SELECT c.ConsumerID, c.FirstName, c.LastName,
                   ca.ResponsibilityType, ca.DateAssociated, ca.DateRemoved
              FROM ConsumerAccount ca
              JOIN Consumer c ON c.ConsumerID = ca.ConsumerID
             WHERE ca.AccountID = %s
             ORDER BY ca.ResponsibilityType, c.LastName
        """, (account_id,))

        history = db.query_all("""
            SELECT ReportMonth, StatusCode, BalanceAmount,
                   ScheduledPaymentAmount
              FROM PaymentHistory
             WHERE AccountID = %s
             ORDER BY ReportMonth DESC
             LIMIT 12
        """, (account_id,))

        audit = db.query_all("""
            SELECT AuditID, ChangedColumn, OldValue, NewValue,
                   ChangedAt, ChangedBy
              FROM AccountAudit
             WHERE AccountID = %s
             ORDER BY ChangedAt DESC, AuditID DESC
        """, (account_id,))

    except psycopg.Error as exc:
        flash(db.friendly_error(exc), "error")
        return redirect(url_for("account_list"))

    return render_template("account_detail.html", account=account,
                           holders=holders, history=history, audit=audit)


# =====================================================================
# Account - CREATE
# =====================================================================

@app.route("/accounts/new", methods=["GET", "POST"])
def account_new():
    """Open a tradeline by calling the D2 stored procedure sp_open_account.

    A bare INSERT into Account would create a tradeline with no owner,
    because ownership lives in ConsumerAccount. The procedure writes both
    rows in one transaction, which is exactly the case it was written for,
    so the application calls it rather than reimplementing it.
    """
    if request.method == "GET":
        return render_template("account_form.html", account={}, errors=[],
                               mode="new", **_account_form_options())

    values, errors = validation.validate_new_account(request.form)

    if errors:
        return render_template("account_form.html", account=request.form,
                               errors=errors, mode="new",
                               **_account_form_options()), 400

    try:
        db.call_procedure("""
            CALL sp_open_account(%(consumer_id)s, %(creditor_id)s,
                                 %(account_number_masked)s,
                                 %(account_category)s, %(account_type)s,
                                 %(date_opened)s, %(limit_or_amount)s,
                                 %(monthly_payment)s,
                                 %(responsibility_type)s,
                                 %(terms_months)s)
        """, values)
    except psycopg.Error as exc:
        return render_template("account_form.html", account=request.form,
                               errors=[db.friendly_error(exc)], mode="new",
                               **_account_form_options()), 400

    flash("Tradeline opened.", "success")
    return redirect(url_for("consumer_detail",
                            consumer_id=values["consumer_id"]))


# =====================================================================
# Account - UPDATE
# =====================================================================

@app.route("/accounts/<int:account_id>/edit", methods=["GET", "POST"])
def account_edit(account_id):
    """Edit a tradeline.

    PaymentStatus and PastDueAmount are deliberately NOT editable here.
    Trigger trg_sync_account_status derives both from the newest
    PaymentHistory row, so anything this form wrote to them would be
    overwritten the next time a payment was reported - and setting
    PastDueAmount by hand can violate chk_account_pastdue_agrees.

    Every successful update here fires trg_account_audit, which writes one
    AccountAudit row per changed column. The audit trail on the detail
    page is produced entirely by the database, not by this function.
    """
    account = db.query_one(
        "SELECT * FROM Account WHERE AccountID = %s", (account_id,))
    if account is None:
        abort(404)

    if request.method == "GET":
        return render_template("account_form.html", account=account,
                               errors=[], mode="edit",
                               **_account_form_options())

    values, errors = validation.validate_account_update(
        request.form, account["accountcategory"])
    values["account_id"] = account_id

    if errors:
        # Merge the submitted values over the stored row so the form
        # redisplays what the user typed while keeping the fields the
        # form does not carry.
        redisplay = dict(account)
        redisplay.update(request.form)
        return render_template("account_form.html", account=redisplay,
                               errors=errors, mode="edit",
                               **_account_form_options()), 400

    try:
        rowcount = db.execute("""
            UPDATE Account
               SET CurrentBalance     = %(current_balance)s,
                   CreditLimit        = %(credit_limit)s,
                   OriginalLoanAmount = %(original_loan_amount)s,
                   MonthlyPayment     = %(monthly_payment)s,
                   AccountStatus      = %(account_status)s,
                   DateClosed         = %(date_closed)s
             WHERE AccountID = %(account_id)s
        """, values)
    except psycopg.Error as exc:
        redisplay = dict(account)
        redisplay.update(request.form)
        return render_template("account_form.html", account=redisplay,
                               errors=[db.friendly_error(exc)], mode="edit",
                               **_account_form_options()), 400

    if rowcount == 0:
        flash("That account no longer exists.", "error")
        return redirect(url_for("account_list"))

    flash("Account updated. Changes are recorded in the audit trail below.",
          "success")
    return redirect(url_for("account_detail", account_id=account_id))


# =====================================================================
# Account - DELETE
# =====================================================================

@app.route("/accounts/<int:account_id>/delete", methods=["GET", "POST"])
def account_delete(account_id):
    """Delete a tradeline, after showing what goes with it.

    PaymentHistory is a weak entity identified by AccountID, so it is
    ON DELETE CASCADE and disappears with the account. ConsumerAccount
    links go too. The Creditor does not: that foreign key is
    ON DELETE RESTRICT in the other direction.
    """
    account = db.query_one("""
        SELECT a.*, cr.CreditorName
          FROM Account a
          JOIN Creditor cr ON cr.CreditorID = a.CreditorID
         WHERE a.AccountID = %s
    """, (account_id,))
    if account is None:
        abort(404)

    if request.method == "GET":
        cascade = db.query_one("""
            SELECT (SELECT COUNT(*) FROM PaymentHistory
                     WHERE AccountID = %(id)s) AS payment_rows,
                   (SELECT COUNT(*) FROM ConsumerAccount
                     WHERE AccountID = %(id)s) AS holders,
                   (SELECT COUNT(*) FROM AccountAudit
                     WHERE AccountID = %(id)s) AS audit_rows
        """, {"id": account_id})
        return render_template("account_delete.html", account=account,
                               cascade=cascade)

    try:
        rowcount = db.execute(
            "DELETE FROM Account WHERE AccountID = %s", (account_id,))
    except psycopg.Error as exc:
        flash(db.friendly_error(exc), "error")
        return redirect(url_for("account_detail", account_id=account_id))

    if rowcount == 0:
        flash("That account no longer exists.", "error")
    else:
        flash(f"Deleted the {account['creditorname']} tradeline and its "
              f"payment history.", "success")
    return redirect(url_for("account_list"))


# =====================================================================
# Audit trail
# =====================================================================

@app.route("/audit")
def audit_log():
    """The AccountAudit table, newest first.

    Nothing in this application writes to AccountAudit. Every row on this
    page was produced by trigger trg_account_audit firing on an UPDATE
    that the Edit account form issued.
    """
    try:
        rows = db.query_all("""
            SELECT aa.AuditID, aa.AccountID, aa.ChangedColumn,
                   aa.OldValue, aa.NewValue, aa.ChangedAt, aa.ChangedBy,
                   cr.CreditorName, a.AccountNumberMasked
              FROM AccountAudit aa
              JOIN Account a   ON a.AccountID  = aa.AccountID
              JOIN Creditor cr ON cr.CreditorID = a.CreditorID
             ORDER BY aa.ChangedAt DESC, aa.AuditID DESC
             LIMIT 100
        """)
    except psycopg.Error as exc:
        flash(db.friendly_error(exc), "error")
        rows = []

    return render_template("audit.html", audit=rows)


# =====================================================================
# Deliverable #5 - Analytics
# =====================================================================
#
# The reports themselves live in queries.py. These routes are generic:
# look the report up, validate its inputs, run it read-only, render.
# Adding a report means adding an entry to queries.py, not a route here.

# Results tables are capped so a console query against PaymentHistory
# cannot render thousands of rows into one page.
CONSOLE_MAX_ROWS = 500


def _consumer_options():
    """Consumers for the report dropdowns, with suffix so Jr and Sr differ."""
    return db.query_all("""
        SELECT ConsumerID,
               CONCAT_WS(' ', FirstName, LastName, Suffix) AS name
          FROM Consumer
         ORDER BY LastName, FirstName, Suffix
    """)


def _report_or_404(query_id):
    query = queries.QUERIES_BY_ID.get(query_id)
    if query is None:
        abort(404)
    return query


@app.route("/analytics")
def analytics_home():
    """Overview: the six categories and the reports in each."""
    sections = [
        {"category": c, "reports": queries.queries_in(c["key"])}
        for c in queries.CATEGORIES
    ]
    return render_template("analytics_home.html", sections=sections,
                           total=len(queries.QUERIES))


@app.route("/analytics/<query_id>")
def analytics_report(query_id):
    """Run one report and show its results, SQL and explanation.

    Inputs arrive on the query string (the form uses GET), so every
    result is a shareable URL and the browser's back button works.
    The report runs on page load with default inputs, so opening a
    report always shows data immediately.
    """
    query = _report_or_404(query_id)

    try:
        consumers = _consumer_options() if any(
            p["type"] == "consumer" for p in query["params"]) else []
    except psycopg.Error as exc:
        flash(db.friendly_error(exc), "error")
        consumers = []

    values, errors = validation.validate_report_params(
        query, request.args, {c["consumerid"] for c in consumers})

    result, sql_error = None, None
    try:
        columns, rows, elapsed_ms, _ = db.run_report(
            query["sql"], values if query["params"] else None)
        result = {"columns": columns, "rows": rows, "elapsed_ms": elapsed_ms}
    except psycopg.Error as exc:
        sql_error = db.sql_error_details(exc, query["sql"])

    category = queries.CATEGORIES_BY_KEY[query["category"]]
    return render_template(
        "analytics_report.html", query=query, category=category,
        siblings=queries.queries_in(query["category"]),
        categories=queries.CATEGORIES, all_queries=queries.QUERIES,
        values=values, errors=errors, consumers=consumers,
        result=result, sql_error=sql_error)


@app.route("/analytics/<query_id>.csv")
def analytics_csv(query_id):
    """Download a report's results as CSV, with the same inputs as the page."""
    query = _report_or_404(query_id)

    try:
        consumer_ids = {c["consumerid"] for c in _consumer_options()}
        values, errors = validation.validate_report_params(
            query, request.args, consumer_ids)
        if errors:
            flash(" ".join(errors), "error")
            return redirect(url_for("analytics_report", query_id=query_id))
        columns, rows, _, _ = db.run_report(
            query["sql"], values if query["params"] else None)
    except psycopg.Error as exc:
        flash(db.friendly_error(exc), "error")
        return redirect(url_for("analytics_report", query_id=query_id))

    # The _level column is a display aid for subtotal rows; keep it in
    # the CSV but give it a name that means something in a spreadsheet.
    header = ["grouping_level" if c == "_level" else c for c in columns]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition":
                 f"attachment; filename={query_id}.csv"})


@app.route("/console", methods=["GET", "POST"])
def sql_console():
    """Run an ad-hoc read-only query.

    Safety is enforced by PostgreSQL, not by string inspection: the
    statement runs inside a READ ONLY transaction with a statement
    timeout (see db.run_report). validate_console_sql only exists to
    give a friendlier message before the round trip.

    GET ?from=<report id> pre-fills the editor with that report's SQL,
    with its parameters filled in, so any report can be modified and
    re-run here.
    """
    sql_text, errors, result, sql_error = "", [], None, None

    if request.method == "GET":
        source = queries.QUERIES_BY_ID.get(request.args.get("from", ""))
        if source:
            if source["params"]:
                try:
                    consumer_ids = {c["consumerid"] for c in _consumer_options()}
                    values, _ = validation.validate_report_params(
                        source, request.args, consumer_ids)
                    sql_text = db.inline_params(source["sql"], values)
                except psycopg.Error as exc:
                    flash(db.friendly_error(exc), "error")
            else:
                sql_text = source["sql"]
        else:
            sql_text = ("SELECT ConsumerName, CurrentScore, ScoreBand, "
                        "UtilizationPct\n  FROM vw_consumer_credit_summary\n"
                        " ORDER BY CurrentScore DESC;")
    else:
        sql_text, errors = validation.validate_console_sql(
            request.form.get("sql"))
        if not errors:
            try:
                columns, rows, elapsed_ms, truncated = db.run_report(
                    sql_text, None, max_rows=CONSOLE_MAX_ROWS)
                result = {"columns": columns, "rows": rows,
                          "elapsed_ms": elapsed_ms, "truncated": truncated}
            except psycopg.Error as exc:
                sql_error = db.sql_error_details(exc, sql_text)

    page = render_template("console.html", sql_text=sql_text,
                           errors=errors, result=result, sql_error=sql_error,
                           max_rows=CONSOLE_MAX_ROWS,
                           examples=queries.QUERIES,
                           templates=queries.CONSOLE_TEMPLATES)
    return page, (400 if (errors or sql_error) else 200)


# =====================================================================
# Template filters for the results tables
# =====================================================================

SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "JOIN", "LEFT", "ON", "AND", "OR", "NOT",
    "IN", "EXISTS", "AS", "GROUP", "BY", "ORDER", "HAVING", "UNION",
    "INTERSECT", "EXCEPT", "ALL", "SOME", "ANY", "WITH", "RECURSIVE",
    "DISTINCT", "CASE", "WHEN", "THEN", "ELSE", "END", "OVER", "PARTITION",
    "WINDOW", "ROWS", "UNBOUNDED", "PRECEDING", "ROLLUP", "CUBE",
    "FILTER", "WITHIN", "IS", "NULL", "DESC", "ASC", "LIMIT", "INTERVAL",
    "DATE", "COALESCE", "COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND",
    "STRING_AGG", "RANK", "DENSE_RANK", "NTILE", "PERCENT_RANK", "LAG",
    "FIRST_VALUE", "PERCENTILE_CONT", "MODE", "STDDEV_SAMP", "GROUPING",
    "CONCAT_WS", "TO_CHAR", "ABS", "BETWEEN", "LIKE", "CURRENT_DATE",
}
_SQL_TOKEN = re.compile(
    r"(--[^\n]*)"                 # comment
    r"|('(?:[^']|'')*')"          # string literal
    r"|(\"[^\"]*\")"              # quoted identifier (display names)
    r"|(%\(\w+\)s)"               # psycopg placeholder
    r"|([A-Za-z_][A-Za-z_0-9]*)"  # word
    r"|(\s+|.)",                  # anything else, one char at a time
    re.DOTALL)


@app.template_filter("sql_highlight")
def sql_highlight(text):
    """Colour SQL for display. Every token is HTML-escaped before wrapping."""
    out = []
    for m in _SQL_TOKEN.finditer(text or ""):
        comment, string, ident, param, word, other = m.groups()
        if comment:
            out.append(f'<span class="sq-c">{escape(comment)}</span>')
        elif string:
            out.append(f'<span class="sq-s">{escape(string)}</span>')
        elif ident:
            out.append(f'<span class="sq-i">{escape(ident)}</span>')
        elif param:
            out.append(f'<span class="sq-p">{escape(param)}</span>')
        elif word:
            if word.upper() in SQL_KEYWORDS:
                out.append(f'<span class="sq-k">{escape(word)}</span>')
            elif word.lower().startswith(("fn_", "sp_", "vw_")):
                out.append(f'<span class="sq-f">{escape(word)}</span>')
            else:
                out.append(str(escape(word)))
        else:
            out.append(str(escape(other)))
    return Markup("".join(out))


@app.template_filter("cell")
def format_cell(value):
    """Format one result value for the table."""
    if value is None:
        return Markup('<span class="null">&mdash;</span>')
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.1f}" if value % 1 else f"{int(value):,}"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


@app.template_test("numeric")
def is_numeric(value):
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


# =====================================================================
# Helpers and error pages
# =====================================================================

def _account_form_options():
    """Dropdown contents for the account forms.

    Offering only the values the CHECK constraints allow means most
    invalid input cannot be submitted in the first place.
    """
    try:
        consumers = db.query_all("""
            SELECT ConsumerID, FirstName, LastName, SecurityFreezeFlag
              FROM Consumer
             ORDER BY LastName, FirstName
        """)
        creditors = db.query_all("""
            SELECT CreditorID, CreditorName, BusinessType
              FROM Creditor
             ORDER BY CreditorName
        """)
    except psycopg.Error:
        consumers, creditors = [], []

    return {
        "consumers": consumers,
        "creditors": creditors,
        "categories": validation.ACCOUNT_CATEGORIES,
        "statuses": validation.ACCOUNT_STATUSES,
        "responsibilities": validation.RESPONSIBILITY_TYPES,
    }


@app.context_processor
def template_globals():
    """Values every template can use without each route passing them."""
    nav_categories = [
        {**c,
         "count": len(queries.queries_in(c["key"])),
         "first_query": queries.queries_in(c["key"])[0]["id"]}
        for c in queries.CATEGORIES
    ]
    return {"current_year": date.today().year,
            "nav_categories": nav_categories}


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html",
                           code=404,
                           message="That record does not exist."), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template("error.html",
                           code=500,
                           message="Something went wrong handling that "
                                   "request."), 500


if __name__ == "__main__":
    app.run(debug=True)
