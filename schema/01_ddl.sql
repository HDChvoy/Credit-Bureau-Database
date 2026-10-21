-- =====================================================================
-- Deliverable #2, Task 1: Data Definition Language
-- Experian Consumer Credit Database
-- PostgreSQL 16
--
-- Nine relations reduced from a seven-entity ERD. The two extra
-- relations are ConsumerAccount (from the M:N relationship) and
-- PaymentHistory (the weak entity).
-- =====================================================================

DROP TABLE IF EXISTS AccountAudit      CASCADE;
DROP TABLE IF EXISTS PaymentHistory    CASCADE;
DROP TABLE IF EXISTS ConsumerAccount   CASCADE;
DROP TABLE IF EXISTS CreditScore       CASCADE;
DROP TABLE IF EXISTS Inquiry           CASCADE;
DROP TABLE IF EXISTS Account           CASCADE;
DROP TABLE IF EXISTS Address           CASCADE;
DROP TABLE IF EXISTS Creditor          CASCADE;
DROP TABLE IF EXISTS Consumer          CASCADE;


-- ---------------------------------------------------------------------
-- 1. Consumer
--    Surrogate PK. A natural key built from name/address/phone was
--    rejected: those attributes are mutable, non-unique (a father and
--    son at one address), and nullable.
-- ---------------------------------------------------------------------
CREATE TABLE Consumer (
    ConsumerID          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    FirstName           VARCHAR(40)  NOT NULL,
    MiddleName          VARCHAR(40),
    LastName            VARCHAR(40)  NOT NULL,
    Suffix              VARCHAR(10),
    SSN_Masked          CHAR(11)     NOT NULL,
    YearOfBirth         SMALLINT     NOT NULL,
    PrimaryPhone        VARCHAR(20),
    EmailAddress        VARCHAR(120),
    EnrollmentDate      DATE         NOT NULL DEFAULT CURRENT_DATE,
    SecurityFreezeFlag  BOOLEAN      NOT NULL DEFAULT FALSE,
    FreezeStartDate     DATE,
    FraudAlertFlag      BOOLEAN      NOT NULL DEFAULT FALSE,
    DeceasedFlag        BOOLEAN      NOT NULL DEFAULT FALSE,

    CONSTRAINT chk_consumer_birthyear
        CHECK (YearOfBirth BETWEEN 1900 AND EXTRACT(YEAR FROM CURRENT_DATE)),
    -- Experian publishes only the year of birth, not the full date.
    CONSTRAINT chk_consumer_ssn_format
        CHECK (SSN_Masked ~ '^XXX-XX-[0-9]{4}$'),
    -- Only the last four digits are ever stored.
    CONSTRAINT chk_consumer_freeze_date
        CHECK ((SecurityFreezeFlag = FALSE AND FreezeStartDate IS NULL)
            OR (SecurityFreezeFlag = TRUE  AND FreezeStartDate IS NOT NULL))
);

COMMENT ON TABLE  Consumer IS 'An individual with a credit file at the bureau.';
COMMENT ON COLUMN Consumer.SSN_Masked IS 'Last four digits only; full SSN is never stored.';
COMMENT ON COLUMN Consumer.YearOfBirth IS 'Year only; matches what Experian reports and minimises PII.';


-- ---------------------------------------------------------------------
-- 2. Address
--    Models consumer address HISTORY, not addresses as independent
--    real-world objects. That is why it is 1:N from Consumer and why
--    two spouses at one house produce two rows.
-- ---------------------------------------------------------------------
CREATE TABLE Address (
    AddressID           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ConsumerID          INTEGER      NOT NULL,
    StreetLine1         VARCHAR(80)  NOT NULL,
    StreetLine2         VARCHAR(40),
    City                VARCHAR(50)  NOT NULL,
    StateCode           CHAR(2)      NOT NULL,
    PostalCode          VARCHAR(10)  NOT NULL,
    AddressType         VARCHAR(20)  NOT NULL DEFAULT 'Residential',
    FirstReportedDate   DATE         NOT NULL,
    LastReportedDate    DATE         NOT NULL,
    IsCurrent           BOOLEAN      NOT NULL DEFAULT FALSE,

    CONSTRAINT fk_address_consumer
        FOREIGN KEY (ConsumerID) REFERENCES Consumer(ConsumerID) ON DELETE CASCADE,
    CONSTRAINT chk_address_type
        CHECK (AddressType IN ('Residential','Mailing','Business','PO Box')),
    CONSTRAINT chk_address_dates
        CHECK (LastReportedDate >= FirstReportedDate)
);

COMMENT ON COLUMN Address.FirstReportedDate IS
    'When a furnisher first reported this address, NOT when the consumer moved in. The bureau cannot observe a move.';


-- ---------------------------------------------------------------------
-- 3. Creditor
--    One entity for lenders, collection agencies, and inquiring
--    businesses. They are the same kind of thing playing different
--    roles; role belongs to the relationship, not the entity.
-- ---------------------------------------------------------------------
CREATE TABLE Creditor (
    CreditorID          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    SubscriberCode      VARCHAR(12)  NOT NULL UNIQUE,   -- candidate key
    CreditorName        VARCHAR(80)  NOT NULL,
    BusinessType        VARCHAR(40)  NOT NULL,
    StreetLine1         VARCHAR(80),
    City                VARCHAR(50),
    StateCode           CHAR(2),
    PostalCode          VARCHAR(10),
    Phone               VARCHAR(20),
    IsDataFurnisher     BOOLEAN      NOT NULL DEFAULT TRUE,

    CONSTRAINT chk_creditor_bustype
        CHECK (BusinessType IN ('Bank Credit Cards','Automobile Financing',
                                'Mortgage Lender','Student Loan Servicer',
                                'Personal Loan','Collection Agency',
                                'Collection Attorney','Utility/Telecom'))
);

COMMENT ON COLUMN Creditor.SubscriberCode IS
    'The furnisher''s registered code with the bureau. A genuine candidate key, kept UNIQUE but not used as the PK.';


-- ---------------------------------------------------------------------
-- 4. Account
--    Carries NO ConsumerID. Ownership lives in ConsumerAccount,
--    because an account can appear on more than one credit file.
--    Two FKs to Creditor: the current holder and, for collections
--    only, the original creditor.
-- ---------------------------------------------------------------------
CREATE TABLE Account (
    AccountID           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    CreditorID          INTEGER      NOT NULL,
    OriginalCreditorID  INTEGER,
    AccountNumberMasked VARCHAR(20)  NOT NULL,
    AccountCategory     VARCHAR(15)  NOT NULL,
    AccountType         VARCHAR(30)  NOT NULL,
    DateOpened          DATE         NOT NULL,
    DateClosed          DATE,
    TermsMonths         SMALLINT,
    CreditLimit         NUMERIC(12,2),
    OriginalLoanAmount  NUMERIC(12,2),
    CurrentBalance      NUMERIC(12,2) NOT NULL DEFAULT 0,
    MonthlyPayment      NUMERIC(10,2),
    PastDueAmount       NUMERIC(10,2) NOT NULL DEFAULT 0,
    DateLastActivity    DATE,
    PaymentStatus       VARCHAR(20)  NOT NULL DEFAULT 'Current',
    PaymentStatusDate   DATE,
    AccountStatus       VARCHAR(15)  NOT NULL DEFAULT 'Open',

    CONSTRAINT fk_account_creditor
        FOREIGN KEY (CreditorID) REFERENCES Creditor(CreditorID) ON DELETE RESTRICT,
    CONSTRAINT fk_account_origcreditor
        FOREIGN KEY (OriginalCreditorID) REFERENCES Creditor(CreditorID) ON DELETE RESTRICT,
    CONSTRAINT uq_account_number
        UNIQUE (CreditorID, AccountNumberMasked),

    CONSTRAINT chk_account_category
        CHECK (AccountCategory IN ('Revolving','Installment','Open','Collection')),
    CONSTRAINT chk_account_status
        CHECK (AccountStatus IN ('Open','Closed','Transferred','Paid')),

    -- Experian shows one field labelled "Credit Limit / Original Balance".
    -- Which one is populated is determined by the account category.
    CONSTRAINT chk_account_amount_disjoint
        CHECK (
            (AccountCategory = 'Revolving'
                 AND CreditLimit IS NOT NULL AND OriginalLoanAmount IS NULL)
         OR (AccountCategory = 'Installment'
                 AND OriginalLoanAmount IS NOT NULL AND CreditLimit IS NULL)
         OR (AccountCategory IN ('Open','Collection'))
        ),

    -- A collection is an account that changed hands: it must name
    -- where it came from, and nothing else may.
    CONSTRAINT chk_account_collection_origin
        CHECK (
            (AccountCategory  = 'Collection' AND OriginalCreditorID IS NOT NULL)
         OR (AccountCategory <> 'Collection' AND OriginalCreditorID IS NULL)
        ),

    CONSTRAINT chk_account_dates
        CHECK (DateClosed IS NULL OR DateClosed >= DateOpened),
    CONSTRAINT chk_account_not_future
        CHECK (DateOpened <= CURRENT_DATE),
    CONSTRAINT chk_account_closed_has_date
        CHECK (AccountStatus <> 'Closed' OR DateClosed IS NOT NULL),
    CONSTRAINT chk_account_amounts_nonneg
        CHECK (CurrentBalance >= 0 AND PastDueAmount >= 0
               AND COALESCE(CreditLimit,0) >= 0
               AND COALESCE(OriginalLoanAmount,0) >= 0),

    -- Delinquency agreement: money past due contradicts a "Current" status.
    CONSTRAINT chk_account_pastdue_agrees
        CHECK (PastDueAmount = 0 OR PaymentStatus <> 'Current')

    -- NOTE: CurrentBalance <= CreditLimit is deliberately NOT enforced.
    -- Over-limit accounts genuinely exist.
);

COMMENT ON TABLE Account IS
    'A tradeline. Ownership is in ConsumerAccount because joint and authorized-user accounts appear on several files.';


-- ---------------------------------------------------------------------
-- 5. ConsumerAccount  (M:N junction)
--    ResponsibilityType is an attribute OF THE RELATIONSHIP: the same
--    account is "Individual" to one person and "Authorized User" to
--    another. The composite PK also enforces, for free, that one
--    consumer cannot hold two responsibility rows on one account.
-- ---------------------------------------------------------------------
CREATE TABLE ConsumerAccount (
    ConsumerID          INTEGER      NOT NULL,
    AccountID           INTEGER      NOT NULL,
    ResponsibilityType  VARCHAR(20)  NOT NULL,
    DateAssociated      DATE         NOT NULL,
    DateRemoved         DATE,

    CONSTRAINT pk_consumeraccount PRIMARY KEY (ConsumerID, AccountID),
    CONSTRAINT fk_ca_consumer
        FOREIGN KEY (ConsumerID) REFERENCES Consumer(ConsumerID) ON DELETE CASCADE,
    CONSTRAINT fk_ca_account
        FOREIGN KEY (AccountID)  REFERENCES Account(AccountID)   ON DELETE CASCADE,
    CONSTRAINT chk_ca_responsibility
        CHECK (ResponsibilityType IN ('Individual','Joint','Cosigner','Authorized User')),
    CONSTRAINT chk_ca_dates
        CHECK (DateRemoved IS NULL OR DateRemoved >= DateAssociated)
);

COMMENT ON COLUMN ConsumerAccount.ResponsibilityType IS
    'Authorized users inherit the payment history onto their file without liability for the balance.';


-- ---------------------------------------------------------------------
-- 6. PaymentHistory  (weak entity)
--    No identifier of its own: a month is meaningless without the
--    account it describes. Identified by (AccountID, ReportMonth),
--    existence-dependent, ON DELETE CASCADE.
-- ---------------------------------------------------------------------
CREATE TABLE PaymentHistory (
    AccountID               INTEGER      NOT NULL,
    ReportMonth             DATE         NOT NULL,
    StatusCode              VARCHAR(4)   NOT NULL,
    BalanceAmount           NUMERIC(12,2),
    ScheduledPaymentAmount  NUMERIC(10,2),

    CONSTRAINT pk_paymenthistory PRIMARY KEY (AccountID, ReportMonth),
    CONSTRAINT fk_ph_account
        FOREIGN KEY (AccountID) REFERENCES Account(AccountID) ON DELETE CASCADE,
    CONSTRAINT chk_ph_status
        CHECK (StatusCode IN ('ND','OK','30','60','90','120','150','180',
                              'CLS','BK','C','CO','D','F','FS','G','IC',
                              'PBC','R','VS')),
    CONSTRAINT chk_ph_month_is_first
        CHECK (EXTRACT(DAY FROM ReportMonth) = 1),
    CONSTRAINT chk_ph_not_future
        CHECK (ReportMonth <= CURRENT_DATE)
);

COMMENT ON TABLE PaymentHistory IS
    'Weak entity. One row per account per month. Largest relation in the schema: 84 rows per account at full 7-year retention.';
COMMENT ON COLUMN PaymentHistory.StatusCode IS
    'ND=no data, OK=current, 30..180=days late, CO=charge-off, R=repossession, F=foreclosure, BK=bankruptcy, etc.';


-- ---------------------------------------------------------------------
-- 7. Inquiry
--    The only entity with two mandatory parents: somebody was
--    inquired about, and somebody did the inquiring.
-- ---------------------------------------------------------------------
CREATE TABLE Inquiry (
    InquiryID           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ConsumerID          INTEGER      NOT NULL,
    CreditorID          INTEGER      NOT NULL,
    InquiryDate         DATE         NOT NULL,
    InquiryType         VARCHAR(6)   NOT NULL,
    PurposeType         VARCHAR(30)  NOT NULL,
    PermissiblePurpose  VARCHAR(60),
    RemovalDate         DATE,

    CONSTRAINT fk_inquiry_consumer
        FOREIGN KEY (ConsumerID) REFERENCES Consumer(ConsumerID) ON DELETE CASCADE,
    CONSTRAINT fk_inquiry_creditor
        FOREIGN KEY (CreditorID) REFERENCES Creditor(CreditorID) ON DELETE RESTRICT,
    CONSTRAINT chk_inquiry_type
        CHECK (InquiryType IN ('Hard','Soft')),
    CONSTRAINT chk_inquiry_purpose
        CHECK (PurposeType IN ('Auto Loan','Mortgage','Credit Card','Personal Loan',
                               'Student Loan','Account Review','Prescreen',
                               'Consumer Self-Check')),
    CONSTRAINT chk_inquiry_not_future
        CHECK (InquiryDate <= CURRENT_DATE)
);

COMMENT ON COLUMN Inquiry.RemovalDate IS
    'InquiryDate + 2 years for hard inquiries. Populated by trigger trg_inquiry_removal, not stored by hand.';


-- ---------------------------------------------------------------------
-- 8. CreditScore
--    Append-only. Scores are NOT recomputed: the models are
--    proprietary and the underlying tradelines purge, so a past score
--    can never be regenerated. Storing it is the only way it survives.
-- ---------------------------------------------------------------------
CREATE TABLE CreditScore (
    ScoreID             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ConsumerID          INTEGER      NOT NULL,
    ScoreModel          VARCHAR(20)  NOT NULL,
    ScoreValue          SMALLINT     NOT NULL,
    ScoreDate           DATE         NOT NULL,
    ScoreRangeMin       SMALLINT     NOT NULL,
    ScoreRangeMax       SMALLINT     NOT NULL,

    CONSTRAINT fk_score_consumer
        FOREIGN KEY (ConsumerID) REFERENCES Consumer(ConsumerID) ON DELETE CASCADE,
    CONSTRAINT uq_score_natural
        UNIQUE (ConsumerID, ScoreModel, ScoreDate),   -- candidate key
    CONSTRAINT chk_score_model
        CHECK (ScoreModel IN ('FICO Score 8','FICO Score 9','VantageScore 3.0',
                              'VantageScore 4.0','FICO Auto Score','FICO Bankcard')),
    -- The valid range depends on the model: 300-850 for the general
    -- models, 250-900 for the industry-specific FICO variants.
    CONSTRAINT chk_score_range_by_model
        CHECK (
            (ScoreModel IN ('FICO Score 8','FICO Score 9','VantageScore 3.0','VantageScore 4.0')
                 AND ScoreRangeMin = 300 AND ScoreRangeMax = 850)
         OR (ScoreModel IN ('FICO Auto Score','FICO Bankcard')
                 AND ScoreRangeMin = 250 AND ScoreRangeMax = 900)
        ),
    CONSTRAINT chk_score_within_range
        CHECK (ScoreValue BETWEEN ScoreRangeMin AND ScoreRangeMax)
);


-- ---------------------------------------------------------------------
-- 9. AccountAudit  (supporting table for the audit trigger)
--    Not part of the conceptual ERD; an implementation artifact
--    required by the trigger in 06_triggers.sql.
-- ---------------------------------------------------------------------
CREATE TABLE AccountAudit (
    AuditID         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    AccountID       INTEGER      NOT NULL,
    ChangedColumn   VARCHAR(30)  NOT NULL,
    OldValue        VARCHAR(50),
    NewValue        VARCHAR(50),
    ChangedAt       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ChangedBy       VARCHAR(40)  NOT NULL DEFAULT CURRENT_USER
);


-- ---------------------------------------------------------------------
-- Business rule enforced by a partial unique index rather than a CHECK:
-- a consumer may have many addresses but only ONE current address.
-- ---------------------------------------------------------------------
CREATE UNIQUE INDEX uq_one_current_address
    ON Address (ConsumerID)
    WHERE IsCurrent = TRUE;
