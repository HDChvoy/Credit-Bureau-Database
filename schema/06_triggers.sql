-- =====================================================================
-- Deliverable #2, Task 5: Triggers
--
-- Four triggers, each enforcing a rule that a CHECK constraint cannot:
-- derived values, cross-row consistency, cross-table synchronisation,
-- and an audit trail.
-- =====================================================================

-- ---------------------------------------------------------------------
-- TRIGGER 1: derive the inquiry removal date.
--
-- Hard inquiries fall off the file two years after they are made;
-- soft inquiries are never disclosed to lenders and have no removal
-- date. Deriving this in a trigger guarantees the rule is applied no
-- matter which application inserts the row.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trgfn_inquiry_removal()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.InquiryType = 'Hard' THEN
        NEW.RemovalDate := (NEW.InquiryDate + INTERVAL '2 years')::DATE;
    ELSE
        NEW.RemovalDate := NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_inquiry_removal
    BEFORE INSERT OR UPDATE OF InquiryDate, InquiryType ON Inquiry
    FOR EACH ROW
    EXECUTE FUNCTION trgfn_inquiry_removal();

-- A trigger only fires on rows written after it exists. Deploying one
-- onto a populated table therefore requires a backfill, or the rule is
-- true of new data and false of old data.
UPDATE Inquiry
   SET RemovalDate = CASE WHEN InquiryType = 'Hard'
                          THEN (InquiryDate + INTERVAL '2 years')::DATE END
 WHERE RemovalDate IS DISTINCT FROM
       CASE WHEN InquiryType = 'Hard'
            THEN (InquiryDate + INTERVAL '2 years')::DATE END;


-- ---------------------------------------------------------------------
-- TRIGGER 2: keep only one current address per consumer.
--
-- A partial unique index already makes two current addresses illegal,
-- but an index can only REJECT the second row. What the business
-- actually wants is for a new current address to demote the old one,
-- which is a data change and therefore a trigger's job.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trgfn_address_single_current()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.IsCurrent THEN
        UPDATE Address
           SET IsCurrent = FALSE
         WHERE ConsumerID = NEW.ConsumerID
           AND IsCurrent  = TRUE
           AND AddressID <> COALESCE(NEW.AddressID, -1);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_address_single_current
    BEFORE INSERT OR UPDATE OF IsCurrent ON Address
    FOR EACH ROW
    EXECUTE FUNCTION trgfn_address_single_current();


-- ---------------------------------------------------------------------
-- TRIGGER 3: synchronise Account current status from PaymentHistory.
--
-- The design notes flag PaymentStatus on Account as a deliberate
-- redundancy, a materialised snapshot of the newest PaymentHistory
-- row, kept because "what is my status now" is the most common query
-- in the system. A redundancy is only safe if something guarantees it
-- stays true. This trigger is that guarantee.
--
-- It also derives PastDueAmount from the delinquency severity, and
-- respects the chk_account_pastdue_agrees constraint by writing both
-- columns together.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trgfn_sync_account_status()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_latest_month  DATE;
    v_latest_code   VARCHAR(4);
    v_status        VARCHAR(20);
    v_pastdue       NUMERIC(10,2);
    v_payment       NUMERIC(10,2);
BEGIN
    -- Find the newest month on record for this account.
    SELECT ph.ReportMonth, ph.StatusCode
      INTO v_latest_month, v_latest_code
      FROM PaymentHistory ph
     WHERE ph.AccountID = NEW.AccountID
     ORDER BY ph.ReportMonth DESC
     LIMIT 1;

    SELECT COALESCE(MonthlyPayment, 0) INTO v_payment
      FROM Account WHERE AccountID = NEW.AccountID;

    v_status := CASE v_latest_code
                    WHEN 'OK'  THEN 'Current'
                    WHEN 'ND'  THEN 'Current'
                    WHEN 'CLS' THEN 'Current'
                    WHEN '30'  THEN '30 Days Past Due'
                    WHEN '60'  THEN '60 Days Past Due'
                    WHEN '90'  THEN '90 Days Past Due'
                    WHEN '120' THEN '120 Days Past Due'
                    WHEN '150' THEN '150 Days Past Due'
                    WHEN '180' THEN '180 Days Past Due'
                    WHEN 'CO'  THEN 'Charge-Off'
                    WHEN 'C'   THEN 'Collection'
                    ELSE            'Derogatory'
                END;

    -- Past-due amount scales with how many payment cycles were missed.
    v_pastdue := CASE v_latest_code
                    WHEN '30'  THEN v_payment * 1
                    WHEN '60'  THEN v_payment * 2
                    WHEN '90'  THEN v_payment * 3
                    WHEN '120' THEN v_payment * 4
                    WHEN '150' THEN v_payment * 5
                    WHEN '180' THEN v_payment * 6
                    ELSE 0
                 END;

    UPDATE Account
       SET PaymentStatus     = v_status,
           PaymentStatusDate = v_latest_month,
           PastDueAmount     = v_pastdue,
           DateLastActivity  = GREATEST(DateLastActivity, v_latest_month)
     WHERE AccountID = NEW.AccountID;

    RETURN NULL;   -- AFTER trigger; return value is ignored
END;
$$;

CREATE TRIGGER trg_sync_account_status
    AFTER INSERT OR UPDATE ON PaymentHistory
    FOR EACH ROW
    EXECUTE FUNCTION trgfn_sync_account_status();


-- ---------------------------------------------------------------------
-- TRIGGER 4: audit material changes to an account.
--
-- Credit data is regulated: a consumer who disputes a balance is
-- entitled to know when it changed and who changed it. This trigger
-- writes one audit row per changed column, which is what makes the
-- dispute investigation possible at all.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trgfn_account_audit()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.CurrentBalance IS DISTINCT FROM OLD.CurrentBalance THEN
        INSERT INTO AccountAudit (AccountID, ChangedColumn, OldValue, NewValue)
        VALUES (NEW.AccountID, 'CurrentBalance',
                OLD.CurrentBalance::VARCHAR, NEW.CurrentBalance::VARCHAR);
    END IF;

    IF NEW.CreditLimit IS DISTINCT FROM OLD.CreditLimit THEN
        INSERT INTO AccountAudit (AccountID, ChangedColumn, OldValue, NewValue)
        VALUES (NEW.AccountID, 'CreditLimit',
                OLD.CreditLimit::VARCHAR, NEW.CreditLimit::VARCHAR);
    END IF;

    IF NEW.PaymentStatus IS DISTINCT FROM OLD.PaymentStatus THEN
        INSERT INTO AccountAudit (AccountID, ChangedColumn, OldValue, NewValue)
        VALUES (NEW.AccountID, 'PaymentStatus',
                OLD.PaymentStatus, NEW.PaymentStatus);
    END IF;

    IF NEW.AccountStatus IS DISTINCT FROM OLD.AccountStatus THEN
        INSERT INTO AccountAudit (AccountID, ChangedColumn, OldValue, NewValue)
        VALUES (NEW.AccountID, 'AccountStatus',
                OLD.AccountStatus, NEW.AccountStatus);
    END IF;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_account_audit
    AFTER UPDATE ON Account
    FOR EACH ROW
    EXECUTE FUNCTION trgfn_account_audit();
