-- =====================================================================
-- Deliverable #2, Task 6: Functions
--
-- Loaded before the views, because several views call these.
-- Each function implements one of the five published FICO scoring
-- factors, or one of the bureau's retention rules.
-- =====================================================================

-- ---------------------------------------------------------------------
-- fn_credit_utilization(ConsumerID) -> NUMERIC
--
-- Revolving balances divided by revolving limits, as a percentage.
-- "Amounts owed" is 30% of a FICO score and utilization is its main
-- component. Experian's guidance: keep it under 30%, and consumers
-- with the highest scores are typically under 10%.
--
-- Only OPEN REVOLVING accounts count. Installment loans are excluded:
-- a mortgage balance is not "utilization" in any meaningful sense.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_credit_utilization(p_consumer_id INTEGER)
RETURNS NUMERIC(6,2)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_balance NUMERIC(14,2);
    v_limit   NUMERIC(14,2);
BEGIN
    SELECT COALESCE(SUM(a.CurrentBalance), 0),
           COALESCE(SUM(a.CreditLimit), 0)
      INTO v_balance, v_limit
      FROM Account a
      JOIN ConsumerAccount ca ON ca.AccountID = a.AccountID
     WHERE ca.ConsumerID     = p_consumer_id
       AND ca.DateRemoved   IS NULL
       AND a.AccountCategory = 'Revolving'
       AND a.AccountStatus   = 'Open';

    -- A consumer with no open revolving credit has no utilization
    -- ratio at all. Returning NULL is correct; returning 0 would
    -- falsely imply perfect utilization.
    IF v_limit = 0 THEN
        RETURN NULL;
    END IF;

    RETURN ROUND((v_balance / v_limit) * 100, 2);
END;
$$;

COMMENT ON FUNCTION fn_credit_utilization IS
    'Revolving utilization %% for a consumer. NULL when no open revolving credit exists.';


-- ---------------------------------------------------------------------
-- fn_average_account_age_months(ConsumerID) -> INTEGER
--
-- "Length of credit history" is 15% of a FICO score, and the average
-- age of accounts is one of the three ages the model looks at.
-- Closing an old card shortens this, which is why the advice is to
-- leave old accounts open.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_average_account_age_months(p_consumer_id INTEGER)
RETURNS INTEGER
LANGUAGE sql
STABLE
AS $$
    SELECT ROUND(AVG(
               EXTRACT(YEAR  FROM AGE(CURRENT_DATE, a.DateOpened)) * 12 +
               EXTRACT(MONTH FROM AGE(CURRENT_DATE, a.DateOpened))
           ))::INTEGER
      FROM Account a
      JOIN ConsumerAccount ca ON ca.AccountID = a.AccountID
     WHERE ca.ConsumerID   = p_consumer_id
       AND ca.DateRemoved IS NULL;
$$;


-- ---------------------------------------------------------------------
-- fn_on_time_payment_pct(ConsumerID) -> NUMERIC
--
-- Payment history is 35% of a FICO score, the largest single factor.
-- Months with no data reported ('ND') are excluded from both the
-- numerator and the denominator: absence of data is not a missed
-- payment, and treating it as one would penalise the consumer for a
-- furnisher's reporting gap.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_on_time_payment_pct(p_consumer_id INTEGER)
RETURNS NUMERIC(6,2)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_total   INTEGER;
    v_on_time INTEGER;
BEGIN
    SELECT COUNT(*),
           COUNT(*) FILTER (WHERE ph.StatusCode IN ('OK','CLS'))
      INTO v_total, v_on_time
      FROM PaymentHistory ph
      JOIN ConsumerAccount ca ON ca.AccountID = ph.AccountID
     WHERE ca.ConsumerID    = p_consumer_id
       AND ca.DateRemoved  IS NULL
       AND ph.StatusCode   <> 'ND';

    IF v_total = 0 THEN
        RETURN NULL;
    END IF;

    RETURN ROUND((v_on_time::NUMERIC / v_total) * 100, 2);
END;
$$;


-- ---------------------------------------------------------------------
-- fn_account_purge_date(AccountID) -> DATE
--
-- Implements the FCRA-style retention windows Experian publishes:
--    closed in good standing ....... 10 years from closure
--    closed in poor standing ........ 7 years from closure
--    collection accounts ............ 7 years from the delinquency
--    open accounts .................. never (NULL)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_account_purge_date(p_account_id INTEGER)
RETURNS DATE
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    r Account%ROWTYPE;
BEGIN
    SELECT * INTO r FROM Account WHERE AccountID = p_account_id;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    -- Collections purge seven years from the date they were opened.
    IF r.AccountCategory = 'Collection' THEN
        RETURN (r.DateOpened + INTERVAL '7 years')::DATE;
    END IF;

    -- Open accounts stay on file indefinitely.
    IF r.DateClosed IS NULL THEN
        RETURN NULL;
    END IF;

    -- Closed: seven years if it went bad, ten if it did not.
    IF EXISTS (SELECT 1 FROM PaymentHistory
                WHERE AccountID  = p_account_id
                  AND StatusCode IN ('30','60','90','120','150','180',
                                     'CO','C','D','F','FS','R','VS','BK'))
    THEN
        RETURN (r.DateClosed + INTERVAL '7 years')::DATE;
    ELSE
        RETURN (r.DateClosed + INTERVAL '10 years')::DATE;
    END IF;
END;
$$;


-- ---------------------------------------------------------------------
-- fn_score_band(ScoreValue) -> VARCHAR
--
-- Maps a numeric score onto the qualitative bands Experian publishes
-- to consumers. A scalar helper, used by the summary views.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_score_band(p_score SMALLINT)
RETURNS VARCHAR(12)
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
             WHEN p_score IS NULL     THEN NULL
             WHEN p_score >= 800      THEN 'Exceptional'
             WHEN p_score >= 740      THEN 'Very Good'
             WHEN p_score >= 670      THEN 'Good'
             WHEN p_score >= 580      THEN 'Fair'
             ELSE                          'Poor'
           END::VARCHAR(12);
$$;
