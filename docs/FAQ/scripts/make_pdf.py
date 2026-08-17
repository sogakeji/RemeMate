"""Generate a valid one-page PDF with French text (no accents) for reading-flow tests."""
def build_pdf(text: str) -> bytes:
    content = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)

text = ("Bonjour, comment ca va ? Nous prenons le cafe ensemble, puis nous partons "
        "a la gare. Le rendez-vous est a dix heures, alors il faut se depecher.")
pdf = build_pdf(text)
path = r"D:\home\Rememate\docs\FAQ\scripts\sample-fr.pdf"
with open(path, "wb") as fh:
    fh.write(pdf)

# validate with pypdf locally before upload
from pypdf import PdfReader
r = PdfReader(path)
extracted = r.pages[0].extract_text() or ""
print("pdf bytes:", len(pdf), "| pages:", len(r.pages), "| text ok:", "bonjour" in extracted.lower())
