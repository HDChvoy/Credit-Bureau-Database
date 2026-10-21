-- =====================================================================
-- Deliverable #2, Task 7: Stored procedures
--
-- Procedures (as opposed to functions) are used where the operation
-- changes data and manages its own transaction. Each one wraps a
-- multi-statement business process that must not be left half done.
-- =====================================================================

-- ---------------------------------------------------------------------
-- sp_open_account
--
-- Opening a tradeline is two writes that must succeed together: the
-- Account row, and the ConsumerAccount row that attaches it to a
-- credit file. An Account with no owner is invisible on every report,
-- so committing the first without the second silently loses data.
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_open_account(
    p_consumer_id     INTEGER,
    p_creditor_id     INTEGER,
    p_acct_number     VARCHAR(20),
    p_category        VARCHAR(15),
    p_type            VARCHAR(30),
    p_date_opened     DATE,
    p_limit_or_amount NUMERIC(12,2),
    p_monthly_payment NUMERIC(10,2),
    p_responsibility  VARCHAR(20) DEFAULT 'Individual',
    p_terms_months    SMALLINT    DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_account_id INTEGER;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM Consumer WHERE ConsumerID = p_consumer_id) THEN
        RAISE EXCEPTION 'Consumer % does not exist', p_consumer_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    IF EXISTS (SELECT 1 FROM Consumer
                WHERE ConsumerID = p_consumer_id AND SecurityFreezeFlag) THEN
        RAISE EXCEPTION
            'Consumer % has a security freeze; new tradelines cannot be added',
            p_consumer_id;
    END IF;

    INSERT INTO Account (
        CreditorID, AccountNumberMasked, AccountCategory, AccountType,
        DateOpened, TermsMonths, CreditLimit, OriginalLoanAmount,
        CurrentBalance, MonthlyPayment, PaymentStatus, PaymentStatusDate,
        DateLastActivity, AccountStatus)
    VALUES (
        p_creditor_id, p_acct_number, p_category, p_type,
        p_date_opened, p_terms_months,
        CASE WHEN p_category = 'Revolving'   THEN p_limit_or_amount END,
        CASE WHEN p_category = 'Installment' THEN p_limit_or_amount END,
        CASE WHEN p_category = 'Installment' THEN p_limit_or_amount ELSE 0 END,
        p_monthly_payment, 'Current', p_date_opened,
        p_date_opened, 'Open')
    RETURNING AccountID INTO v_account_id;

    INSERT INTO ConsumerAccount
        (ConsumerID, AccountID, ResponsibilityType, DateAssociated)
    VALUES (p_consumer_id, v_account_id, p_responsibility, p_date_opened);

    RAISE NOTICE 'Opened account % for consumer % (% / %)',
                 v_account_id, p_consumer_id, p_category, p_responsibility;
END;
$$;


-- ---------------------------------------------------------------------
-- sp_record_monthly_payment
--
-- The furnisher-facing entry point. Writes one PaymentHistory row;
-- trigger trg_sync_account_status then propagates the new status and
-- past-due amount up to Account. The balance is updated here rather
-- than in the trigger because only the furnisher knows it.
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_record_monthly_payment(
    p_account_id  INTEGER,
    p_month       DATE,
    p_status_code VARCHAR(4),
    p_balance     NUMERIC(12,2)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_month DATE := DATE_TRUNC('month', p_month)::DATE;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM Account WHERE AccountID = p_account_id) THEN
        RAISE EXCEPTION 'Account % does not exist', p_account_id;
    END IF;

    -- Re-reporting an already-reported month is a correction, not an
    -- error: furnishers restate history routinely.
    INSERT INTO PaymentHistory
        (AccountID, ReportMonth, StatusCode, BalanceAmount, ScheduledPaymentAmount)
    VALUES (p_account_id, v_month, p_status_code, p_balance,
            (SELECT MonthlyPayment FROM Account WHERE AccountID = p_account_id))
    ON CONFLICT (AccountID, ReportMonth) DO UPDATE
        SET StatusCode    = EXCLUDED.StatusCode,
            BalanceAmount = EXCLUDED.BalanceAmount;

    UPDATE Account
       SET CurrentBalance = p_balance
     WHERE AccountID = p_account_id;

    RAISE NOTICE 'Recorded % for account % month %',
                 p_status_code, p_account_id, v_month;
END;
$$;


-- ---------------------------------------------------------------------
-- sp_transfer_to_collections
--
-- A charged-off debt sold to an agency becomes a NEW account held by
-- the agency, with the original lender recorded as OriginalCreditorID.
-- The old tradeline is closed rather than deleted: the consumer's
-- history of it is precisely what the report is for.
--
-- This is the operation that makes the two Creditor foreign keys on
-- Account earn their place.
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_transfer_to_collections(
    p_account_id  INTEGER,
    p_agency_id   INTEGER,
    p_transfer_dt DATE DEFAULT CURRENT_DATE
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_old       Account%ROWTYPE;
    v_new_id    INTEGER;
    v_owner     INTEGER;
BEGIN
    SELECT * INTO v_old FROM Account WHERE AccountID = p_account_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Account % does not exist', p_account_id;
    END IF;

    IF v_old.AccountCategory = 'Collection' THEN
        RAISE EXCEPTION 'Account % is already a collection', p_account_id;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM Creditor
                    WHERE CreditorID = p_agency_id
                      AND BusinessType IN ('Collection Agency','Collection Attorney'))
    THEN
        RAISE EXCEPTION 'Creditor % is not a collection agency', p_agency_id;
    END IF;

    -- 1. The new collection tradeline, held by the agency.
    INSERT INTO Account (
        CreditorID, OriginalCreditorID, AccountNumberMasked,
        AccountCategory, AccountType, DateOpened, CurrentBalance,
        PastDueAmount, PaymentStatus, PaymentStatusDate,
        DateLastActivity, AccountStatus)
    VALUES (
        p_agency_id, v_old.CreditorID,
        'COL' || LPAD(p_account_id::TEXT, 9, '0'),
        'Collection', 'Collection', p_transfer_dt, v_old.CurrentBalance,
        v_old.CurrentBalance, 'Collection', p_transfer_dt,
        p_transfer_dt, 'Open')
    RETURNING AccountID INTO v_new_id;

    -- 2. Every liable party on the old account is liable on the new one.
    --    Authorized users are NOT carried over: they never owed the debt.
    FOR v_owner IN
        SELECT ConsumerID FROM ConsumerAccount
         WHERE AccountID = p_account_id
           AND ResponsibilityType <> 'Authorized User'
           AND DateRemoved IS NULL
    LOOP
        INSERT INTO ConsumerAccount
            (ConsumerID, AccountID, ResponsibilityType, DateAssociated)
        VALUES (v_owner, v_new_id, 'Individual', p_transfer_dt);
    END LOOP;

    -- 3. Close the original, zeroing the balance now owed elsewhere.
    UPDATE Account
       SET AccountStatus     = 'Transferred',
           CurrentBalance    = 0,
           PastDueAmount     = 0,
           PaymentStatus     = 'Transferred',
           PaymentStatusDate = p_transfer_dt,
           DateClosed        = p_transfer_dt
     WHERE AccountID = p_account_id;

    RAISE NOTICE 'Account % transferred to agency % as new collection account %',
                 p_account_id, p_agency_id, v_new_id;
END;
$$;


-- ---------------------------------------------------------------------
-- sp_purge_expired_records
--
-- The retention sweep. Hard inquiries older than two years, and
-- accounts past the date fn_account_purge_date() computes for them,
-- are removed. PaymentHistory disappears with its account through the
-- ON DELETE CASCADE that the weak-entity relationship requires.
--
-- p_dry_run defaults TRUE so the procedure reports what it WOULD
-- delete: destructive maintenance on regulated data should never be
-- the default behaviour of a callable routine.
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_purge_expired_records(
    p_dry_run BOOLEAN DEFAULT TRUE
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_inq   INTEGER;
    v_acct  INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_inq
      FROM Inquiry
     WHERE InquiryType = 'Hard'
       AND RemovalDate < CURRENT_DATE;

    SELECT COUNT(*) INTO v_acct
      FROM Account
     WHERE fn_account_purge_date(AccountID) < CURRENT_DATE;

    IF p_dry_run THEN
        RAISE NOTICE 'DRY RUN: % expired hard inquiries and % expired accounts would be purged',
                     v_inq, v_acct;
        RETURN;
    END IF;

    DELETE FROM Inquiry
     WHERE InquiryType = 'Hard'
       AND RemovalDate < CURRENT_DATE;

    DELETE FROM Account
     WHERE fn_account_purge_date(AccountID) < CURRENT_DATE;

    RAISE NOTICE 'PURGED: % inquiries, % accounts (payment history cascaded)',
                 v_inq, v_acct;
END;
$$;
