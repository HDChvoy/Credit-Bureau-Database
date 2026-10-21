-- =====================================================================
-- Deliverable #2, Task 3: Indexes
--
-- Every index below is justified by a query the application actually
-- runs. Indexes are not free: each one slows INSERT and UPDATE, which
-- matters here because furnishers bulk-load millions of tradeline
-- updates every month.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Reverse lookup on the M:N junction.
--    The composite PK (ConsumerID, AccountID) already serves
--    "all accounts for this consumer". It cannot serve the opposite
--    direction, "who is on this account", because AccountID is not the
--    leading column. That question is asked on every dispute and every
--    fraud investigation.
-- ---------------------------------------------------------------------
CREATE INDEX idx_consumeraccount_account
    ON ConsumerAccount (AccountID, ConsumerID);

-- ---------------------------------------------------------------------
-- 2. Inquiry lookup by consumer, newest first.
--    Supports both the report display and the two-year purge sweep.
--    DESC ordering lets the planner read the newest rows without a sort.
-- ---------------------------------------------------------------------
CREATE INDEX idx_inquiry_consumer_date
    ON Inquiry (ConsumerID, InquiryDate DESC);

-- ---------------------------------------------------------------------
-- 3. PARTIAL index: hard inquiries only.
--    Only hard inquiries affect the score and appear to lenders, and
--    they are a minority of rows. A partial index stays small and is
--    read far more often than the soft ones.
-- ---------------------------------------------------------------------
CREATE INDEX idx_inquiry_hard_only
    ON Inquiry (ConsumerID, InquiryDate DESC)
    WHERE InquiryType = 'Hard';

-- ---------------------------------------------------------------------
-- 4. Latest score per consumer.
--    "What is my score today" is the single most common consumer query
--    on the entire system.
-- ---------------------------------------------------------------------
CREATE INDEX idx_creditscore_consumer_date
    ON CreditScore (ConsumerID, ScoreDate DESC);

-- ---------------------------------------------------------------------
-- 5. Accounts by creditor.
--    Supports the furnisher-facing view: "show me every tradeline I
--    report." The FK column is not indexed automatically in PostgreSQL.
-- ---------------------------------------------------------------------
CREATE INDEX idx_account_creditor
    ON Account (CreditorID);

-- ---------------------------------------------------------------------
-- 6. PARTIAL index: delinquent accounts only.
--    Collections and risk teams query this constantly; healthy accounts
--    are the overwhelming majority and are excluded from the index.
-- ---------------------------------------------------------------------
CREATE INDEX idx_account_delinquent
    ON Account (PaymentStatus, PaymentStatusDate DESC)
    WHERE PastDueAmount > 0;

-- ---------------------------------------------------------------------
-- 7. Revolving accounts, for the utilization calculation.
--    Utilization drives 30% of a FICO score and is recomputed on every
--    report pull. COVERING columns via INCLUDE let the query be
--    answered from the index alone (index-only scan).
-- ---------------------------------------------------------------------
CREATE INDEX idx_account_revolving_util
    ON Account (AccountID)
    INCLUDE (CurrentBalance, CreditLimit)
    WHERE AccountCategory = 'Revolving' AND AccountStatus = 'Open';

-- ---------------------------------------------------------------------
-- 8. Payment history by month.
--    The PK (AccountID, ReportMonth) answers "history for one account".
--    Portfolio-wide analytics ask the transposed question, "every
--    delinquency reported in March", which needs ReportMonth leading.
-- ---------------------------------------------------------------------
CREATE INDEX idx_paymenthistory_month_status
    ON PaymentHistory (ReportMonth, StatusCode);

-- ---------------------------------------------------------------------
-- 9. Consumer name search, case-insensitive.
--    Support agents search by surname. An expression index on
--    UPPER(LastName) is used only if the query also calls UPPER().
-- ---------------------------------------------------------------------
CREATE INDEX idx_consumer_lastname_upper
    ON Consumer (UPPER(LastName), UPPER(FirstName));

ANALYZE;
