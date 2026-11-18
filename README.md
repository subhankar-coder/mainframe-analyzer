# Production Mainframe-to-OCP Assessment Engine (Pluggable Parser Switch)

This project implements a **Strategy/Router Architecture** that combines **Lark**, **Tree-sitter**, and **Regex State Machines** by default, while providing a single CLI or environment switch to flip the parsing pipeline to **ANTLR4 + Tree-sitter**.

## How the Parser Switch Works (`src/config.py` & `src/parsers/unified_router.py`)

1. **Default Mode (`--mode hybrid` or `PARSER_ENGINE_MODE=hybrid`)**:
   - **Regex State Machine (`src/parsers/regex_state_engine.py`)**: Extracts copybooks, JCL steps, BMS 3270 coordinates, RACF rules, and high-level `PERFORM`/`GO TO`/`CALL` edges without failing on missing vendor files.
   - **Lark EBNF Engine (`src/parsers/lark_engine.py`)**: Parses COBOL `PROCEDURE DIVISION` blocks into structured `StatementASTNode` trees (`IF`, `PERFORM`, `CALL`, `EXEC CICS`, `EXEC SQL`).
   - **Tree-sitter CST Engine (`src/parsers/treesitter_engine.py`)**: Performs error-tolerant Concrete Syntax Tree boundary checks and isolates syntax error nodes.

2. **Switched Production ANTLR4 Mode (`--mode antlr4_treesitter` or `PARSER_ENGINE_MODE=antlr4_treesitter`)**:
   - Routes AST construction through `src/parsers/antlr4_engine.py` (`ANTLR4CompilerEngine`) + `src/parsers/treesitter_engine.py` (`TreeSitterCSTEngine`).
   - If pre-generated Proleap `Cobol85Lexer.py` and `Cobol85Parser.py` are placed in `src/parsers/generated/`, it executes native ANTLR4 parse trees; otherwise it runs in resilient token-visitor compatibility mode.

3. **IBM `SYSADATA` Enrichment (`src/adata_parser.py`)**:
   - Active in all modes (`ENABLE_ADATA=true`). Reads binary `0x0042` symbol table records directly from `.adata` files.

## Usage

```bash
pip install -r requirements.txt

# Run in Default Hybrid Mode (Lark + Tree-sitter + Regex State Machine)
python main.py --mode hybrid

# Flip the Switch to ANTLR4 + Tree-sitter Mode
python main.py --mode antlr4_treesitter
```
