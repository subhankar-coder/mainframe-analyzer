      * CUSTOMER ACCOUNT RECORD COPYBOOK
       01  CUST-ACCOUNT-REC.
           05  CUST-ID                PIC X(10).
           05  CUST-NAME              PIC X(30).
           05  CUST-BALANCE           PIC S9(7)V99 COMP-3.
           05  CUST-SECURITY-RAW      PIC X(20).
           05  CUST-SECURITY-PARSED REDEFINES CUST-SECURITY-RAW.
               10  CUST-BRANCH-CD     PIC X(04).
               10  CUST-RISK-TIER     PIC X(02).
               10  CUST-AUDIT-FLAGS   PIC X(14).
