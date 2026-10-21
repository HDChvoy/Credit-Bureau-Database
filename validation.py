"""
Form validation.

The database already enforces these rules, so why check them here too?
Because a CHECK constraint can only reject the whole statement after the
user has submitted it, and it rejects it with a constraint name. Checking
first means the user gets "Year of birth must be a number" pointing at the
field they got wrong, instead of a transaction that aborted.

The database checks stay as the real guarantee. This layer is for the
user's benefit, not the data's - anything that slips past it still gets
caught by Postgres and translated by db.friendly_error().

Every function here returns a list of error strings. Empty list means the
input was acceptable.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

# Mirrors chk_consumer_ssn_format in 01_ddl.sql.
SSN_PATTERN = re.compile(r"^XXX-XX-\d{4}$")

# Mirrors the CHECK constraint value lists in 01_ddl.sql. Kept here as
# well so the form can render them as dropdowns, which stops most invalid
# values from ever being submitted.
ACCOUNT_CATEGORIES = ["Revolving", "Installment", "Open", "Collection"]
ACCOUNT_STATUSES = ["Open", "Closed", "Transferred", "Paid"]
RESPONSIBILITY_TYPES = ["Individual", "Joint", "Cosigner", "Authorized User"]
ADDRESS_TYPES = ["Residential", "Mailing", "Business", "PO Box"]


def parse_decimal(value, field_name, errors, required=False, allow_zero=True):
    """Convert a form string to a Decimal, recording a message if it isn't one.

    Returns None for blank input so the caller can pass a real SQL NULL
    rather than an empty string, which is what the nullable money columns
    on Account expect.
    """
    value = (value or "").strip().replace(",", "").replace("$", "")
    if not value:
        if required:
            errors.append(f"{field_name} is required.")
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        errors.append(f"{field_name} must be a number.")
        return None
    if parsed < 0:
        errors.append(f"{field_name} cannot be negative.")
        return None
    if not allow_zero and parsed == 0:
        errors.append(f"{field_name} must be greater than zero.")
        return None
    return parsed


def parse_date(value, field_name, errors, required=False, allow_future=False):
    """Convert a form string to a date, recording a message if it isn't one."""
    value = (value or "").strip()
    if not value:
        if required:
            errors.append(f"{field_name} is required.")
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{field_name} must be a date in YYYY-MM-DD form.")
        return None
    if not allow_future and parsed > date.today():
        errors.append(f"{field_name} cannot be in the future.")
        return None
    return parsed


def parse_int(value, field_name, errors, required=False):
    """Convert a form string to an int, recording a message if it isn't one."""
    value = (value or "").strip()
    if not value:
        if required:
            errors.append(f"{field_name} is required.")
        return None
    try:
        return int(value)
    except ValueError:
        errors.append(f"{field_name} must be a whole number.")
        return None


def validate_consumer(form):
    """Check the consumer form and return (values, errors).

    values is a dict ready to hand to the INSERT or UPDATE. It is only
    meaningful when errors is empty.
    """
    errors = []

    first_name = (form.get("first_name") or "").strip()
    last_name = (form.get("last_name") or "").strip()
    middle_name = (form.get("middle_name") or "").strip() or None
    suffix = (form.get("suffix") or "").strip() or None
    ssn_masked = (form.get("ssn_masked") or "").strip()
    phone = (form.get("primary_phone") or "").strip() or None
    email = (form.get("email_address") or "").strip() or None

    if not first_name:
        errors.append("First name is required.")
    elif len(first_name) > 40:
        errors.append("First name cannot be longer than 40 characters.")

    if not last_name:
        errors.append("Last name is required.")
    elif len(last_name) > 40:
        errors.append("Last name cannot be longer than 40 characters.")

    if middle_name and len(middle_name) > 40:
        errors.append("Middle name cannot be longer than 40 characters.")

    if suffix and len(suffix) > 10:
        errors.append("Suffix cannot be longer than 10 characters.")

    # The schema stores only the last four digits. If the user types a
    # bare four digits, accept it and mask it for them rather than
    # bouncing the form - the point of the rule is that a full SSN is
    # never stored, and helping them comply serves that better than a
    # rejection would.
    if re.fullmatch(r"\d{4}", ssn_masked):
        ssn_masked = f"XXX-XX-{ssn_masked}"
    if not SSN_PATTERN.match(ssn_masked):
        errors.append("SSN must be the last four digits only, entered as "
                      "1234 or XXX-XX-1234. Full SSNs are not stored.")

    year_of_birth = parse_int(form.get("year_of_birth"), "Year of birth",
                              errors, required=True)
    if year_of_birth is not None:
        if not (1900 <= year_of_birth <= date.today().year):
            errors.append(f"Year of birth must be between 1900 and "
                          f"{date.today().year}.")

    if email and "@" not in email:
        errors.append("Email address does not look like an email address.")
    if email and len(email) > 120:
        errors.append("Email address cannot be longer than 120 characters.")
    if phone and len(phone) > 20:
        errors.append("Phone number cannot be longer than 20 characters.")

    # chk_consumer_freeze_date: the flag and the date have to agree.
    security_freeze = form.get("security_freeze_flag") == "on"
    freeze_start = parse_date(form.get("freeze_start_date"),
                              "Freeze start date", errors)
    if security_freeze and freeze_start is None:
        errors.append("A security freeze needs a freeze start date.")
    if not security_freeze and freeze_start is not None:
        errors.append("Freeze start date can only be set when the security "
                      "freeze is switched on.")

    values = {
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "suffix": suffix,
        "ssn_masked": ssn_masked,
        "year_of_birth": year_of_birth,
        "primary_phone": phone,
        "email_address": email,
        "security_freeze_flag": security_freeze,
        "freeze_start_date": freeze_start,
        "fraud_alert_flag": form.get("fraud_alert_flag") == "on",
        "deceased_flag": form.get("deceased_flag") == "on",
    }
    return values, errors


def validate_new_account(form):
    """Check the new-account form and return (values, errors).

    The values line up with the parameters of sp_open_account, which is
    the D2 stored procedure this form calls.
    """
    errors = []

    consumer_id = parse_int(form.get("consumer_id"), "Consumer", errors,
                            required=True)
    creditor_id = parse_int(form.get("creditor_id"), "Creditor", errors,
                            required=True)

    account_number = (form.get("account_number_masked") or "").strip()
    if not account_number:
        errors.append("Account number is required.")
    elif len(account_number) > 20:
        errors.append("Account number cannot be longer than 20 characters.")

    category = (form.get("account_category") or "").strip()
    if category not in ACCOUNT_CATEGORIES:
        errors.append("Account category must be one of: "
                      + ", ".join(ACCOUNT_CATEGORIES) + ".")

    account_type = (form.get("account_type") or "").strip()
    if not account_type:
        errors.append("Account type is required.")
    elif len(account_type) > 30:
        errors.append("Account type cannot be longer than 30 characters.")

    date_opened = parse_date(form.get("date_opened"), "Date opened", errors,
                             required=True)

    # sp_open_account takes one amount and decides from the category
    # whether it becomes CreditLimit or OriginalLoanAmount. That is what
    # keeps chk_account_amount_disjoint satisfied.
    limit_or_amount = parse_decimal(form.get("limit_or_amount"),
                                    "Credit limit / loan amount", errors)
    if category in ("Revolving", "Installment") and limit_or_amount is None:
        label = ("Credit limit" if category == "Revolving"
                 else "Original loan amount")
        errors.append(f"{label} is required for a {category.lower()} account.")

    monthly_payment = parse_decimal(form.get("monthly_payment"),
                                    "Monthly payment", errors)

    responsibility = (form.get("responsibility_type") or "Individual").strip()
    if responsibility not in RESPONSIBILITY_TYPES:
        errors.append("Responsibility must be one of: "
                      + ", ".join(RESPONSIBILITY_TYPES) + ".")

    terms_months = parse_int(form.get("terms_months"), "Term in months", errors)
    if terms_months is not None and not (0 < terms_months <= 600):
        errors.append("Term in months must be between 1 and 600.")

    # sp_open_account has no parameter for an original creditor, so it
    # cannot satisfy chk_account_collection_origin. Saying so here is
    # clearer than letting the procedure fail on the constraint.
    if category == "Collection":
        errors.append("Collection accounts are created by the "
                      "sp_transfer_to_collections procedure, not by opening a "
                      "new tradeline. Use Transfer to collections on the "
                      "existing account instead.")

    values = {
        "consumer_id": consumer_id,
        "creditor_id": creditor_id,
        "account_number_masked": account_number,
        "account_category": category,
        "account_type": account_type,
        "date_opened": date_opened,
        "limit_or_amount": limit_or_amount,
        "monthly_payment": monthly_payment,
        "responsibility_type": responsibility,
        "terms_months": terms_months,
    }
    return values, errors


def validate_account_update(form, category):
    """Check the edit-account form and return (values, errors).

    `category` comes from the existing row rather than the form: the
    category decides which amount column is legal, and letting the user
    change it would mean moving money between two columns that
    chk_account_amount_disjoint says cannot both be populated.
    """
    errors = []

    current_balance = parse_decimal(form.get("current_balance"),
                                    "Current balance", errors, required=True)

    credit_limit = None
    original_loan_amount = None
    if category == "Revolving":
        credit_limit = parse_decimal(form.get("credit_limit"),
                                     "Credit limit", errors, required=True)
    elif category == "Installment":
        original_loan_amount = parse_decimal(form.get("original_loan_amount"),
                                             "Original loan amount", errors,
                                             required=True)

    monthly_payment = parse_decimal(form.get("monthly_payment"),
                                    "Monthly payment", errors)

    account_status = (form.get("account_status") or "").strip()
    if account_status not in ACCOUNT_STATUSES:
        errors.append("Account status must be one of: "
                      + ", ".join(ACCOUNT_STATUSES) + ".")

    date_closed = parse_date(form.get("date_closed"), "Date closed", errors)

    # chk_account_closed_has_date
    if account_status == "Closed" and date_closed is None:
        errors.append("An account marked Closed needs a closing date.")
    if account_status != "Closed" and date_closed is not None:
        errors.append("Only a closed account can have a closing date.")

    values = {
        "current_balance": current_balance,
        "credit_limit": credit_limit,
        "original_loan_amount": original_loan_amount,
        "monthly_payment": monthly_payment,
        "account_status": account_status,
        "date_closed": date_closed,
    }
    return values, errors


# =====================================================================
# Deliverable #5: analytics parameters and the SQL console
# =====================================================================

def validate_report_params(query, args, consumer_ids):
    """Check the user-adjustable inputs of one analytics report.

    `query` is an entry from queries.QUERIES, `args` is request.args,
    and `consumer_ids` is the set of IDs that actually exist, so a
    hand-edited URL asking for consumer 9999 gets a sentence rather than
    an empty result that looks like a bug.

    Returns (values, errors). Blank inputs fall back to the default, so
    a report always opens with something on screen.
    """
    values, errors = {}, []

    for p in query["params"]:
        raw = (args.get(p["name"]) or "").strip()
        if raw == "":
            values[p["name"]] = p["default"]
            continue

        if p["type"] in ("int", "consumer"):
            try:
                number = int(raw)
            except ValueError:
                errors.append(f"{p['label']} must be a whole number "
                              f"(you entered \"{raw}\").")
                values[p["name"]] = p["default"]
                continue

            if p["type"] == "int" and not p["min"] <= number <= p["max"]:
                errors.append(f"{p['label']} must be between {p['min']} "
                              f"and {p['max']}.")
                values[p["name"]] = p["default"]
                continue

            if p["type"] == "consumer" and number not in consumer_ids:
                errors.append(f"There is no consumer #{number}.")
                values[p["name"]] = p["default"]
                continue

            values[p["name"]] = number

        elif p["type"] == "choice":
            if raw not in p["choices"]:
                errors.append(f"{p['label']} must be one of: "
                              f"{', '.join(p['choices'])}.")
                values[p["name"]] = p["default"]
                continue
            values[p["name"]] = raw

    return values, errors


# The console accepts one read-only statement. These checks are for a
# helpful message; the READ ONLY transaction in db.run_report is the
# actual enforcement and would refuse a write however it was disguised.
CONSOLE_MAX_LENGTH = 10000
CONSOLE_ALLOWED_START = ("SELECT", "WITH", "VALUES", "TABLE", "EXPLAIN")
_LEADING_COMMENTS = re.compile(r"^(\s*(--[^\n]*\n?|/\*.*?\*/))*\s*", re.DOTALL)
# Comments and quoted text, so a ';' inside them is not mistaken for a
# second statement.
_COMMENTS_AND_STRINGS = re.compile(
    r"--[^\n]*|/\*.*?\*/|'(?:[^']|'')*'|\"[^\"]*\"", re.DOTALL)


def validate_console_sql(text):
    """Return (cleaned_sql, errors) for a statement typed into the console."""
    errors = []
    sql_text = (text or "").strip()

    if not sql_text:
        return "", ["Type a query to run."]

    if len(sql_text) > CONSOLE_MAX_LENGTH:
        return sql_text, [f"Queries are limited to {CONSOLE_MAX_LENGTH:,} "
                          f"characters."]

    # One trailing semicolon is normal habit from psql; allow it.
    sql_text = sql_text.rstrip(";").rstrip()

    if ";" in _COMMENTS_AND_STRINGS.sub("", sql_text):
        errors.append("Run one statement at a time - remove the semicolon "
                      "in the middle of the query.")

    body = _LEADING_COMMENTS.sub("", sql_text, count=1)
    first_word = body.split(None, 1)[0].upper() if body else ""
    if first_word and first_word not in CONSOLE_ALLOWED_START:
        errors.append(f"The console only runs queries (SELECT or WITH). "
                      f"\"{first_word}\" statements change data - use the "
                      f"Consumers and Accounts pages for that.")

    return sql_text, errors
