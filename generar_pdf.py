from pathlib import Path
import re
import textwrap

lines = []
for raw in Path("respuestas_hdt5.md").read_text(encoding="utf-8").splitlines():
    line = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", raw.strip()).replace("**", "").replace("`", "").replace("•", "-")
    lines.extend(textwrap.wrap(line, width=96, break_long_words=False) if line else [""])
pages = [lines[i:i + 48] for i in range(0, len(lines), 48)] or [[]]
objects = []
def add(value):
    objects.append(value if isinstance(value, bytes) else value.encode("latin-1", "replace")); return len(objects)
font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
page_data = []
for chunk in pages:
    commands = ["BT", "/F1 10 Tf", "50 742 Td", "14 TL"]
    for line in chunk:
        if line.startswith("# "): commands.append("/F1 14 Tf")
        elif line.startswith("## "): commands.append("/F1 12 Tf")
        safe = line.lstrip("# ").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({safe}) Tj T*"); commands.append("/F1 10 Tf")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", "replace")
    content = add(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    page_data.append((content, add(f"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>")))
pages_id = add("<< /Type /Pages /Kids [] /Count 0 >>")
for _, page_id in page_data: objects[page_id - 1] = objects[page_id - 1].replace(b"/Parent 0 0 R", f"/Parent {pages_id} 0 R".encode())
objects[pages_id - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for _, p in page_data)}] /Count {len(page_data)} >>".encode()
catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
pdf = bytearray(b"%PDF-1.4\n"); offsets = [0]
for i, data in enumerate(objects, 1): offsets.append(len(pdf)); pdf.extend(f"{i} 0 obj\n".encode()); pdf.extend(data); pdf.extend(b"\nendobj\n")
xref = len(pdf); pdf.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
for offset in offsets[1:]: pdf.extend(f"{offset:010d} 00000 n \n".encode())
pdf.extend(f"trailer\n<< /Size {len(objects)+1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
Path("respuestas_hdt5.pdf").write_bytes(pdf)
print("respuestas_hdt5.pdf generado")
