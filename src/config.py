import os
from enum import Enum
from dataclasses import dataclass

class ParserMode(str, Enum):
    HYBRID_LARK_TREESITTER_REGEX = "hybrid"       # Default: Lark + Tree-sitter + Regex State Machine
    ANTLR4_TREESITTER = "antlr4_treesitter"       # Production Switch: ANTLR4 + Tree-sitter CST
    REGEX_FALLBACK = "regex"                      # Zero-dependency fallback

@dataclass
class EngineConfig:
    mode: ParserMode = ParserMode.HYBRID_LARK_TREESITTER_REGEX
    enable_adata_enrichment: bool = True
    strict_grammar_mode: bool = False             # If False, gracefully degrades on missing libraries/grammars

    @classmethod
    def from_env(cls, cli_mode: str = None) -> "EngineConfig":
        raw_mode = (cli_mode or os.getenv("PARSER_ENGINE_MODE", "hybrid")).lower()
        mode_map = {
            "hybrid": ParserMode.HYBRID_LARK_TREESITTER_REGEX,
            "antlr4": ParserMode.ANTLR4_TREESITTER,
            "antlr4_treesitter": ParserMode.ANTLR4_TREESITTER,
            "regex": ParserMode.REGEX_FALLBACK,
        }
        return cls(
            mode=mode_map.get(raw_mode, ParserMode.HYBRID_LARK_TREESITTER_REGEX),
            enable_adata_enrichment=os.getenv("ENABLE_ADATA", "true").lower() == "true",
            strict_grammar_mode=os.getenv("STRICT_GRAMMAR", "false").lower() == "true",
        )
