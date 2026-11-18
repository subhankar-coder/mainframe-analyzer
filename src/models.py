from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class DataItemNode:
    level: int
    name: str
    pic_clause: Optional[str] = None
    usage: str = "DISPLAY"          # DISPLAY, COMP, COMP-3
    redefines: Optional[str] = None
    byte_length: int = 0
    source_engine: str = "REGEX"    # ADATA, LARK, ANTLR4, REGEX

@dataclass
class StatementASTNode:
    stmt_type: str                  # IF, EVALUATE, PERFORM, MOVE, COMPUTE, CALL, EXEC_CICS, EXEC_SQL
    raw_text: str
    paragraph: str
    children: List["StatementASTNode"] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)

@dataclass
class CobolAST:
    program_id: str
    source_file: str
    active_parser_pipeline: str = "HYBRID (Lark + Tree-sitter + Regex)"
    adata_enriched: bool = False
    copybooks: List[str] = field(default_factory=list)
    paragraphs: List[str] = field(default_factory=list)
    performs: List[tuple] = field(default_factory=list)       # (caller_para, target_para)
    gotos: List[tuple] = field(default_factory=list)          # (caller_para, target_para)
    external_calls: List[str] = field(default_factory=list)   # CALL 'PGM' or EXEC CICS XCTL/LINK
    cics_commands: List[str] = field(default_factory=list)    # SEND MAP, RECEIVE MAP, READQ TS
    sql_tables: List[str] = field(default_factory=list)
    file_selects: List[str] = field(default_factory=list)     # Logical DD names
    data_items: List[DataItemNode] = field(default_factory=list)
    statement_trees: List[StatementASTNode] = field(default_factory=list)
    syntax_error_nodes: int = 0

@dataclass
class BMSField:
    name: str
    pos: tuple
    length: int
    attributes: List[str]           # ASKIP, UNPROT, IC, BRT, DRK (password)

@dataclass
class BMSScreen:
    mapset_name: str
    map_name: str
    fields: List[BMSField] = field(default_factory=list)

@dataclass
class JCLStep:
    step_name: str
    program_executed: str
    dd_datasets: Dict[str, str] = field(default_factory=dict) # DDNAME -> DSN

@dataclass
class JCLJob:
    job_name: str
    steps: List[JCLStep] = field(default_factory=list)

@dataclass
class RACFRule:
    resource_class: str             # e.g., TCICSTRN, DATASET, FACILITY
    profile_name: str               # Transaction ID or DSN pattern
    uacc: str                       # NONE, READ, UPDATE
    permitted_groups: Dict[str, str] = field(default_factory=dict) # Group -> Access Level

@dataclass
class OCPReadinessFinding:
    component: str
    category: str                   # UI, Security, Data, Compute, State
    severity: str                   # LOW, MEDIUM, HIGH, BLOCKER
    legacy_pattern: str
    ocp_target_solution: str
    remediation_effort_days: int
