from pathlib import Path
from typing import List
from src.config import EngineConfig, ParserMode
from src.models import CobolAST, BMSScreen, JCLJob, RACFRule
from src.adata_parser import IBMADATAParser
from src.parsers.regex_state_engine import RegexStateMachineEngine
from src.parsers.lark_engine import LarkGrammarEngine
from src.parsers.treesitter_engine import TreeSitterCSTEngine
from src.parsers.antlr4_engine import ANTLR4CompilerEngine

class UnifiedMainframeParserRouter:
    """
    Production Strategy Router with Feature Switch:
      - Mode 1 (`hybrid` - Default): Lark (EBNF AST) + Tree-sitter (Error-tolerant CST) + Regex State Machine
      - Mode 2 (`antlr4_treesitter` - Switch): ANTLR4 Compiler Visitor + Tree-sitter CST (+ Regex preprocessor)
      - Mode 3 (`regex` - Fallback): Fast Regex State Machine only
    Always enriches symbol tables with binary IBM SYSADATA (0x0042) when enabled and available.
    """
    def __init__(self, config: EngineConfig):
        self.config = config
        self.regex_engine = RegexStateMachineEngine()
        self.lark_engine = LarkGrammarEngine()
        self.treesitter_engine = TreeSitterCSTEngine()
        self.antlr4_engine = ANTLR4CompilerEngine()
        self.adata_reader = IBMADATAParser()

    def parse_cobol_file(self, cbl_file: Path, copybook_dir: Path) -> CobolAST:
        raw_text = cbl_file.read_text(encoding="utf-8")

        # Step 1: Pre-process inventory, copybooks, CICS, SQL, and Call graph via fault-tolerant state machine
        ast = self.regex_engine.parse_cobol(cbl_file, copybook_dir=copybook_dir)

        # Step 2: Route to active Grammar / CST pipeline based on switch
        if self.config.mode == ParserMode.HYBRID_LARK_TREESITTER_REGEX:
            self.lark_engine.enrich_ast_with_lark(raw_text, ast)
            self.treesitter_engine.validate_and_annotate_cst(raw_text, ast)
            ast.active_parser_pipeline = "HYBRID (Lark EBNF + Tree-sitter CST + Regex State Machine)"

        elif self.config.mode == ParserMode.ANTLR4_TREESITTER:
            # First build statement trees, then pass through ANTLR4 Visitor + Tree-sitter CST
            self.lark_engine.enrich_ast_with_lark(raw_text, ast)
            self.antlr4_engine.parse_with_antlr4_visitor(raw_text, ast)
            self.treesitter_engine.validate_and_annotate_cst(raw_text, ast)
            ast.active_parser_pipeline = "SWITCHED_PROD (ANTLR4 Visitor + Tree-sitter CST)"

        else:
            ast.active_parser_pipeline = "REGEX_STATE_MACHINE_ONLY"

        # Step 3: Enrich with Binary IBM SYSADATA if present
        if self.config.enable_adata_enrichment:
            adata_path = copybook_dir / f"{cbl_file.stem}.adata"
            if adata_path.exists():
                adata_symbols = self.adata_reader.parse_adata_file(adata_path)
                ast.data_items.extend(adata_symbols)
                ast.adata_enriched = True

        return ast

    def parse_bms_screens(self, workspace: Path) -> List[BMSScreen]:
        return [self.regex_engine.parse_bms(bms) for bms in sorted(workspace.glob("*.bms"))]

    def parse_jcl_jobs(self, workspace: Path) -> List[JCLJob]:
        return [self.regex_engine.parse_jcl(jcl) for jcl in sorted(workspace.glob("*.jcl"))]

    def parse_racf_profiles(self, workspace: Path) -> List[RACFRule]:
        rules: List[RACFRule] = []
        for racf_file in sorted(workspace.glob("*RACF*.txt")):
            rules.extend(self.regex_engine.parse_racf(racf_file))
        return rules
