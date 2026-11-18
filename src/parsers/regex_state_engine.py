import re
from pathlib import Path
from typing import Dict, List
from src.models import (
    CobolAST, DataItemNode, BMSScreen, BMSField, JCLJob, JCLStep, RACFRule, StatementASTNode
)

class RegexStateMachineEngine:
    """
    Fault-tolerant Regex + State Machine parser.
    Never crashes on missing copybooks or vendor syntax extensions.
    """

    def parse_copybook(self, filepath: Path) -> List[DataItemNode]:
        items: List[DataItemNode] = []
        if not filepath.exists():
            return items

        pattern = re.compile(
            r"^\s*(\d{2})\s+([A-Z0-9-]+)"
            r"(?:\s+REDEFINES\s+([A-Z0-9-]+))?"
            r"(?:\s+PIC\s+([X9SV()0-9]+))?"
            r"(?:\s+(COMP-3|COMP|BINARY|DISPLAY))?",
            re.IGNORECASE
        )
        for line in filepath.read_text().splitlines():
            clean = line[6:72].strip() if len(line) > 6 else line.strip()
            if clean.startswith("*") or not clean:
                continue
            match = pattern.search(clean)
            if match:
                lvl, name, redef, pic, usage = match.groups()
                if name.upper() != "FILLER":
                    items.append(
                        DataItemNode(
                            level=int(lvl),
                            name=name.upper(),
                            pic_clause=pic.upper() if pic else None,
                            usage=usage.upper() if usage else "DISPLAY",
                            redefines=redef.upper() if redef else None,
                            source_engine="REGEX_STATE_MACHINE"
                        )
                    )
        return items

    def parse_cobol(self, filepath: Path, copybook_dir: Path) -> CobolAST:
        raw_lines = filepath.read_text().splitlines()
        ast = CobolAST(program_id=filepath.stem, source_file=filepath.name)

        in_proc_div = False
        current_para = "MAIN-ENTRY"

        for line in raw_lines:
            clean = line[6:72].strip() if len(line) > 6 else line.strip()
            if not clean or clean.startswith("*"):
                continue

            upper = clean.upper()

            if "PROGRAM-ID." in upper:
                parts = upper.split("PROGRAM-ID.")[1].strip().rstrip(".")
                ast.program_id = parts.split()[0]

            if "PROCEDURE DIVISION" in upper:
                in_proc_div = True
                continue

            for m in re.finditer(r"\bCOPY\s+([A-Z0-9-]+)", upper):
                cpy_name = m.group(1).rstrip(".")
                ast.copybooks.append(cpy_name)
                cpy_path = copybook_dir / f"{cpy_name}.cpy"
                ast.data_items.extend(self.parse_copybook(cpy_path))

            for m in re.finditer(r"\bSELECT\s+([A-Z0-9-]+)\s+ASSIGN\s+TO\s+([A-Z0-9-]+)", upper):
                ast.file_selects.append(m.group(2).rstrip("."))

            if not in_proc_div:
                m_data = re.search(
                    r"^(\d{2})\s+([A-Z0-9-]+)(?:\s+REDEFINES\s+([A-Z0-9-]+))?(?:\s+PIC\s+([X9SV()0-9]+))?(?:\s+(COMP-3|COMP))?",
                    upper
                )
                if m_data:
                    lvl, name, redef, pic, usage = m_data.groups()
                    ast.data_items.append(
                        DataItemNode(
                            level=int(lvl),
                            name=name,
                            pic_clause=pic,
                            usage=usage or "DISPLAY",
                            redefines=redef,
                            source_engine="REGEX_STATE_MACHINE"
                        )
                    )

            if in_proc_div:
                if re.match(r"^[0-9A-Z-]+\.$", upper) and not upper.startswith(("END-", "EXIT.", "GOBACK.", "STOP")):
                    current_para = upper.rstrip(".")
                    ast.paragraphs.append(current_para)
                    continue

                for m in re.finditer(r"\bPERFORM\s+([0-9A-Z-]+)", upper):
                    target = m.group(1).rstrip(".")
                    if target not in ("UNTIL", "VARYING", "TIMES"):
                        ast.performs.append((current_para, target))

                for m in re.finditer(r"\bGO\s+TO\s+([0-9A-Z-]+)", upper):
                    ast.gotos.append((current_para, m.group(1).rstrip(".")))

                for m in re.finditer(r"\bCALL\s+['\"]?([A-Z0-9-]+)['\"]?", upper):
                    ast.external_calls.append(m.group(1))

                if "EXEC CICS" in upper:
                    cics_cmd = re.sub(r"\s+", " ", upper)
                    ast.cics_commands.append(cics_cmd)
                    m_xctl = re.search(r"(?:XCTL|LINK)\s+PROGRAM\(['\"]([A-Z0-9-]+)['\"]\)", upper)
                    if m_xctl:
                        ast.external_calls.append(m_xctl.group(1))

                for m in re.finditer(r"\b(?:FROM|INTO|UPDATE|TABLE)\s+([A-Z0-9_]+)", upper):
                    tbl = m.group(1)
                    if tbl not in ("SQLCA", "WHERE", "SET", "VALUES") and not tbl.startswith(":"):
                        if tbl not in ast.sql_tables:
                            ast.sql_tables.append(tbl)

        return ast

    def parse_bms(self, filepath: Path) -> BMSScreen:
        content = filepath.read_text()
        mapset_name = filepath.stem
        map_name = filepath.stem

        m_set = re.search(r"^([A-Z0-9]+)\s+DFHMSD", content, re.MULTILINE)
        if m_set:
            mapset_name = m_set.group(1)

        m_map = re.search(r"^([A-Z0-9]+)\s+DFHMDI", content, re.MULTILINE)
        if m_map:
            map_name = m_map.group(1)

        screen = BMSScreen(mapset_name=mapset_name, map_name=map_name)
        for m_fld in re.finditer(
            r"^([A-Z0-9]+)\s+DFHMDF\s+POS=\((\d+),(\d+)\),\s*LENGTH=(\d+)(?:,\s*ATTRB=\(([^)]+)\))?",
            content,
            re.MULTILINE
        ):
            fname, r, c, length, attrb = m_fld.groups()
            attrs = [a.strip() for a in attrb.split(",")] if attrb else []
            screen.fields.append(BMSField(name=fname, pos=(int(r), int(c)), length=int(length), attributes=attrs))

        return screen

    def parse_jcl(self, filepath: Path) -> JCLJob:
        lines = filepath.read_text().splitlines()
        job = JCLJob(job_name=filepath.stem)
        current_step = None

        for line in lines:
            if line.startswith("//*") or not line.startswith("//"):
                continue
            m_job = re.match(r"^//([A-Z0-9]+)\s+JOB\b", line)
            if m_job:
                job.job_name = m_job.group(1)
                continue

            m_exec = re.match(r"^//([A-Z0-9]+)\s+EXEC\s+PGM=([A-Z0-9]+)", line)
            if m_exec:
                current_step = JCLStep(step_name=m_exec.group(1), program_executed=m_exec.group(2))
                job.steps.append(current_step)
                continue

            m_dd = re.match(r"^//([A-Z0-9]+)\s+DD\s+.*DSN=([A-Z0-9.]+)", line)
            if m_dd and current_step:
                current_step.dd_datasets[m_dd.group(1)] = m_dd.group(2)

            m_run = re.search(r"RUN\s+PROGRAM\(([A-Z0-9]+)\)", line)
            if m_run and current_step and current_step.program_executed == "IKJEFT01":
                current_step.program_executed = f"IKJEFT01->{m_run.group(1)}"

        return job

    def parse_racf(self, filepath: Path) -> List[RACFRule]:
        rules: Dict[str, RACFRule] = {}
        for line in filepath.read_text().splitlines():
            line = line.strip()
            m_rdef = re.match(r"RDEFINE\s+([A-Z0-9]+)\s+([A-Z0-9.*]+)\s+UACC\(([A-Z]+)\)", line)
            if m_rdef:
                cls, prof, uacc = m_rdef.groups()
                rules[prof] = RACFRule(resource_class=cls, profile_name=prof, uacc=uacc)

            m_perm = re.match(
                r"PERMIT\s+([A-Z0-9.*]+)\s+CLASS\(([A-Z0-9]+)\)\s+ID\(([A-Z0-9]+)\)\s+ACCESS\(([A-Z]+)\)",
                line
            )
            if m_perm:
                prof, cls, grp, acc = m_perm.groups()
                if prof not in rules:
                    rules[prof] = RACFRule(resource_class=cls, profile_name=prof, uacc="NONE")
                rules[prof].permitted_groups[grp] = acc

        return list(rules.values())
