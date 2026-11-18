import struct
from pathlib import Path
from typing import List
from src.models import DataItemNode

class IBMADATAParser:
    """
    Parses binary IBM Enterprise COBOL SYSADATA files.
    Standard ADATA Record Header format (Big-Endian on z/OS):
      - Bytes 0-1: Language Code (uint8) + EditionLevel (uint8)
      - Bytes 2-3: Record Type (uint16) -> 0x0042 = Symbol, 0x0030 = Parse Tree
      - Bytes 4-5: Record Length (uint16)
    """
    RECORD_TYPE_SYMBOL = 0x0042
    RECORD_TYPE_PARSE_TREE = 0x0030

    def parse_adata_file(self, filepath: Path) -> List[DataItemNode]:
        extracted_symbols: List[DataItemNode] = []
        if not filepath.exists():
            return extracted_symbols

        data = filepath.read_bytes()
        offset = 0
        total_len = len(data)

        while offset + 6 <= total_len:
            lang_code, edition, rec_type, rec_len = struct.unpack(">BBHH", data[offset:offset+6])
            if rec_len == 0 or offset + rec_len > total_len:
                break

            payload = data[offset+6 : offset+rec_len]
            if rec_type == self.RECORD_TYPE_SYMBOL and len(payload) >= 14:
                level, usage_code, flags, byte_len, n_len, p_len, r_len = struct.unpack(
                    ">HBBIHHH", payload[:14]
                )
                cursor = 14
                name = payload[cursor:cursor+n_len].decode("ascii", errors="ignore")
                cursor += n_len
                pic = payload[cursor:cursor+p_len].decode("ascii", errors="ignore") if p_len else None
                cursor += p_len
                redef = payload[cursor:cursor+r_len].decode("ascii", errors="ignore") if r_len else None

                usage_map = {0: "DISPLAY", 1: "COMP-3", 2: "COMP"}
                extracted_symbols.append(
                    DataItemNode(
                        level=level,
                        name=name,
                        pic_clause=pic,
                        usage=usage_map.get(usage_code, "DISPLAY"),
                        redefines=redef,
                        byte_length=byte_len,
                        source_engine="IBM_SYSADATA_0x0042"
                    )
                )
            offset += rec_len

        return extracted_symbols

    @staticmethod
    def create_mock_adata_binary(filepath: Path):
        records = bytearray()
        sample_symbols = [
            (5, 0, 0, 10, "WS-ACCT-ID", "X(10)", ""),
            (5, 1, 0, 5, "WS-BAL-AMT", "S9(7)V99", ""),
            (5, 0, 1, 20, "WS-RAW-BUF", "X(20)", ""),
            (5, 0, 1, 20, "WS-PARSED-BUF", "X(20)", "WS-RAW-BUF"),
        ]
        for level, usage, flags, b_len, name, pic, redef in sample_symbols:
            n_b, p_b, r_b = name.encode("ascii"), pic.encode("ascii"), redef.encode("ascii")
            payload = struct.pack(
                ">HBBIHHH", level, usage, flags, b_len, len(n_b), len(p_b), len(r_b)
            ) + n_b + p_b + r_b
            rec_len = 6 + len(payload)
            header = struct.pack(">BBHH", 16, 1, IBMADATAParser.RECORD_TYPE_SYMBOL, rec_len)
            records.extend(header + payload)

        filepath.write_bytes(bytes(records))
