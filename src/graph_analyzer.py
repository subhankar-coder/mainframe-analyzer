import networkx as nx
from typing import List, Dict
from src.models import (
    CobolAST, BMSScreen, JCLJob, RACFRule, OCPReadinessFinding
)

class OCPGraphAnalyzer:
    def __init__(self):
        self.system_graph = nx.DiGraph()
        self.cfg_graphs: Dict[str, nx.DiGraph] = {}
        self.findings: List[OCPReadinessFinding] = []

    def build_graphs(
        self,
        asts: List[CobolAST],
        screens: List[BMSScreen],
        jobs: List[JCLJob],
        racf_rules: List[RACFRule]
    ):
        for ast in asts:
            self.system_graph.add_node(ast.program_id, type="COBOL_PGM", cics=bool(ast.cics_commands))
            cfg = nx.DiGraph()
            for para in ast.paragraphs:
                cfg.add_node(para)
            for src, dst in ast.performs:
                cfg.add_edge(src, dst, type="PERFORM")
            for src, dst in ast.gotos:
                cfg.add_edge(src, dst, type="GOTO")
            self.cfg_graphs[ast.program_id] = cfg

            for ext in ast.external_calls:
                self.system_graph.add_node(ext, type="COBOL_PGM")
                self.system_graph.add_edge(ast.program_id, ext, relation="CALLS_OR_XCTL")

            for tbl in ast.sql_tables:
                self.system_graph.add_node(tbl, type="DB2_TABLE")
                self.system_graph.add_edge(ast.program_id, tbl, relation="SQL_ACCESS")

            for dd in ast.file_selects:
                self.system_graph.add_node(dd, type="LOGICAL_FILE")
                self.system_graph.add_edge(ast.program_id, dd, relation="FILE_IO")

            for cmd in ast.cics_commands:
                if "MAP(" in cmd:
                    for scr in screens:
                        if scr.map_name in cmd or scr.mapset_name in cmd:
                            self.system_graph.add_node(scr.map_name, type="BMS_SCREEN")
                            self.system_graph.add_edge(ast.program_id, scr.map_name, relation="RENDERS_UI")

        for job in jobs:
            self.system_graph.add_node(job.job_name, type="JCL_JOB")
            for step in job.steps:
                pgm = step.program_executed.split("->")[-1]
                self.system_graph.add_edge(job.job_name, pgm, relation=f"EXEC_{step.step_name}")
                for dd, dsn in step.dd_datasets.items():
                    self.system_graph.add_node(dsn, type="VSAM_OR_SEQ_DSN")
                    self.system_graph.add_edge(pgm, dsn, relation=f"DD_{dd}")

        for rule in racf_rules:
            self.system_graph.add_node(rule.profile_name, type="RACF_PROFILE", cls=rule.resource_class)
            for node, attrs in list(self.system_graph.nodes(data=True)):
                if attrs.get("type") in ("COBOL_PGM", "VSAM_OR_SEQ_DSN"):
                    if node in rule.profile_name or rule.profile_name.rstrip("*") in node:
                        self.system_graph.add_edge(rule.profile_name, node, relation="PROTECTS")

        self._evaluate_ocp_readiness(asts, screens, jobs, racf_rules)

    def _evaluate_ocp_readiness(
        self,
        asts: List[CobolAST],
        screens: List[BMSScreen],
        jobs: List[JCLJob],
        racf_rules: List[RACFRule]
    ):
        for ast in asts:
            if ast.cics_commands:
                has_tsq = any("READQ TS" in c or "WRITEQ TS" in c for c in ast.cics_commands)
                has_commarea = any("COMMAREA" in c for c in ast.cics_commands)
                if has_tsq or has_commarea:
                    self.findings.append(
                        OCPReadinessFinding(
                            component=ast.program_id,
                            category="State & Concurrency",
                            severity="HIGH",
                            legacy_pattern="CICS DFHCOMMAREA / Temporary Storage Queue (TSQ) session state",
                            ocp_target_solution="Externalize session state to Red Hat Data Grid (Infinispan) or Redis cluster on OCP; refactor CICS program to stateless REST microservice.",
                            remediation_effort_days=8
                        )
                    )

            if any("QUERY SECURITY" in c or "ASSIGN USERID" in c for c in ast.cics_commands):
                self.findings.append(
                    OCPReadinessFinding(
                        component=ast.program_id,
                        category="Security (RACF/SAF)",
                        severity="HIGH",
                        legacy_pattern="Inline EXEC CICS QUERY SECURITY / ASSIGN USERID SAF calls",
                        ocp_target_solution="Replace inline SAF checks with OpenShift Service Mesh (Istio) RequestAuthentication + OIDC JWT claims issued by Red Hat build of Keycloak.",
                        remediation_effort_days=5
                    )
                )

            redefs = [d for d in ast.data_items if d.redefines]
            comp3s = [d for d in ast.data_items if d.usage == "COMP-3"]
            if redefs or comp3s:
                self.findings.append(
                    OCPReadinessFinding(
                        component=ast.program_id,
                        category="Data Representation",
                        severity="MEDIUM",
                        legacy_pattern=f"{len(redefs)} REDEFINES memory overlays & {len(comp3s)} COMP-3 Packed Decimals (EBCDIC)",
                        ocp_target_solution="Convert EBCDIC Packed Decimal to UTF-8 BigDecimal/Decimal; replace REDEFINES union overlays with polymorphic DTOs or explicit byte-slice parsers.",
                        remediation_effort_days=6
                    )
                )

            if ast.gotos:
                self.findings.append(
                    OCPReadinessFinding(
                        component=ast.program_id,
                        category="Control Flow (AST)",
                        severity="MEDIUM",
                        legacy_pattern=f"Unstructured branching ({len(ast.gotos)} GO TO jumps across paragraphs)",
                        ocp_target_solution="Apply AST loop-restructuring algorithm before converting paragraphs into modular functions.",
                        remediation_effort_days=4
                    )
                )

        for scr in screens:
            self.findings.append(
                OCPReadinessFinding(
                    component=f"{scr.mapset_name}.{scr.map_name}",
                    category="UI (Online Screens)",
                    severity="HIGH",
                    legacy_pattern=f"3270 BMS Terminal Map with {len(scr.fields)} positional fields (POS/ATTRB)",
                    ocp_target_solution="Decompile BMS DFHMDF macros into JSON Schema; generate React/PatternFly Micro-Frontend served via NGINX pod on OCP with a Backend-for-Frontend (BFF) validation layer.",
                    remediation_effort_days=5
                )
            )

        for job in jobs:
            self.findings.append(
                OCPReadinessFinding(
                    component=job.job_name,
                    category="Batch & Storage",
                    severity="MEDIUM",
                    legacy_pattern=f"Multi-step JCL ({len(job.steps)} steps) with VSAM/GDG dataset dependencies",
                    ocp_target_solution="Migrate JCL orchestration to Red Hat OpenShift Pipelines (Tekton) or Argo Workflows; migrate VSAM KSDS files to Cloud-Native PostgreSQL (Crunchy Data / EDB) with indexed tables.",
                    remediation_effort_days=7
                )
            )

        if racf_rules:
            self.findings.append(
                OCPReadinessFinding(
                    component="RACF_SECURITY_DB",
                    category="Security (RACF/SAF)",
                    severity="HIGH",
                    legacy_pattern=f"{len(racf_rules)} RACF Resource Profiles (TCICSTRN, DATASET) and Group ACLs",
                    ocp_target_solution="Extract RACF groups to LDAP/Keycloak Realms; enforce API-level RBAC via OpenShift API Management (3scale) and Kubernetes NetworkPolicies.",
                    remediation_effort_days=10
                )
            )
