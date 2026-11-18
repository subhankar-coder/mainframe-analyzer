import argparse
from pathlib import Path
from src.config import EngineConfig
from src.adata_parser import IBMADATAParser
from src.parsers.unified_router import UnifiedMainframeParserRouter
from src.graph_analyzer import OCPGraphAnalyzer
from src.doc_generator import OCPArchitectureDocGenerator

def bootstrap_sample_mainframe_estate(base_dir: Path):
    base_dir.mkdir(parents=True, exist_ok=True)

    (base_dir / "CUSTCOPY.cpy").write_text("""      * CUSTOMER ACCOUNT RECORD COPYBOOK
       01  CUST-ACCOUNT-REC.
           05  CUST-ID                PIC X(10).
           05  CUST-NAME              PIC X(30).
           05  CUST-BALANCE           PIC S9(7)V99 COMP-3.
           05  CUST-SECURITY-RAW      PIC X(20).
           05  CUST-SECURITY-PARSED REDEFINES CUST-SECURITY-RAW.
               10  CUST-BRANCH-CD     PIC X(04).
               10  CUST-RISK-TIER     PIC X(02).
               10  CUST-AUDIT-FLAGS   PIC X(14).
""", encoding="utf-8")

    (base_dir / "ACCTMNU.cbl").write_text("""       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTMNU.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY CUSTCOPY.
       01  WS-COMMAREA.
           05 WS-STATE-FLAG           PIC X(01).
           05 WS-USER-ID              PIC X(08).
       PROCEDURE DIVISION.
       0000-MAIN-LOGIC.
           EXEC CICS ASSIGN USERID(WS-USER-ID) END-EXEC.
           EXEC CICS QUERY SECURITY RESTYPE('TRANSATTACH') RESID('AC01') END-EXEC.
           PERFORM 1000-RECEIVE-SCREEN.
           PERFORM 2000-FETCH-ACCOUNT-DATA.
           PERFORM 3000-SEND-SCREEN.
           EXEC CICS RETURN TRANSID('AC01') COMMAREA(WS-COMMAREA) END-EXEC.
       1000-RECEIVE-SCREEN.
           EXEC CICS RECEIVE MAP('ACCTMAP') MAPSET('ACCTSET') END-EXEC.
           EXEC CICS READQ TS QUEUE('ACCTTSQ') INTO(WS-COMMAREA) END-EXEC.
       2000-FETCH-ACCOUNT-DATA.
           EXEC SQL SELECT BAL_AMT INTO :CUST-BALANCE FROM TB_ACCOUNTS WHERE ACCT_ID = :CUST-ID END-EXEC.
           IF CUST-BALANCE < 0 THEN
               GO TO 2500-OVERDRAFT-ALERT
           END-IF.
       2500-OVERDRAFT-ALERT.
           CALL 'RISKCALC' USING CUST-ACCOUNT-REC.
       3000-SEND-SCREEN.
           EXEC CICS SEND MAP('ACCTMAP') MAPSET('ACCTSET') ERASE END-EXEC.
           EXEC CICS XCTL PROGRAM('AUDITLOG') END-EXEC.
""", encoding="utf-8")

    (base_dir / "INTBATCH.cbl").write_text("""       IDENTIFICATION DIVISION.
       PROGRAM-ID. INTBATCH.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-FILE ASSIGN TO ACCTIN.
           SELECT RPT-FILE  ASSIGN TO RPTOUT.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY CUSTCOPY.
       PROCEDURE DIVISION.
       0000-BATCH-MAIN.
           PERFORM 1000-PROCESS-RECORDS.
           GOBACK.
       1000-PROCESS-RECORDS.
           EXEC SQL UPDATE TB_ACCOUNTS SET BAL_AMT = :CUST-BALANCE END-EXEC.
           CALL 'RISKCALC' USING CUST-ACCOUNT-REC.
""", encoding="utf-8")

    (base_dir / "ACCTSET.bms").write_text("""ACCTSET  DFHMSD TYPE=&SYSPARM,MODE=INOUT,LANG=COBOL,STORAGE=AUTO
ACCTMAP  DFHMDI SIZE=(24,80),LINE=1,COLUMN=1
LBLTITLE DFHMDF POS=(1,25),LENGTH=30,ATTRB=(ASKIP,BRT),INITIAL='CORE BANKING ACCOUNT INQUIRY'
ACCTID   DFHMDF POS=(4,15),LENGTH=10,ATTRB=(UNPROT,IC,FSET)
PASSWD   DFHMDF POS=(5,15),LENGTH=8,ATTRB=(UNPROT,DRK)
CUSTNAM  DFHMDF POS=(7,15),LENGTH=30,ATTRB=(ASKIP)
BALAMT   DFHMDF POS=(8,15),LENGTH=12,ATTRB=(ASKIP,BRT)
ERRMSG   DFHMDF POS=(23,2),LENGTH=70,ATTRB=(ASKIP,BRT)
         DFHMSD TYPE=FINAL
""", encoding="utf-8")

    (base_dir / "NIGHTLY.jcl").write_text("""//NIGHTLY  JOB (ACCT01),'CORE BATCH',CLASS=A,MSGCLASS=X
//* NIGHTLY INTEREST AND ACCOUNT RECONCILIATION
//STEP01   EXEC PGM=INTBATCH
//ACCTIN   DD DSN=PROD.BANK.ACCOUNTS.VSAM,DISP=SHR
//RPTOUT   DD DSN=PROD.BANK.NIGHTLY.REPORT,DISP=(NEW,CATLG)
//STEP02   EXEC PGM=IKJEFT01
//SYSTSIN  DD *
  DSN SYSTEM(DB2P)
  RUN PROGRAM(AUDITLOG) PLAN(AUDPLAN)
/*
""", encoding="utf-8")

    (base_dir / "RACF_EXPORTS.txt").write_text("""RDEFINE TCICSTRN ACCTMNU UACC(NONE)
PERMIT ACCTMNU CLASS(TCICSTRN) ID(BANKTELL) ACCESS(READ)
PERMIT ACCTMNU CLASS(TCICSTRN) ID(BRANCHMGR) ACCESS(UPDATE)
RDEFINE DATASET PROD.BANK.ACCOUNTS.VSAM UACC(NONE)
PERMIT PROD.BANK.ACCOUNTS.VSAM CLASS(DATASET) ID(BATCHSVC) ACCESS(UPDATE)
PERMIT PROD.BANK.ACCOUNTS.VSAM CLASS(DATASET) ID(AUDITOR) ACCESS(READ)
""", encoding="utf-8")

    IBMADATAParser.create_mock_adata_binary(base_dir / "ACCTMNU.adata")


def main():
    arg_parser = argparse.ArgumentParser(description="Mainframe to OpenShift (OCP) Discovery & Roadmap Engine")
    arg_parser.add_argument(
        "--mode",
        choices=["hybrid", "antlr4_treesitter", "regex"],
        default=None,
        help="Switch parser pipeline: 'hybrid' (Lark+Tree-sitter+Regex) or 'antlr4_treesitter' (ANTLR4+Tree-sitter)"
    )
    args = arg_parser.parse_args()

    config = EngineConfig.from_env(cli_mode=args.mode)
    base_dir = Path(__file__).parent
    workspace = base_dir / "sample_mainframe_estate"
    bootstrap_sample_mainframe_estate(workspace)

    router = UnifiedMainframeParserRouter(config)
    analyzer = OCPGraphAnalyzer()
    doc_gen = OCPArchitectureDocGenerator()

    asts = [
        router.parse_cobol_file(cbl_file, copybook_dir=workspace)
        for cbl_file in sorted(workspace.glob("*.cbl"))
    ]
    screens = router.parse_bms_screens(workspace)
    jobs = router.parse_jcl_jobs(workspace)
    racf_rules = router.parse_racf_profiles(workspace)

    analyzer.build_graphs(asts, screens, jobs, racf_rules)

    output_md = doc_gen.generate_markdown_report(config, asts, screens, jobs, racf_rules, analyzer)
    output_path = base_dir / "OCP_Migration_Assessment_Report.md"
    output_path.write_text(output_md, encoding="utf-8")
    print(f"[+] Mode: {config.mode.value} | Generated report: {output_path.resolve()}")


if __name__ == "__main__":
    main()
