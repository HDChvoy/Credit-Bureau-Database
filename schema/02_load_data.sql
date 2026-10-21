-- =====================================================================
-- Deliverable #2, Task 2: Load mock data
-- Minimum 15 records per relation. All names, addresses, phone numbers
-- and account numbers are fabricated for coursework purposes.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Consumer (15 rows)
-- ---------------------------------------------------------------------
INSERT INTO Consumer
 (FirstName, MiddleName, LastName, Suffix, SSN_Masked, YearOfBirth,
  PrimaryPhone, EmailAddress, EnrollmentDate,
  SecurityFreezeFlag, FreezeStartDate, FraudAlertFlag, DeceasedFlag) VALUES
 ('Marcus','T','Whitfield',NULL,'XXX-XX-4821',1985,'312-555-0142','mwhitfield@example.com','2021-03-14',FALSE,NULL,FALSE,FALSE),
 ('Priya',NULL,'Raghunathan',NULL,'XXX-XX-9037',1990,'847-555-0198','praghu@example.com','2020-11-02',FALSE,NULL,FALSE,FALSE),
 ('Devon','L','Okafor',NULL,'XXX-XX-2264',1978,'773-555-0177','dokafor@example.com','2019-06-21',TRUE,'2024-02-10',FALSE,FALSE),
 ('Sylvia',NULL,'Brennan',NULL,'XXX-XX-5519',1962,'630-555-0110','sbrennan@example.com','2018-09-30',FALSE,NULL,FALSE,FALSE),
 ('Aaron','J','Castellanos','Jr','XXX-XX-7743',1995,'312-555-0165','acastellanos@example.com','2022-01-18',FALSE,NULL,TRUE,FALSE),
 ('Aaron','J','Castellanos','Sr','XXX-XX-3308',1968,'312-555-0165','acastellanos.sr@example.com','2017-04-05',FALSE,NULL,FALSE,FALSE),
 ('Nadia',NULL,'Petrossian',NULL,'XXX-XX-6612',1988,'224-555-0133','npetrossian@example.com','2021-07-09',FALSE,NULL,FALSE,FALSE),
 ('Grant','R','Ishikawa',NULL,'XXX-XX-1187',1993,'708-555-0121','gishikawa@example.com','2023-02-27',FALSE,NULL,FALSE,FALSE),
 ('Camille',NULL,'Dubois',NULL,'XXX-XX-4450',1981,'815-555-0154','cdubois@example.com','2020-05-16',FALSE,NULL,FALSE,FALSE),
 ('Terrence','M','Boyle',NULL,'XXX-XX-8896',1974,'331-555-0189','tboyle@example.com','2019-12-03',FALSE,NULL,FALSE,FALSE),
 ('Ingrid',NULL,'Halvorsen',NULL,'XXX-XX-2073',1999,'847-555-0146','ihalvorsen@example.com','2024-03-11',FALSE,NULL,FALSE,FALSE),
 ('Rashid','A','Bahri',NULL,'XXX-XX-5528',1986,'773-555-0192','rbahri@example.com','2021-10-22',FALSE,NULL,FALSE,FALSE),
 ('Lorna',NULL,'Featherstone',NULL,'XXX-XX-6684',1957,'630-555-0107','lfeatherstone@example.com','2016-08-14',FALSE,NULL,FALSE,TRUE),
 ('Emeka','C','Nwosu',NULL,'XXX-XX-3391',1992,'312-555-0173','enwosu@example.com','2022-06-08',FALSE,NULL,FALSE,FALSE),
 ('Beatrix',NULL,'Vandermolen',NULL,'XXX-XX-7015',1983,'708-555-0138','bvandermolen@example.com','2020-02-19',TRUE,'2025-11-01',TRUE,FALSE);


-- ---------------------------------------------------------------------
-- Address (20 rows; several consumers have prior addresses)
-- Consumers 5 and 6 (Castellanos Jr and Sr) deliberately share an
-- address to demonstrate the mixed-file risk discussed in the design.
-- ---------------------------------------------------------------------
INSERT INTO Address
 (ConsumerID, StreetLine1, StreetLine2, City, StateCode, PostalCode,
  AddressType, FirstReportedDate, LastReportedDate, IsCurrent) VALUES
 ( 1,'4417 N Hermitage Ave','Apt 3B','Chicago','IL','60640','Residential','2019-01-15','2026-07-01',TRUE),
 ( 1,'812 W Cornelia Ave',NULL,'Chicago','IL','60657','Residential','2015-06-01','2018-12-20',FALSE),
 ( 2,'1330 Sherman Ave','Unit 705','Evanston','IL','60201','Residential','2020-08-10','2026-08-01',TRUE),
 ( 3,'5722 S Blackstone Ave',NULL,'Chicago','IL','60637','Residential','2017-03-22','2026-06-15',TRUE),
 ( 3,'PO Box 40881',NULL,'Chicago','IL','60640','PO Box','2021-05-01','2025-09-30',FALSE),
 ( 4,'229 Cottonwood Ln',NULL,'Naperville','IL','60540','Residential','2011-04-18','2026-08-01',TRUE),
 ( 5,'7140 Kilpatrick Ave',NULL,'Skokie','IL','60076','Residential','2022-01-05','2026-07-20',TRUE),
 ( 6,'7140 Kilpatrick Ave',NULL,'Skokie','IL','60076','Residential','2016-09-12','2026-07-20',TRUE),
 ( 7,'908 Ridge Rd','Apt 12','Wilmette','IL','60091','Residential','2021-06-30','2026-08-01',TRUE),
 ( 8,'3355 W Fullerton Ave','2F','Chicago','IL','60647','Residential','2023-02-14','2026-07-01',TRUE),
 ( 8,'1204 Elmwood Ave',NULL,'Berwyn','IL','60402','Residential','2019-08-01','2023-01-31',FALSE),
 ( 9,'615 Dundee Rd',NULL,'Rockford','IL','61103','Residential','2020-04-25','2026-06-01',TRUE),
 (10,'44 Waverly Pl',NULL,'Aurora','IL','60506','Residential','2018-11-11','2026-08-01',TRUE),
 (10,'2200 Corporate Blvd','Ste 400','Aurora','IL','60502','Business','2022-03-01','2026-05-01',FALSE),
 (11,'1877 Hawthorne Ct','Apt 9','Palatine','IL','60067','Residential','2024-02-28','2026-08-01',TRUE),
 (12,'6033 N Sheridan Rd','Unit 22C','Chicago','IL','60660','Residential','2021-09-15','2026-07-15',TRUE),
 (13,'85 Foxfield Dr',NULL,'Wheaton','IL','60187','Residential','2009-07-04','2025-12-01',TRUE),
 (14,'1140 S Wabash Ave','Apt 1802','Chicago','IL','60605','Residential','2022-05-20','2026-08-01',TRUE),
 (15,'3901 Ridgeland Ave',NULL,'Berwyn','IL','60402','Residential','2020-01-08','2026-07-01',TRUE),
 (15,'77 Linden St',NULL,'Oak Park','IL','60302','Mailing','2023-06-01','2026-04-01',FALSE);


-- ---------------------------------------------------------------------
-- Creditor (16 rows; lenders, agencies and inquiry-only businesses)
-- ---------------------------------------------------------------------
INSERT INTO Creditor
 (SubscriberCode, CreditorName, BusinessType, StreetLine1, City, StateCode,
  PostalCode, Phone, IsDataFurnisher) VALUES
 ('SUB-100241','Northgate Bank Card Services','Bank Credit Cards','500 Commerce Dr','Columbus','OH','43215','800-555-0301',TRUE),
 ('SUB-100377','Lakeshore Federal Credit Union','Bank Credit Cards','88 Lakeview Pkwy','Milwaukee','WI','53202','800-555-0312',TRUE),
 ('SUB-100418','Vantage Auto Finance','Automobile Financing','2100 Motorway Blvd','Dearborn','MI','48120','800-555-0324',TRUE),
 ('SUB-100522','Cardinal Home Lending','Mortgage Lender','410 Tower Sq','Des Moines','IA','50309','800-555-0335',TRUE),
 ('SUB-100689','Meridian Student Loan Servicing','Student Loan Servicer','75 Scholar Way','Harrisburg','PA','17101','800-555-0347',TRUE),
 ('SUB-100731','Copperfield Personal Credit','Personal Loan','1919 Bank St','Wilmington','DE','19801','800-555-0358',TRUE),
 ('SUB-100844','Ashcroft Recovery Group','Collection Agency','620 Industrial Rd','Buffalo','NY','14204','800-555-0369',TRUE),
 ('SUB-100950','Pemberton & Slade LLP','Collection Attorney','1 Courthouse Plz','Chicago','IL','60602','312-555-0370',TRUE),
 ('SUB-101066','Riverbend Utilities','Utility/Telecom','300 Water St','Peoria','IL','61602','309-555-0381',TRUE),
 ('SUB-101173','Summit Ridge Bankcard','Bank Credit Cards','44 Summit Ave','Sioux Falls','SD','57104','800-555-0392',TRUE),
 ('SUB-101288','Keystone Mortgage Corp','Mortgage Lender','950 Granite Way','Pittsburgh','PA','15222','800-555-0403',TRUE),
 ('SUB-101394','Trailhead Motors Credit','Automobile Financing','7700 Dealership Row','Fort Worth','TX','76102','800-555-0414',TRUE),
 ('SUB-101401','Beacon Rewards Card Co','Bank Credit Cards','12 Harbor St','Boston','MA','02110','800-555-0425',TRUE),
 ('SUB-101557','Halyard Insurance Services','Personal Loan','88 Windward Dr','Tampa','FL','33602','800-555-0436',FALSE),
 ('SUB-101663','Fairmount Leasing Partners','Personal Loan','2020 Fairmount Ave','Denver','CO','80202','800-555-0447',FALSE),
 ('SUB-101779','Quarry Creek Collections','Collection Agency','15 Quarry Rd','Toledo','OH','43604','800-555-0458',TRUE);


-- ---------------------------------------------------------------------
-- Account (20 rows)
-- Mix of revolving, installment, open and collection accounts so that
-- the disjoint amount constraint is exercised in every direction.
-- ---------------------------------------------------------------------
INSERT INTO Account
 (CreditorID, OriginalCreditorID, AccountNumberMasked, AccountCategory, AccountType,
  DateOpened, DateClosed, TermsMonths, CreditLimit, OriginalLoanAmount,
  CurrentBalance, MonthlyPayment, PastDueAmount, DateLastActivity,
  PaymentStatus, PaymentStatusDate, AccountStatus) VALUES
 ( 1,NULL,'************4417','Revolving','Credit Card','2018-05-12',NULL,NULL,12000.00,NULL,3247.88,95.00,0.00,'2026-08-01','Current','2026-08-01','Open'),
 ( 2,NULL,'************9921','Revolving','Credit Card','2020-09-03',NULL,NULL,6500.00,NULL,5980.14,180.00,0.00,'2026-08-01','Current','2026-08-01','Open'),
 ( 3,NULL,'**********7708','Installment','Auto Loan','2023-04-19',NULL,72,NULL,34500.00,24118.62,548.00,0.00,'2026-08-01','Current','2026-08-01','Open'),
 ( 4,NULL,'*********55031','Installment','Mortgage','2016-07-28',NULL,360,NULL,289000.00,231447.05,1685.00,0.00,'2026-08-01','Current','2026-08-01','Open'),
 ( 5,NULL,'**********2264','Installment','Student Loan','2012-08-30',NULL,120,NULL,42000.00,9832.77,410.00,0.00,'2026-07-01','Current','2026-07-01','Open'),
 ( 6,NULL,'************8140','Installment','Personal Loan','2024-01-15',NULL,48,NULL,15000.00,9421.30,362.00,724.00,'2026-06-01','30 Days Past Due','2026-07-01','Open'),
 ( 7,   1,'**********3055','Collection','Collection','2025-02-11',NULL,NULL,NULL,NULL,1842.00,0.00,1842.00,'2026-05-01','Collection','2026-08-01','Open'),
 ( 8,   9,'**********6612','Collection','Collection','2024-09-04',NULL,NULL,NULL,NULL,617.45,0.00,617.45,'2026-03-01','Collection','2026-08-01','Open'),
 ( 9,NULL,'*******44127','Open','Service Account','2019-11-20',NULL,NULL,NULL,NULL,142.66,142.66,0.00,'2026-08-01','Current','2026-08-01','Open'),
 (10,NULL,'************5519','Revolving','Credit Card','2014-03-08','2024-06-30',NULL,9000.00,NULL,0.00,NULL,0.00,'2024-06-30','Paid','2024-06-30','Closed'),
 (11,NULL,'*********71204','Installment','Mortgage','2021-06-14',NULL,360,NULL,412000.00,381209.44,2240.00,0.00,'2026-08-01','Current','2026-08-01','Open'),
 (12,NULL,'**********9037','Installment','Auto Loan','2022-10-02',NULL,60,NULL,27800.00,11455.19,512.00,0.00,'2026-08-01','Current','2026-08-01','Open'),
 (13,NULL,'************1187','Revolving','Credit Card','2023-03-27',NULL,NULL,3000.00,NULL,2871.00,75.00,0.00,'2026-08-01','Current','2026-08-01','Open'),
 ( 1,NULL,'************7743','Revolving','Charge Card','2022-02-09',NULL,NULL,5000.00,NULL,412.09,40.00,0.00,'2026-08-01','Current','2026-08-01','Open'),
 ( 2,NULL,'************3308','Revolving','Credit Card','2011-01-19',NULL,NULL,20000.00,NULL,1105.42,60.00,0.00,'2026-08-01','Current','2026-08-01','Open'),
 ( 3,NULL,'**********4450','Installment','Auto Loan','2019-05-23','2024-05-23',60,NULL,22000.00,0.00,NULL,0.00,'2024-05-23','Paid','2024-05-23','Closed'),
 (10,NULL,'************8896','Revolving','Credit Card','2017-09-11',NULL,NULL,15000.00,NULL,13890.55,420.00,840.00,'2026-05-01','60 Days Past Due','2026-08-01','Open'),
 ( 6,NULL,'**********2073','Installment','Personal Loan','2025-04-08',NULL,36,NULL,8000.00,6733.12,258.00,0.00,'2026-08-01','Current','2026-08-01','Open'),
 (16,   9,'**********5528','Collection','Collection','2026-01-16',NULL,NULL,NULL,NULL,389.20,0.00,389.20,'2026-06-01','Collection','2026-08-01','Open'),
 ( 5,NULL,'**********3391','Installment','Student Loan','2015-09-01',NULL,120,NULL,58000.00,21044.90,505.00,0.00,'2026-08-01','Current','2026-08-01','Open');


-- ---------------------------------------------------------------------
-- ConsumerAccount (24 rows; the M:N junction)
-- Accounts 4 and 11 are joint mortgages appearing on two files.
-- Account 15 carries an authorized user who is not liable for it.
-- ---------------------------------------------------------------------
INSERT INTO ConsumerAccount
 (ConsumerID, AccountID, ResponsibilityType, DateAssociated, DateRemoved) VALUES
 ( 1, 1,'Individual','2018-05-12',NULL),
 ( 2, 2,'Individual','2020-09-03',NULL),
 ( 1, 3,'Individual','2023-04-19',NULL),
 ( 4, 4,'Joint','2016-07-28',NULL),
 (10, 4,'Joint','2016-07-28',NULL),
 ( 3, 5,'Individual','2012-08-30',NULL),
 ( 5, 6,'Individual','2024-01-15',NULL),
 ( 5, 7,'Individual','2025-02-11',NULL),
 ( 7, 8,'Individual','2024-09-04',NULL),
 ( 9, 9,'Individual','2019-11-20',NULL),
 ( 4,10,'Individual','2014-03-08',NULL),
 ( 2,11,'Joint','2021-06-14',NULL),
 (12,11,'Joint','2021-06-14',NULL),
 ( 2,12,'Individual','2022-10-02',NULL),
 ( 8,13,'Individual','2023-03-27',NULL),
 ( 5,14,'Individual','2022-02-09',NULL),
 ( 6,15,'Individual','2011-01-19',NULL),
 ( 5,15,'Authorized User','2022-06-01',NULL),
 ( 9,16,'Individual','2019-05-23',NULL),
 (10,17,'Individual','2017-09-11',NULL),
 (11,18,'Individual','2025-04-08',NULL),
 (12,19,'Individual','2026-01-16',NULL),
 (14,20,'Individual','2015-09-01',NULL),
 (13, 1,'Authorized User','2019-03-01','2023-08-15');


-- ---------------------------------------------------------------------
-- PaymentHistory (weak entity)
-- Generated rather than typed: one row per account per month from the
-- later of the open date or 24 months ago, through last month.
-- Delinquent accounts (6 and 17) are seeded with real late codes.
-- ---------------------------------------------------------------------
INSERT INTO PaymentHistory (AccountID, ReportMonth, StatusCode, BalanceAmount, ScheduledPaymentAmount)
SELECT a.AccountID,
       m.mon::DATE,
       CASE
         WHEN a.AccountID = 6  AND m.mon >= DATE '2026-06-01' THEN '30'
         WHEN a.AccountID = 17 AND m.mon >= DATE '2026-07-01' THEN '60'
         WHEN a.AccountID = 17 AND m.mon  = DATE '2026-06-01' THEN '30'
         WHEN a.AccountID IN (7,8,19)                          THEN 'C'
         WHEN a.AccountStatus = 'Closed'
              AND m.mon > a.DateClosed                         THEN 'CLS'
         WHEN a.AccountID = 13 AND m.mon = DATE '2025-11-01'   THEN '30'
         ELSE 'OK'
       END,
       ROUND((a.CurrentBalance * (0.85 + random() * 0.30))::NUMERIC, 2),
       a.MonthlyPayment
FROM Account a
CROSS JOIN LATERAL (
    SELECT generate_series(
        GREATEST(DATE_TRUNC('month', a.DateOpened),
                 DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '24 months'),
        DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month',
        INTERVAL '1 month'
    ) AS mon
) m;


-- ---------------------------------------------------------------------
-- Inquiry (18 rows)
-- Consumer 1 has three auto inquiries inside a 14-day window: the
-- classic rate-shopping cluster that scoring models collapse into one.
-- ---------------------------------------------------------------------
INSERT INTO Inquiry
 (ConsumerID, CreditorID, InquiryDate, InquiryType, PurposeType, PermissiblePurpose) VALUES
 ( 1, 3,'2023-04-05','Hard','Auto Loan','Application for credit'),
 ( 1,12,'2023-04-09','Hard','Auto Loan','Application for credit'),
 ( 1,12,'2023-04-16','Hard','Auto Loan','Application for credit'),
 ( 1, 1,'2024-11-20','Soft','Account Review','Review of existing account'),
 ( 2, 4,'2021-05-28','Hard','Mortgage','Application for credit'),
 ( 2,11,'2021-06-02','Hard','Mortgage','Application for credit'),
 ( 3, 5,'2022-08-14','Soft','Consumer Self-Check','Consumer-initiated review'),
 ( 4,10,'2024-02-19','Hard','Credit Card','Application for credit'),
 ( 5, 6,'2024-01-10','Hard','Personal Loan','Application for credit'),
 ( 5,13,'2025-03-22','Hard','Credit Card','Application for credit'),
 ( 7,14,'2025-07-08','Soft','Prescreen','Firm offer of credit'),
 ( 8,13,'2023-03-19','Hard','Credit Card','Application for credit'),
 ( 9,15,'2024-06-11','Soft','Prescreen','Firm offer of credit'),
 (10, 1,'2022-09-30','Hard','Credit Card','Application for credit'),
 (11, 6,'2025-04-02','Hard','Personal Loan','Application for credit'),
 (12, 2,'2021-09-25','Hard','Credit Card','Application for credit'),
 (14, 5,'2015-08-20','Hard','Student Loan','Application for credit'),
 (15, 1,'2026-02-14','Soft','Account Review','Review of existing account');


-- ---------------------------------------------------------------------
-- CreditScore (30 rows; two dated scores per consumer)
-- ---------------------------------------------------------------------
INSERT INTO CreditScore (ConsumerID, ScoreModel, ScoreValue, ScoreDate, ScoreRangeMin, ScoreRangeMax) VALUES
 ( 1,'FICO Score 8',742,'2026-02-01',300,850), ( 1,'FICO Score 8',751,'2026-08-01',300,850),
 ( 2,'FICO Score 8',689,'2026-02-01',300,850), ( 2,'FICO Score 8',671,'2026-08-01',300,850),
 ( 3,'FICO Score 8',805,'2026-02-01',300,850), ( 3,'VantageScore 3.0',812,'2026-08-01',300,850),
 ( 4,'FICO Score 8',778,'2026-02-01',300,850), ( 4,'FICO Score 8',783,'2026-08-01',300,850),
 ( 5,'FICO Score 8',604,'2026-02-01',300,850), ( 5,'FICO Score 8',571,'2026-08-01',300,850),
 ( 6,'FICO Score 8',816,'2026-02-01',300,850), ( 6,'FICO Bankcard',842,'2026-08-01',250,900),
 ( 7,'FICO Score 8',655,'2026-02-01',300,850), ( 7,'FICO Score 8',662,'2026-08-01',300,850),
 ( 8,'FICO Score 8',701,'2026-02-01',300,850), ( 8,'FICO Score 8',694,'2026-08-01',300,850),
 ( 9,'FICO Score 8',735,'2026-02-01',300,850), ( 9,'FICO Auto Score',748,'2026-08-01',250,900),
 (10,'FICO Score 8',598,'2026-02-01',300,850), (10,'FICO Score 8',562,'2026-08-01',300,850),
 (11,'FICO Score 8',668,'2026-02-01',300,850), (11,'FICO Score 8',684,'2026-08-01',300,850),
 (12,'FICO Score 8',712,'2026-02-01',300,850), (12,'FICO Score 8',703,'2026-08-01',300,850),
 (13,'FICO Score 8',759,'2026-02-01',300,850), (13,'FICO Score 8',759,'2026-08-01',300,850),
 (14,'FICO Score 8',727,'2026-02-01',300,850), (14,'VantageScore 4.0',734,'2026-08-01',300,850),
 (15,'FICO Score 8',643,'2026-02-01',300,850), (15,'FICO Score 8',659,'2026-08-01',300,850);
