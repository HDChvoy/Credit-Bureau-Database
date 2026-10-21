"""
Deliverable #5 - the analytics query library.

Every report on the Analytics pages is defined here, once. Each entry
carries the SQL that runs, the plain-English question it answers, the
parameters the user can change, and an explanation of the technique.
The page shows the SQL text from this file verbatim, so what the grader
reads on screen is exactly what PostgreSQL executed.

Six categories, matching the Deliverable #5 brief:

    set_ops     UNION, INTERSECT, EXCEPT
    membership  IN, NOT IN, NOT EXISTS
    comparison  > ALL, < SOME
    with        multi-CTE pipelines and WITH RECURSIVE
    aggregate   FILTER, HAVING, STRING_AGG, ordered-set aggregates
    olap        ROLLUP, CUBE, window functions (RANK, NTILE, LAG, ...)

Conventions:

  * Every user-supplied value is a named psycopg placeholder
    (%(name)s). Nothing is formatted into the SQL text.
  * Output columns are aliased with quoted display names
    ("Total balance"), so the column headers on screen come straight
    from the query instead of from a mapping in Python.
  * A column aliased "_level" is a GROUPING() result. The template hides
    it and uses it to style subtotal and grand-total rows.
"""

# Late-payment status codes in PaymentHistory (see chk_ph_status).
# Repeated inline in the SQL below rather than formatted in, so every
# query on screen is complete and runnable as-is in psql.


CATEGORIES = [
    {
        "key": "set_ops",
        "title": "Set operations",
        "icon": "layers",
        "blurb": "Combine the results of two queries: UNION, INTERSECT and EXCEPT.",
    },
    {
        "key": "membership",
        "title": "Set membership",
        "icon": "filter",
        "blurb": "Test whether a value is in the result of a subquery: IN, NOT IN, NOT EXISTS.",
    },
    {
        "key": "comparison",
        "title": "Set comparison",
        "icon": "scale",
        "blurb": "Compare one value against every row of a subquery: > ALL and < SOME.",
    },
    {
        "key": "with",
        "title": "WITH subqueries",
        "icon": "stack",
        "blurb": "Named intermediate results (CTEs), including a recursive one.",
    },
    {
        "key": "aggregate",
        "title": "Advanced aggregates",
        "icon": "sigma",
        "blurb": "FILTER, HAVING, STRING_AGG, PERCENTILE_CONT, MODE and STDDEV.",
    },
    {
        "key": "olap",
        "title": "OLAP",
        "icon": "cube",
        "blurb": "Subtotals with ROLLUP and CUBE, and window functions over ordered data.",
    },
]


QUERIES = [

    # =================================================================
    # SET OPERATIONS
    # =================================================================
    {
        "id": "union-creditor-contacts",
        "category": "set_ops",
        "title": "Every creditor on one credit file",
        "question": "Which creditors appear anywhere on this consumer's file, "
                    "and in what role?",
        "concepts": ["UNION", "three-way union", "duplicate elimination"],
        "params": [
            {"name": "consumer_id", "label": "Consumer", "type": "consumer",
             "default": 1},
        ],
        "sql": """\
-- A creditor can show up on a credit file in three different ways.
-- Each SELECT finds one of them; UNION stacks the three results and
-- removes exact duplicate rows.
SELECT cr.CreditorName  AS "Creditor",
       cr.BusinessType  AS "Business type",
       'Holds a tradeline' AS "Relationship"
  FROM ConsumerAccount ca
  JOIN Account  a  ON a.AccountID   = ca.AccountID
  JOIN Creditor cr ON cr.CreditorID = a.CreditorID
 WHERE ca.ConsumerID = %(consumer_id)s

UNION

SELECT cr.CreditorName,
       cr.BusinessType,
       i.InquiryType || ' inquiry - ' || i.PurposeType
  FROM Inquiry  i
  JOIN Creditor cr ON cr.CreditorID = i.CreditorID
 WHERE i.ConsumerID = %(consumer_id)s

UNION

SELECT orig.CreditorName,
       orig.BusinessType,
       'Original creditor of a collection'
  FROM ConsumerAccount ca
  JOIN Account  a    ON a.AccountID      = ca.AccountID
  JOIN Creditor orig ON orig.CreditorID  = a.OriginalCreditorID
 WHERE ca.ConsumerID = %(consumer_id)s

 ORDER BY "Creditor", "Relationship";""",
        "explain": [
            "Tradelines, inquiries and collections live in different tables, "
            "so no single SELECT can list them together. UNION can, because "
            "all three branches return the same three columns.",
            "UNION (not UNION ALL) removes duplicate rows. Marcus Whitfield "
            "(#1) has two identical hard auto-loan inquiries from Trailhead "
            "Motors Credit a week apart; they appear here once.",
            "Try Aaron Castellanos Jr (#5): he has a collection, so the "
            "third branch adds the original creditor that sold the debt.",
        ],
    },
    {
        "id": "intersect-delinquent-applicants",
        "category": "set_ops",
        "title": "Behind on payments and still applying",
        "question": "Which consumers have money past due AND have applied for "
                    "new credit (a hard inquiry)?",
        "concepts": ["INTERSECT", "WITH", "scalar subqueries"],
        "params": [],
        "sql": """\
WITH flagged AS (
    -- Set 1: consumers with money past due on any tradeline
    SELECT ca.ConsumerID
      FROM ConsumerAccount ca
      JOIN Account a ON a.AccountID = ca.AccountID
     WHERE a.PastDueAmount > 0

    INTERSECT

    -- Set 2: consumers somebody pulled a hard inquiry on
    SELECT i.ConsumerID
      FROM Inquiry i
     WHERE i.InquiryType = 'Hard'
)
SELECT c.ConsumerID                        AS "ID",
       CONCAT_WS(' ', c.FirstName, c.LastName, c.Suffix)    AS "Consumer",
       (SELECT SUM(a.PastDueAmount)
          FROM ConsumerAccount ca
          JOIN Account a ON a.AccountID = ca.AccountID
         WHERE ca.ConsumerID = c.ConsumerID)  AS "Total past due",
       (SELECT COUNT(*)
          FROM Inquiry i
         WHERE i.ConsumerID = c.ConsumerID
           AND i.InquiryType = 'Hard')        AS "Hard inquiries",
       (SELECT MAX(i.InquiryDate)
          FROM Inquiry i
         WHERE i.ConsumerID = c.ConsumerID
           AND i.InquiryType = 'Hard')        AS "Most recent application"
  FROM flagged f
  JOIN Consumer c ON c.ConsumerID = f.ConsumerID
 ORDER BY "Total past due" DESC;""",
        "explain": [
            "INTERSECT keeps only the IDs that come out of BOTH queries. "
            "That is a delinquency signal combined with a credit-seeking "
            "signal, which is the profile underwriters look hardest at.",
            "The intersection is computed on ConsumerID alone. The names "
            "and totals are joined on afterwards, so the set operation "
            "stays on the key and is not affected by extra columns.",
        ],
    },
    {
        "id": "except-unconverted-inquiries",
        "category": "set_ops",
        "title": "Applications that never became accounts",
        "question": "Which hard inquiries did NOT result in a tradeline with "
                    "the creditor that made them?",
        "concepts": ["EXCEPT", "composite-key set difference", "WITH"],
        "params": [],
        "sql": """\
WITH unconverted AS (
    -- Every (consumer, creditor) pair that had a hard inquiry ...
    SELECT i.ConsumerID, i.CreditorID
      FROM Inquiry i
     WHERE i.InquiryType = 'Hard'

    EXCEPT

    -- ... minus every pair where an account actually exists.
    SELECT ca.ConsumerID, a.CreditorID
      FROM ConsumerAccount ca
      JOIN Account a ON a.AccountID = ca.AccountID
)
SELECT CONCAT_WS(' ', c.FirstName, c.LastName, c.Suffix) AS "Consumer",
       cr.CreditorName                  AS "Inquiring creditor",
       STRING_AGG(DISTINCT i.PurposeType, ', ')  AS "Purpose",
       COUNT(*)                         AS "Inquiries",
       MAX(i.InquiryDate)               AS "Latest inquiry"
  FROM unconverted u
  JOIN Inquiry  i  ON i.ConsumerID  = u.ConsumerID
                  AND i.CreditorID  = u.CreditorID
                  AND i.InquiryType = 'Hard'
  JOIN Consumer c  ON c.ConsumerID  = u.ConsumerID
  JOIN Creditor cr ON cr.CreditorID = u.CreditorID
 GROUP BY c.ConsumerID, cr.CreditorID
 ORDER BY "Consumer";""",
        "explain": [
            "EXCEPT returns rows in the first set that are not in the "
            "second. Here a 'row' is a (consumer, creditor) pair, so the "
            "difference is taken on a composite key.",
            "Most of these are rate shopping: Priya Raghunathan applied "
            "for a mortgage with two lenders and opened it with Keystone, "
            "so the Cardinal Home Lending inquiry is what is left over.",
        ],
    },

    # =================================================================
    # SET MEMBERSHIP
    # =================================================================
    {
        "id": "in-business-type",
        "category": "membership",
        "title": "Consumers by creditor industry",
        "question": "Which consumers hold a tradeline with any creditor in "
                    "the chosen industry?",
        "concepts": ["IN", "nested IN subqueries", "correlated scalar subquery"],
        "params": [
            {"name": "business_type", "label": "Creditor industry",
             "type": "choice", "default": "Bank Credit Cards",
             "choices": ["Bank Credit Cards", "Automobile Financing",
                         "Mortgage Lender", "Student Loan Servicer",
                         "Personal Loan", "Collection Agency",
                         "Collection Attorney", "Utility/Telecom"]},
        ],
        "sql": """\
-- Three levels of IN, read from the inside out:
--   creditors in the industry -> their accounts -> who holds them.
SELECT c.ConsumerID                     AS "ID",
       CONCAT_WS(' ', c.FirstName, c.LastName, c.Suffix) AS "Consumer",
       c.YearOfBirth                    AS "Born",
       (SELECT COUNT(*)
          FROM ConsumerAccount ca2
          JOIN Account  a2  ON a2.AccountID   = ca2.AccountID
          JOIN Creditor cr2 ON cr2.CreditorID = a2.CreditorID
         WHERE ca2.ConsumerID   = c.ConsumerID
           AND cr2.BusinessType = %(business_type)s) AS "Matching tradelines"
  FROM Consumer c
 WHERE c.ConsumerID IN (
         SELECT ca.ConsumerID
           FROM ConsumerAccount ca
          WHERE ca.AccountID IN (
                  SELECT a.AccountID
                    FROM Account a
                   WHERE a.CreditorID IN (
                           SELECT cr.CreditorID
                             FROM Creditor cr
                            WHERE cr.BusinessType = %(business_type)s)))
 ORDER BY c.LastName, c.FirstName;""",
        "explain": [
            "Each IN asks 'is this value somewhere in that list?'. Nesting "
            "them walks Creditor -> Account -> ConsumerAccount -> Consumer "
            "without a single JOIN in the outer query.",
            "Because IN is a membership test, a consumer with three bank "
            "cards still appears once. A JOIN would have returned them "
            "three times and needed a DISTINCT.",
            "The industry is a dropdown limited to the values "
            "chk_creditor_bustype allows, and it reaches PostgreSQL as a "
            "parameter, never as part of the SQL text.",
        ],
    },
    {
        "id": "not-exists-no-revolving",
        "category": "membership",
        "title": "Consumers with no open revolving credit",
        "question": "Who has no open credit card or charge card, and so has "
                    "no utilization figure at all?",
        "concepts": ["NOT EXISTS", "correlated subquery", "D2 function"],
        "params": [],
        "sql": """\
SELECT c.ConsumerID                     AS "ID",
       CONCAT_WS(' ', c.FirstName, c.LastName, c.Suffix) AS "Consumer",
       COALESCE((SELECT STRING_AGG(DISTINCT a.AccountCategory, ', ')
                   FROM ConsumerAccount ca
                   JOIN Account a ON a.AccountID = ca.AccountID
                  WHERE ca.ConsumerID = c.ConsumerID),
                '(no tradelines)')      AS "What they do have",
       fn_credit_utilization(c.ConsumerID) AS "Utilization (pct)"
  FROM Consumer c
 WHERE NOT EXISTS (
         SELECT 1
           FROM ConsumerAccount ca
           JOIN Account a ON a.AccountID = ca.AccountID
          WHERE ca.ConsumerID     = c.ConsumerID   -- correlated to the outer row
            AND a.AccountCategory = 'Revolving'
            AND a.AccountStatus   = 'Open')
 ORDER BY c.LastName;""",
        "explain": [
            "NOT EXISTS runs the inner query once per consumer (it is "
            "correlated on c.ConsumerID) and keeps the consumer only when "
            "the inner query finds nothing.",
            "The Utilization column is the D2 function "
            "fn_credit_utilization. It returns NULL, not 0%, for exactly "
            "these people - no revolving credit means utilization is "
            "undefined, which is not the same as perfect.",
        ],
    },
    {
        "id": "not-in-inquiry-only-creditors",
        "category": "membership",
        "title": "Creditors that never furnished a tradeline",
        "question": "Which creditors have pulled credit but never reported "
                    "an account, either as holder or original creditor?",
        "concepts": ["NOT IN", "the NULL trap", "IS NOT NULL guard"],
        "params": [],
        "sql": """\
SELECT cr.CreditorName AS "Creditor",
       cr.BusinessType AS "Business type",
       (SELECT COUNT(*) FROM Inquiry i
         WHERE i.CreditorID = cr.CreditorID) AS "Inquiries made"
  FROM Creditor cr
 WHERE cr.CreditorID NOT IN (SELECT a.CreditorID FROM Account a)
   AND cr.CreditorID NOT IN (
         SELECT a.OriginalCreditorID
           FROM Account a
          WHERE a.OriginalCreditorID IS NOT NULL)   -- required, see below
 ORDER BY cr.CreditorName;""",
        "explain": [
            "NOT IN is the negated membership test, and it has a trap. "
            "OriginalCreditorID is NULL on every non-collection account. "
            "If one NULL gets into a NOT IN list, 'x NOT IN (..., NULL)' "
            "evaluates to UNKNOWN for every x and the query returns zero rows.",
            "The IS NOT NULL filter in the second subquery is what prevents "
            "that. Remove it in the SQL console and the result goes empty.",
        ],
    },

    # =================================================================
    # SET COMPARISON
    # =================================================================
    {
        "id": "all-above-every-delinquent",
        "category": "comparison",
        "title": "Scores above every delinquent consumer",
        "question": "Which clean-file consumers have a latest FICO 8 score "
                    "higher than ALL consumers who are behind on payments?",
        "concepts": ["> ALL", "DISTINCT ON", "WITH", "D2 function"],
        "params": [],
        "sql": """\
WITH latest_fico8 AS (
    -- One row per consumer: their most recent FICO Score 8.
    SELECT DISTINCT ON (ConsumerID) ConsumerID, ScoreValue
      FROM CreditScore
     WHERE ScoreModel = 'FICO Score 8'
     ORDER BY ConsumerID, ScoreDate DESC
),
delinquent AS (
    SELECT DISTINCT ca.ConsumerID
      FROM ConsumerAccount ca
      JOIN Account a ON a.AccountID = ca.AccountID
     WHERE a.PastDueAmount > 0
)
SELECT CONCAT_WS(' ', c.FirstName, c.LastName, c.Suffix)  AS "Consumer",
       s.ScoreValue                      AS "Latest FICO 8",
       fn_score_band(s.ScoreValue)       AS "Band",
       (SELECT MAX(s2.ScoreValue)
          FROM latest_fico8 s2
         WHERE s2.ConsumerID IN (SELECT ConsumerID FROM delinquent))
                                         AS "Best delinquent score"
  FROM latest_fico8 s
  JOIN Consumer c ON c.ConsumerID = s.ConsumerID
 WHERE s.ConsumerID NOT IN (SELECT ConsumerID FROM delinquent)
   AND s.ScoreValue > ALL (
         SELECT s2.ScoreValue
           FROM latest_fico8 s2
          WHERE s2.ConsumerID IN (SELECT ConsumerID FROM delinquent))
 ORDER BY s.ScoreValue DESC;""",
        "explain": [
            "'> ALL (subquery)' is true only when the value beats every row "
            "the subquery returns. It is equivalent to '> MAX(...)', which "
            "is why the last column shows the delinquent maximum for "
            "comparison.",
            "Scores are compared within one model only. FICO 8 and "
            "VantageScore are on different scales, so comparing across "
            "them would be meaningless even though both are numbers.",
            "Edge case worth knowing: if the subquery returns no rows, "
            "> ALL is true for everybody.",
        ],
    },
    {
        "id": "some-below-a-delinquent",
        "category": "comparison",
        "title": "Clean files scoring below a delinquent one",
        "question": "Which consumers with no past-due balance still score "
                    "LOWER than at least one (SOME) delinquent consumer?",
        "concepts": ["< SOME / ANY", "WITH", "correlated count"],
        "params": [],
        "sql": """\
WITH latest_fico8 AS (
    SELECT DISTINCT ON (ConsumerID) ConsumerID, ScoreValue
      FROM CreditScore
     WHERE ScoreModel = 'FICO Score 8'
     ORDER BY ConsumerID, ScoreDate DESC
),
delinquent AS (
    SELECT DISTINCT ca.ConsumerID
      FROM ConsumerAccount ca
      JOIN Account a ON a.AccountID = ca.AccountID
     WHERE a.PastDueAmount > 0
)
SELECT CONCAT_WS(' ', c.FirstName, c.LastName, c.Suffix)      AS "Consumer",
       s.ScoreValue                          AS "Latest FICO 8",
       fn_credit_utilization(c.ConsumerID)   AS "Utilization (pct)",
       (SELECT COUNT(*)
          FROM latest_fico8 s2
         WHERE s2.ConsumerID IN (SELECT ConsumerID FROM delinquent)
           AND s2.ScoreValue > s.ScoreValue) AS "Delinquent consumers scoring higher"
  FROM latest_fico8 s
  JOIN Consumer c ON c.ConsumerID = s.ConsumerID
 WHERE s.ConsumerID NOT IN (SELECT ConsumerID FROM delinquent)
   AND s.ScoreValue < SOME (
         SELECT s2.ScoreValue
           FROM latest_fico8 s2
          WHERE s2.ConsumerID IN (SELECT ConsumerID FROM delinquent))
 ORDER BY s.ScoreValue;""",
        "explain": [
            "'< SOME (subquery)' (SOME and ANY are synonyms) is true when "
            "the value is smaller than at least one row. Equivalent to "
            "'< MAX(...)'.",
            "This is the complement of the > ALL report, and it is the "
            "more interesting one: these people have never missed a "
            "payment and still score below someone who has. The "
            "utilization column is part of why - payment history is not "
            "the only input to a score.",
        ],
    },

    # =================================================================
    # WITH
    # =================================================================
    {
        "id": "with-risk-tier",
        "category": "with",
        "title": "Consumer risk tiers",
        "question": "Combine score, debt, delinquency and recent applications "
                    "into one risk tier per consumer.",
        "concepts": ["multiple CTEs", "CTE chaining", "FILTER", "CASE"],
        "params": [],
        "sql": """\
WITH latest_score AS (
    SELECT DISTINCT ON (ConsumerID) ConsumerID, ScoreValue
      FROM CreditScore
     WHERE ScoreModel = 'FICO Score 8'
     ORDER BY ConsumerID, ScoreDate DESC
),
liability AS (
    -- Authorized users are excluded: they carry the account's history
    -- on their file but are not liable for the balance.
    SELECT ca.ConsumerID,
           SUM(a.CurrentBalance) FILTER (WHERE a.AccountStatus = 'Open') AS open_debt,
           SUM(a.PastDueAmount)                                         AS past_due,
           COUNT(*) FILTER (WHERE a.AccountCategory = 'Collection')     AS collections
      FROM ConsumerAccount ca
      JOIN Account a ON a.AccountID = ca.AccountID
     WHERE ca.ResponsibilityType <> 'Authorized User'
     GROUP BY ca.ConsumerID
),
recent_apps AS (
    SELECT ConsumerID, COUNT(*) AS hard_24mo
      FROM Inquiry
     WHERE InquiryType = 'Hard'
       AND InquiryDate > CURRENT_DATE - INTERVAL '24 months'
     GROUP BY ConsumerID
),
profile AS (
    -- This CTE reads the three above it.
    SELECT c.ConsumerID,
           CONCAT_WS(' ', c.FirstName, c.LastName, c.Suffix)       AS consumer,
           s.ScoreValue                           AS score,
           COALESCE(l.open_debt, 0)               AS open_debt,
           COALESCE(l.past_due, 0)                AS past_due,
           COALESCE(l.collections, 0)             AS collections,
           COALESCE(r.hard_24mo, 0)               AS hard_24mo,
           fn_credit_utilization(c.ConsumerID)    AS utilization
      FROM Consumer c
      LEFT JOIN latest_score s ON s.ConsumerID = c.ConsumerID
      LEFT JOIN liability    l ON l.ConsumerID = c.ConsumerID
      LEFT JOIN recent_apps  r ON r.ConsumerID = c.ConsumerID
)
SELECT consumer      AS "Consumer",
       score         AS "FICO 8",
       open_debt     AS "Open debt",
       past_due      AS "Past due",
       collections   AS "Collections",
       hard_24mo     AS "Hard inquiries (24 mo)",
       utilization   AS "Utilization (pct)",
       CASE
         WHEN collections > 0 OR past_due > 0                THEN 'High'
         WHEN score < 670 OR utilization > 30 OR hard_24mo >= 2 THEN 'Elevated'
         ELSE 'Low'
       END           AS "Risk tier"
  FROM profile
 ORDER BY CASE
            WHEN collections > 0 OR past_due > 0                THEN 1
            WHEN score < 670 OR utilization > 30 OR hard_24mo >= 2 THEN 2
            ELSE 3
          END,
          score;""",
        "explain": [
            "Four named subqueries, each answering one question, and a "
            "fourth (profile) that is built out of the first three. "
            "Written as nested subqueries this would be unreadable.",
            "LEFT JOIN onto each CTE keeps consumers who have no score, no "
            "debt or no inquiries; COALESCE turns their missing values into 0.",
            "The liability CTE leaves out Authorized User links. Lorna "
            "Featherstone is an authorized user on Marcus Whitfield's card: "
            "it is on her file, but its balance is not her debt.",
        ],
    },
    {
        "id": "with-recursive-calendar",
        "category": "with",
        "title": "Monthly late-payment calendar",
        "question": "For each of the last N months, how many payment "
                    "reports were on time and how many were late, "
                    "including months with no data?",
        "concepts": ["WITH RECURSIVE", "gap filling", "LEFT JOIN", "FILTER"],
        "params": [
            {"name": "months", "label": "Months to show", "type": "int",
             "default": 30, "min": 1, "max": 84},
        ],
        "sql": """\
WITH RECURSIVE calendar(month, n) AS (
    -- Anchor: the most recent reported month.
    SELECT (SELECT MAX(ReportMonth) FROM PaymentHistory), 1

    UNION ALL

    -- Recursive step: one month earlier, until N months exist.
    SELECT (month - INTERVAL '1 month')::date, n + 1
      FROM calendar
     WHERE n < %(months)s
),
reported AS (
    SELECT ReportMonth,
           COUNT(*)                                                AS reports,
           COUNT(*) FILTER (WHERE StatusCode = 'OK')               AS on_time,
           COUNT(*) FILTER (WHERE StatusCode IN
                     ('30','60','90','120','150','180'))           AS late
      FROM PaymentHistory
     GROUP BY ReportMonth
)
SELECT TO_CHAR(cal.month, 'YYYY-MM')   AS "Month",
       COALESCE(r.reports, 0)          AS "Reports",
       COALESCE(r.on_time, 0)          AS "On time",
       COALESCE(r.late, 0)             AS "Late",
       CASE WHEN r.reports IS NULL THEN 'no data reported' ELSE '' END
                                       AS "Note"
  FROM calendar cal
  LEFT JOIN reported r ON r.ReportMonth = cal.month
 ORDER BY cal.month DESC;""",
        "explain": [
            "A recursive CTE has an anchor row and a step that refers to "
            "the CTE itself. PostgreSQL repeats the step until it returns "
            "nothing - here, until n reaches the number you asked for.",
            "Why bother: GROUP BY ReportMonth can only produce months that "
            "have data. A report that silently skips empty months misleads. "
            "Generating the calendar first and LEFT JOINing onto it makes "
            "the gaps visible. Ask for more than 24 months to see them.",
            "Months is validated as a whole number between 1 and 84 (the "
            "seven-year retention window) before the query is sent.",
        ],
    },

    # =================================================================
    # ADVANCED AGGREGATES
    # =================================================================
    {
        "id": "agg-creditor-portfolio",
        "category": "aggregate",
        "title": "Creditor portfolio scorecard",
        "question": "For each creditor: how many tradelines, how many "
                    "delinquent, how much owed, and which products?",
        "concepts": ["FILTER", "HAVING", "STRING_AGG DISTINCT", "AVG", "ratio"],
        "params": [
            {"name": "min_accounts", "label": "Minimum tradelines",
             "type": "int", "default": 1, "min": 1, "max": 100},
        ],
        "sql": """\
SELECT cr.CreditorName                                   AS "Creditor",
       cr.BusinessType                                   AS "Industry",
       COUNT(a.AccountID)                                AS "Tradelines",
       COUNT(*) FILTER (WHERE a.AccountStatus = 'Open')  AS "Open",
       COUNT(*) FILTER (WHERE a.PastDueAmount > 0)       AS "Delinquent",
       ROUND(100.0 * COUNT(*) FILTER (WHERE a.PastDueAmount > 0)
             / COUNT(*), 1)                              AS "Delinquency (pct)",
       SUM(a.CurrentBalance)                             AS "Total balance",
       ROUND(AVG(a.CurrentBalance), 2)                   AS "Average balance",
       STRING_AGG(DISTINCT a.AccountType, ', ')          AS "Products"
  FROM Creditor cr
  JOIN Account a ON a.CreditorID = cr.CreditorID
 GROUP BY cr.CreditorID, cr.CreditorName, cr.BusinessType
HAVING COUNT(a.AccountID) >= %(min_accounts)s
 ORDER BY "Total balance" DESC;""",
        "explain": [
            "FILTER (WHERE ...) restricts one aggregate to a subset of the "
            "group, so open, delinquent and total counts come out of a "
            "single pass instead of three separate queries.",
            "HAVING filters groups after aggregation - WHERE cannot, "
            "because the count does not exist yet when WHERE runs. Raise "
            "the minimum to 2 to keep only creditors with several accounts.",
            "STRING_AGG(DISTINCT ...) collapses the group's product types "
            "into one readable cell.",
        ],
    },
    {
        "id": "agg-score-distribution",
        "category": "aggregate",
        "title": "Score distribution by birth decade",
        "question": "What does the spread of current FICO 8 scores look like "
                    "for each generation of consumers?",
        "concepts": ["PERCENTILE_CONT", "MODE()", "STDDEV_SAMP", "WITHIN GROUP"],
        "params": [],
        "sql": """\
WITH latest_fico8 AS (
    SELECT DISTINCT ON (ConsumerID) ConsumerID, ScoreValue
      FROM CreditScore
     WHERE ScoreModel = 'FICO Score 8'
     ORDER BY ConsumerID, ScoreDate DESC
)
SELECT (c.YearOfBirth / 10 * 10) || 's'          AS "Born in",
       COUNT(*)                                  AS "Consumers",
       MIN(s.ScoreValue)                         AS "Lowest",
       MAX(s.ScoreValue)                         AS "Highest",
       ROUND(AVG(s.ScoreValue), 1)               AS "Mean",
       PERCENTILE_CONT(0.5)
         WITHIN GROUP (ORDER BY s.ScoreValue)    AS "Median",
       ROUND(STDDEV_SAMP(s.ScoreValue), 1)       AS "Std deviation",
       MODE()
         WITHIN GROUP (ORDER BY fn_score_band(s.ScoreValue))
                                                 AS "Most common band"
  FROM latest_fico8 s
  JOIN Consumer c ON c.ConsumerID = s.ConsumerID
 GROUP BY c.YearOfBirth / 10
 ORDER BY c.YearOfBirth / 10;""",
        "explain": [
            "PERCENTILE_CONT and MODE are ordered-set aggregates: they need "
            "the group's values sorted, which is what WITHIN GROUP "
            "(ORDER BY ...) supplies. The median interpolates between the "
            "two middle values when a group has an even count.",
            "STDDEV_SAMP is blank for a decade with one consumer. That is "
            "correct, not a bug: sample standard deviation divides by "
            "n - 1, so it is undefined for a single value.",
            "MODE() is applied to the D2 fn_score_band function, so the "
            "aggregate runs over a derived label rather than a stored column.",
        ],
    },

    # =================================================================
    # OLAP
    # =================================================================
    {
        "id": "olap-rollup-balances",
        "category": "olap",
        "title": "Open balances with subtotals (ROLLUP)",
        "question": "Total open balances by account category and type, with "
                    "a subtotal per category and a grand total.",
        "concepts": ["GROUP BY ROLLUP", "GROUPING()", "hierarchical subtotals"],
        "params": [],
        "sql": """\
SELECT CASE WHEN GROUPING(a.AccountCategory) = 1 THEN 'All categories'
            ELSE a.AccountCategory END                AS "Category",
       CASE WHEN GROUPING(a.AccountCategory) = 1 THEN 'Grand total'
            WHEN GROUPING(a.AccountType)     = 1 THEN 'Subtotal'
            ELSE a.AccountType END                    AS "Type",
       COUNT(*)                                       AS "Accounts",
       SUM(a.CurrentBalance)                          AS "Balance",
       SUM(a.PastDueAmount)                           AS "Past due",
       GROUPING(a.AccountCategory, a.AccountType)     AS "_level"
  FROM Account a
 WHERE a.AccountStatus = 'Open'
 GROUP BY ROLLUP (a.AccountCategory, a.AccountType)
 ORDER BY GROUPING(a.AccountCategory), a.AccountCategory,
          GROUPING(a.AccountType),     a.AccountType;""",
        "explain": [
            "ROLLUP(category, type) produces three grouping levels in one "
            "query: (category, type), (category) and (). That is the detail "
            "rows, a subtotal for each category and the grand total.",
            "In subtotal rows the rolled-up column is NULL. GROUPING() "
            "returns 1 for exactly those columns, which is how the CASE "
            "expressions label them 'Subtotal' and 'Grand total' instead of "
            "showing a blank.",
            "GROUPING(category, type) as a bitmask (0, 1 or 3) is also how "
            "this page knows to style subtotal rows in bold.",
        ],
    },
    {
        "id": "olap-cube-inquiries",
        "category": "olap",
        "title": "Inquiries cross-tab (CUBE)",
        "question": "Inquiry counts by type and purpose, with totals along "
                    "every dimension.",
        "concepts": ["GROUP BY CUBE", "GROUPING()", "COUNT DISTINCT"],
        "params": [],
        "sql": """\
SELECT CASE WHEN GROUPING(i.InquiryType) = 1 THEN 'All types'
            ELSE i.InquiryType END                    AS "Inquiry type",
       CASE WHEN GROUPING(i.PurposeType) = 1 THEN 'All purposes'
            ELSE i.PurposeType END                    AS "Purpose",
       COUNT(*)                                       AS "Inquiries",
       COUNT(DISTINCT i.ConsumerID)                   AS "Consumers",
       MIN(i.InquiryDate)                             AS "Earliest",
       MAX(i.InquiryDate)                             AS "Latest",
       GROUPING(i.InquiryType, i.PurposeType)         AS "_level"
  FROM Inquiry i
 GROUP BY CUBE (i.InquiryType, i.PurposeType)
 ORDER BY GROUPING(i.InquiryType), i.InquiryType,
          GROUPING(i.PurposeType), i.PurposeType;""",
        "explain": [
            "CUBE(a, b) produces every combination of groupings: (a, b), "
            "(a), (b) and (). ROLLUP only goes down one hierarchy; CUBE "
            "also gives the totals across the other dimension - here, "
            "the count for each purpose regardless of hard or soft.",
            "COUNT(DISTINCT ConsumerID) is not additive: the 'All' rows "
            "count people once even if they had several inquiries, so they "
            "can be smaller than the sum of the rows above them.",
        ],
    },
    {
        "id": "olap-window-exposure",
        "category": "olap",
        "title": "Debt ranking (window functions)",
        "question": "Rank consumers by the open debt they are liable for, "
                    "with quartile, share of total and running total.",
        "concepts": ["RANK()", "NTILE()", "PERCENT_RANK()", "SUM() OVER", "named WINDOW"],
        "params": [],
        "sql": """\
WITH exposure AS (
    SELECT c.ConsumerID,
           CONCAT_WS(' ', c.FirstName, c.LastName, c.Suffix) AS consumer,
           SUM(a.CurrentBalance)            AS debt
      FROM Consumer c
      JOIN ConsumerAccount ca ON ca.ConsumerID = c.ConsumerID
      JOIN Account a          ON a.AccountID   = ca.AccountID
     WHERE a.AccountStatus = 'Open'
       AND ca.ResponsibilityType <> 'Authorized User'
     GROUP BY c.ConsumerID
)
SELECT RANK()  OVER w                               AS "Rank",
       consumer                                     AS "Consumer",
       debt                                         AS "Open debt",
       NTILE(4) OVER w                              AS "Quartile",
       ROUND(100 * debt / SUM(debt) OVER (), 1)     AS "Share of debt (pct)",
       SUM(debt) OVER (w ROWS UNBOUNDED PRECEDING)  AS "Running total",
       ROUND((100 * PERCENT_RANK() OVER (ORDER BY debt))::numeric, 0)
                                                    AS "Percentile"
  FROM exposure
WINDOW w AS (ORDER BY debt DESC)
 ORDER BY "Rank", "Consumer";""",
        "explain": [
            "A window function computes over a set of rows related to the "
            "current one without collapsing them the way GROUP BY does - "
            "every consumer keeps their own row and also gets a rank.",
            "SUM(debt) OVER () with an empty window is the total over all "
            "rows, which turns each debt into a percentage. Adding "
            "ROWS UNBOUNDED PRECEDING turns the same SUM into a running total.",
            "Joint accounts count in full for each joint holder, because "
            "each is liable for the whole balance. That is why the two "
            "joint mortgage holders tie on rank and the shares can add up "
            "to more than the bureau's actual lending.",
        ],
    },
    {
        "id": "olap-window-score-trend",
        "category": "olap",
        "title": "Score movement (LAG, PARTITION BY)",
        "question": "How did each consumer's FICO 8 score change between "
                    "reports, and who moved the most?",
        "concepts": ["LAG()", "PARTITION BY", "FIRST_VALUE()", "DENSE_RANK()"],
        "params": [],
        "sql": """\
WITH history AS (
    SELECT cs.ConsumerID,
           CONCAT_WS(' ', c.FirstName, c.LastName, c.Suffix) AS consumer,
           cs.ScoreDate,
           cs.ScoreValue,
           -- previous score for the SAME consumer
           LAG(cs.ScoreValue) OVER (PARTITION BY cs.ConsumerID
                                    ORDER BY cs.ScoreDate)        AS prev_score,
           FIRST_VALUE(cs.ScoreValue) OVER (PARTITION BY cs.ConsumerID
                                    ORDER BY cs.ScoreDate)        AS first_score
      FROM CreditScore cs
      JOIN Consumer c ON c.ConsumerID = cs.ConsumerID
     WHERE cs.ScoreModel = 'FICO Score 8'
)
SELECT consumer                                   AS "Consumer",
       ScoreDate                                  AS "Report date",
       prev_score                                 AS "Previous",
       ScoreValue                                 AS "Current",
       ScoreValue - prev_score                    AS "Change",
       fn_score_band(prev_score::smallint) || ' -> ' || fn_score_band(ScoreValue)
                                                  AS "Band movement",
       DENSE_RANK() OVER (ORDER BY ABS(ScoreValue - prev_score) DESC)
                                                  AS "Biggest mover rank"
  FROM history
 WHERE prev_score IS NOT NULL       -- first report has nothing to compare to
 ORDER BY "Biggest mover rank", "Consumer";""",
        "explain": [
            "PARTITION BY ConsumerID restarts the window for each person, "
            "so LAG() fetches that consumer's previous score and never "
            "reaches across into somebody else's history.",
            "The outer query then ranks the changes across everyone with a "
            "second window function. DENSE_RANK gives tied movers the same "
            "rank without leaving a gap after them.",
            "Aaron Castellanos Jr and Terrence Boyle lost the most points - "
            "both have accounts past due. That is the delinquency showing "
            "up in the score.",
        ],
    },
]


# Lookup tables used by the routes.
QUERIES_BY_ID = {q["id"]: q for q in QUERIES}
CATEGORIES_BY_KEY = {c["key"]: c for c in CATEGORIES}


def queries_in(category_key):
    """All queries in one category, in definition order."""
    return [q for q in QUERIES if q["category"] == category_key]


# =====================================================================
# SQL console starter templates
# =====================================================================
# Short frames the console can drop into the editor with one click.
# Each one runs as-is against the D2 schema, so a template is never a
# syntax error waiting to happen; the comment marks the part to change.

CONSOLE_TEMPLATES = [
    {"label": "SELECT", "sql": """\
-- Basic query: change the columns, table and filter
SELECT FirstName, LastName, YearOfBirth
  FROM Consumer
 WHERE YearOfBirth >= 1990
 ORDER BY LastName;"""},

    {"label": "JOIN", "sql": """\
-- Join two tables on their key
SELECT c.FirstName, c.LastName, a.AccountType, a.CurrentBalance
  FROM Consumer c
  JOIN ConsumerAccount ca ON ca.ConsumerID = c.ConsumerID
  JOIN Account a          ON a.AccountID   = ca.AccountID
 ORDER BY a.CurrentBalance DESC;"""},

    {"label": "GROUP BY", "sql": """\
-- Aggregate per group; HAVING filters the groups
SELECT AccountCategory,
       COUNT(*)            AS accounts,
       SUM(CurrentBalance) AS total_balance
  FROM Account
 GROUP BY AccountCategory
HAVING COUNT(*) >= 2
 ORDER BY total_balance DESC;"""},

    {"label": "UNION", "sql": """\
-- Stack two queries with the same columns (UNION removes duplicates)
SELECT ConsumerID, 'Has a score' AS source FROM CreditScore
UNION
SELECT ConsumerID, 'Has an inquiry'       FROM Inquiry
 ORDER BY ConsumerID;"""},

    {"label": "IN subquery", "sql": """\
-- Keep rows whose value appears in a subquery's result
SELECT FirstName, LastName
  FROM Consumer
 WHERE ConsumerID IN (
         SELECT ConsumerID
           FROM Inquiry
          WHERE InquiryType = 'Hard');"""},

    {"label": "> ALL", "sql": """\
-- Compare against every row of a subquery (try SOME instead of ALL)
SELECT AccountID, AccountType, CurrentBalance
  FROM Account
 WHERE CurrentBalance > ALL (
         SELECT CurrentBalance
           FROM Account
          WHERE AccountCategory = 'Revolving');"""},

    {"label": "WITH", "sql": """\
-- Name an intermediate result, then query it
WITH balances AS (
    SELECT ca.ConsumerID, SUM(a.CurrentBalance) AS total
      FROM ConsumerAccount ca
      JOIN Account a ON a.AccountID = ca.AccountID
     GROUP BY ca.ConsumerID
)
SELECT c.FirstName, c.LastName, b.total
  FROM balances b
  JOIN Consumer c ON c.ConsumerID = b.ConsumerID
 ORDER BY b.total DESC;"""},

    {"label": "Recursive", "sql": """\
-- Generate rows with WITH RECURSIVE: change the 12 to any count
WITH RECURSIVE months(month, n) AS (
    SELECT DATE '2026-01-01', 1
    UNION ALL
    SELECT (month + INTERVAL '1 month')::date, n + 1
      FROM months
     WHERE n < 12
)
SELECT month FROM months;"""},

    {"label": "ROLLUP", "sql": """\
-- Subtotals per group plus a grand total (try CUBE)
SELECT AccountCategory, AccountStatus,
       COUNT(*)            AS accounts,
       SUM(CurrentBalance) AS balance
  FROM Account
 GROUP BY ROLLUP (AccountCategory, AccountStatus)
 ORDER BY AccountCategory, AccountStatus;"""},

    {"label": "Window", "sql": """\
-- Rank rows without collapsing them (try DENSE_RANK, NTILE(4), LAG)
SELECT AccountID, AccountCategory, CurrentBalance,
       RANK() OVER (PARTITION BY AccountCategory
                    ORDER BY CurrentBalance DESC) AS rank_in_category
  FROM Account
 ORDER BY AccountCategory, rank_in_category;"""},
]
