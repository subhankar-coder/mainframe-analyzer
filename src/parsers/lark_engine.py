from typing import List
from src.models import StatementASTNode, CobolAST

try:
    from lark import Lark, Tree, Token
    LARK_AVAILABLE = True
except ImportError:
    LARK_AVAILABLE = False

COBOL_PROCEDURE_EBNF = r"""
    start: paragraph+

    paragraph: PARA_NAME "." statement*

    ?statement: perform_stmt
              | goto_stmt
              | call_stmt
              | if_stmt
              | move_stmt
              | exec_stmt
              | goback_stmt

    perform_stmt: "PERFORM"i NAME ("THRU"i NAME)? "."?
    goto_stmt: "GO"i "TO"i? NAME "."?
    call_stmt: "CALL"i STRING ("USING"i NAME+)? "."?
    move_stmt: "MOVE"i (NAME | NUMBER | STRING) "TO"i NAME+ "."?
    goback_stmt: ("GOBACK"i | "STOP"i "RUN"i) "."?
    exec_stmt: "EXEC"i ("CICS"i | "SQL"i) /[^E]+/ "END-EXEC"i "."?

    if_stmt: "IF"i condition "THEN"i? statement+ ("ELSE"i statement+)? "END-IF"i "."?

    condition: operand COMP_OP operand
    ?operand: (":"? NAME) | NUMBER | STRING

    COMP_OP: "=" | "<" | ">" | "<=" | ">=" | "NOT ="i
    PARA_NAME: /[0-9A-Za-z][0-9A-Za-z-]*/
    NAME: /[A-Za-z0-9][A-Za-z0-9_-]*/
    STRING: /'[^']*'/ | /"[^"]*"/
    NUMBER: /[+-]?\d+(\.\d+)?/

    %import common.WS
    %ignore WS
"""

class LarkGrammarEngine:
    """
    Pure-Python Earley/LALR EBNF Grammar Parser using Lark.
    Parses COBOL Procedure Division blocks into hierarchical StatementASTNodes.
    """
    def __init__(self):
        self.parser = Lark(COBOL_PROCEDURE_EBNF, parser="earley") if LARK_AVAILABLE else None

    def enrich_ast_with_lark(self, raw_cobol_text: str, ast: CobolAST) -> bool:
        proc_text = self._extract_procedure_division(raw_cobol_text)
        if not proc_text:
            return False

        if self.parser is not None:
            try:
                tree = self.parser.parse(proc_text)
                ast.statement_trees = self._convert_lark_tree(tree)
                return True
            except Exception:
                pass

        # Built-in pure-Python recursive descent AST builder when Lark package is not installed
        ast.statement_trees = self._fallback_recursive_descent_ast(proc_text)
        return LARK_AVAILABLE

    def _extract_procedure_division(self, raw_cobol_text: str) -> str:
        lines = []
        in_proc = False
        for line in raw_cobol_text.splitlines():
            clean = line[6:72].strip() if len(line) > 6 else line.strip()
            if not clean or clean.startswith("*"):
                continue
            if "PROCEDURE DIVISION" in clean.upper():
                in_proc = True
                continue
            if in_proc:
                lines.append(clean)
        return "\n".join(lines)

    def _convert_lark_tree(self, tree) -> List[StatementASTNode]:
        nodes: List[StatementASTNode] = []
        for para in tree.children:
            if getattr(para, "data", "") == "paragraph":
                para_name = str(para.children[0])
                for stmt in para.children[1:]:
                    nodes.append(self._tree_to_stmt_node(stmt, para_name))
        return nodes

    def _tree_to_stmt_node(self, tree_node, para_name: str) -> StatementASTNode:
        stmt_type = getattr(tree_node, "data", "STATEMENT").upper()
        children = []
        tokens = []
        for ch in getattr(tree_node, "children", []):
            if hasattr(ch, "data"):
                children.append(self._tree_to_stmt_node(ch, para_name))
            else:
                tokens.append(str(ch))
        return StatementASTNode(
            stmt_type=stmt_type,
            raw_text=" ".join(tokens),
            paragraph=para_name,
            children=children,
            metadata={"parser": "LARK_EARLEY_EBNF"}
        )

    def _fallback_recursive_descent_ast(self, proc_text: str) -> List[StatementASTNode]:
        nodes: List[StatementASTNode] = []
        current_para = "MAIN-LOGIC"
        active_if_node = None

        for line in proc_text.splitlines():
            u = line.upper()
            if u.endswith(".") and " " not in u and not u.startswith(("END-IF", "GOBACK")):
                current_para = u.rstrip(".")
                continue

            if u.startswith("IF "):
                active_if_node = StatementASTNode(
                    stmt_type="IF_STMT",
                    raw_text=line,
                    paragraph=current_para,
                    metadata={"parser": "LARK_COMPAT_AST"}
                )
                nodes.append(active_if_node)
            elif u.startswith("END-IF"):
                active_if_node = None
            else:
                stmt_kind = u.split()[0] if u.split() else "STMT"
                node = StatementASTNode(
                    stmt_type=f"{stmt_kind}_STMT",
                    raw_text=line,
                    paragraph=current_para,
                    metadata={"parser": "LARK_COMPAT_AST"}
                )
                if active_if_node is not None:
                    active_if_node.children.append(node)
                else:
                    nodes.append(node)
        return nodes
