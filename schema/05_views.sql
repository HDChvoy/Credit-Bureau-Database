-- =====================================================================
-- Deliverable #2, Task 4: Views
--
-- Views serve two purposes here. Several encapsulate joins that would
-- otherwise be repeated in every application query. One of them,
-- vw_consumer_disclosure, exists for ACCESS CONTROL: it exposes the
-- consumer-facing subset of the file while withholding the internal
-- columns a consumer is not entitled to see.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. vw_consumer_credit_summary
--    One row per consumer: the dashboard a member sees on login.
--    Combines the three scoring factors the functions compute with
--    the consumer's most recent score.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_consumer_credit_summary AS
SELECT
    c.ConsumerID,
    c.FirstName || ' ' || c.LastName                       AS ConsumerName,
    latest.ScoreValue                                      AS CurrentScore,
    latest.ScoreModel,
    fn_score_band(latest.ScoreValue)                       AS ScoreBand,
    COUNT(*) FILTER (WHERE a.AccountStatus = 'Open')       AS OpenAccounts,
    COUNT(*) FILTER (WHERE a.AccountCategory = 'Collection') AS CollectionAccounts,
    COALESCE(SUM(a.CurrentBalance) FILTER
             (WHERE a.AccountStatus = 'Open'), 0)          AS TotalBalance,
    fn_credit_utilization(c.ConsumerID)                    AS UtilizationPct,
    fn_average_account_age_months(c.ConsumerID)            AS AvgAccountAgeMonths,
    fn_on_time_payment_pct(c.ConsumerID)                   AS OnTimePaymentPct,
    (SELECT COUNT(*) FROM Inquiry i
      WHERE i.ConsumerID  = c.ConsumerID
        AND i.InquiryType = 'Hard'
        AND i.InquiryDate > CURRENT_DATE - INTERVAL '2 years')
                                                           AS HardInquiries24Mo
FROM Consumer c
LEFT JOIN ConsumerAccount ca
       ON ca.ConsumerID = c.ConsumerID AND ca.DateRemoved IS NULL
LEFT JOIN Account a
       ON a.AccountID = ca.AccountID
LEFT JOIN LATERAL (
        SELECT cs.ScoreValue, cs.ScoreModel
          FROM CreditScore cs
         WHERE cs.ConsumerID = c.ConsumerID
         ORDER BY cs.ScoreDate DESC, cs.ScoreID DESC
         LIMIT 1
     ) latest ON TRUE
GROUP BY c.ConsumerID, c.FirstName, c.LastName,
         latest.ScoreValue, latest.ScoreModel;


-- ---------------------------------------------------------------------
-- 2. vw_delinquent_accounts
--    The collections and risk work queue. Joins through the M:N
--    junction so that a joint account correctly surfaces BOTH liable
--    parties, but excludes authorized users, who carry the history
--    on their file without owing the debt.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_delinquent_accounts AS
SELECT
    a.AccountID,
    cr.CreditorName,
    a.AccountType,
    c.ConsumerID,
    c.FirstName || ' ' || c.LastName  AS ConsumerName,
    ca.ResponsibilityType,
    a.CurrentBalance,
    a.PastDueAmount,
    a.PaymentStatus,
    a.PaymentStatusDate,
    (SELECT COUNT(*) FROM PaymentHistory ph
      WHERE ph.AccountID  = a.AccountID
        AND ph.StatusCode IN ('30','60','90','120','150','180'))
                                      AS LateMonthsOnRecord
FROM Account a
JOIN Creditor        cr ON cr.CreditorID = a.CreditorID
JOIN ConsumerAccount ca ON ca.AccountID  = a.AccountID
JOIN Consumer        c  ON c.ConsumerID  = ca.ConsumerID
WHERE a.PastDueAmount > 0
  AND ca.DateRemoved IS NULL
  AND ca.ResponsibilityType <> 'Authorized User';


-- ---------------------------------------------------------------------
-- 3. vw_active_hard_inquiries
--    Hard inquiries still inside the two-year window. Rows outside it
--    are legally invisible to lenders even before the purge job
--    physically removes them, so the view, not the table, is what
--    lender-facing code must read.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_active_hard_inquiries AS
SELECT
    i.InquiryID,
    i.ConsumerID,
    cr.CreditorName,
    cr.BusinessType,
    i.InquiryDate,
    i.PurposeType,
    i.RemovalDate,
    (i.RemovalDate - CURRENT_DATE) AS DaysUntilRemoval
FROM Inquiry i
JOIN Creditor cr ON cr.CreditorID = i.CreditorID
WHERE i.InquiryType = 'Hard'
  AND i.InquiryDate > CURRENT_DATE - INTERVAL '2 years';


-- ---------------------------------------------------------------------
-- 4. vw_rate_shopping_clusters
--    THE INTERESTING ONE.
--
--    Scoring models collapse multiple auto, mortgage or student-loan
--    inquiries made inside a short shopping window into a single
--    inquiry, so that a consumer comparing lenders is not punished for
--    diligence. This cannot be expressed as a CHECK constraint: it is
--    a windowing problem over neighbouring rows.
--
--    LAG() finds the gap to the previous inquiry of the same purpose;
--    a running sum of "gap > 14 days" assigns a cluster number.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_rate_shopping_clusters AS
WITH gapped AS (
    SELECT
        i.InquiryID, i.ConsumerID, i.PurposeType, i.InquiryDate,
        COALESCE(
            i.InquiryDate - LAG(i.InquiryDate) OVER (
                PARTITION BY i.ConsumerID, i.PurposeType
                ORDER BY i.InquiryDate),
            9999
        ) AS DaysSincePrevious
    FROM Inquiry i
    WHERE i.InquiryType = 'Hard'
      AND i.PurposeType IN ('Auto Loan','Mortgage','Student Loan')
),
numbered AS (
    SELECT g.*,
           SUM(CASE WHEN g.DaysSincePrevious > 14 THEN 1 ELSE 0 END)
               OVER (PARTITION BY g.ConsumerID, g.PurposeType
                     ORDER BY g.InquiryDate
                     ROWS UNBOUNDED PRECEDING) AS ClusterNo
    FROM gapped g
)
SELECT
    ConsumerID,
    PurposeType,
    ClusterNo,
    COUNT(*)          AS InquiriesInCluster,
    MIN(InquiryDate)  AS ClusterStart,
    MAX(InquiryDate)  AS ClusterEnd,
    1                 AS ScoredAsInquiries   -- the whole cluster counts once
FROM numbered
GROUP BY ConsumerID, PurposeType, ClusterNo;


-- ---------------------------------------------------------------------
-- 5. vw_consumer_disclosure
--    The consumer-facing credit file. Deliberately omits internal
--    columns: subscriber codes, the furnisher flag, and the audit
--    trail. Granting a consumer-facing role SELECT on this view rather
--    than on the base tables is the access-control mechanism.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_consumer_disclosure AS
SELECT
    c.ConsumerID,
    c.FirstName || ' ' || COALESCE(c.MiddleName || ' ', '') || c.LastName
        || COALESCE(' ' || c.Suffix, '')             AS FullName,
    c.SSN_Masked,
    c.YearOfBirth,
    addr.StreetLine1 || COALESCE(', ' || addr.StreetLine2, '')
        || ', ' || addr.City || ', ' || addr.StateCode
        || ' ' || addr.PostalCode                    AS CurrentAddress,
    cr.CreditorName                                  AS AccountName,
    a.AccountNumberMasked,
    a.AccountType,
    ca.ResponsibilityType,
    a.DateOpened,
    COALESCE(a.CreditLimit, a.OriginalLoanAmount)    AS LimitOrOriginalAmount,
    a.CurrentBalance,
    a.MonthlyPayment,
    a.PaymentStatus,
    a.AccountStatus,
    fn_account_purge_date(a.AccountID)               AS ScheduledRemovalDate
FROM Consumer c
JOIN ConsumerAccount ca ON ca.ConsumerID = c.ConsumerID AND ca.DateRemoved IS NULL
JOIN Account         a  ON a.AccountID   = ca.AccountID
JOIN Creditor        cr ON cr.CreditorID = a.CreditorID
LEFT JOIN Address  addr ON addr.ConsumerID = c.ConsumerID AND addr.IsCurrent
WHERE c.DeceasedFlag = FALSE;
