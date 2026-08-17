"""Transform docs/FAQ/faq.{zh,en}.md into content/{zh,en}/qa.yaml.

- `### N.N Question` headings become items; the body until the next heading
  becomes the (multi-line markdown) answer via a `answer: |` block scalar.
- Image refs are rewritten from docs/FAQ/images/... to public/qa/<locale>/...
- Internal anchor links `[text](#anchor)` are converted to plain text
  (the flat /qa page has no anchors, and the renderer rejects `#` hrefs).
"""
import io, re, sys

def transform(path: str, locale: str) -> list[tuple[str, str]]:
    text = io.open(path, encoding="utf-8").read()
    lines = text.splitlines()
    items: list[tuple[str, str]] = []
    question = None
    body: list[str] = []

    def flush():
        if question is not None:
            body_text = "\n".join(body).strip()
            if body_text:
                # rewrite image paths
                body_text = body_text.replace("images/", f"public/qa/{locale}/")
                # drop internal anchors: [text](#anchor) -> text
                body_text = re.sub(r"\[([^\]]+)\]\(#[^)]*\)", r"\1", body_text)
                items.append((question, body_text))
        body.clear()

    for line in lines:
        if line.startswith("### "):
            flush()
            question = line[4:].strip()
        elif line.startswith("## ") or line.startswith("---"):
            continue
        else:
            if question is not None:
                body.append(line)
    flush()
    return items

def emit(path: str, title: str, description: str, items: list[tuple[str, str]]) -> None:
    out = [f"title: {title}", f"description: {description}", "indexable: false", "items:"]
    for q, a in items:
        out.append("  - question: " + q.replace(":", "：").replace('"', "'"))
        out.append("    answer: |")
        for al in a.splitlines():
            out.append("      " + al if al.strip() else "")
    io.open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"wrote {path}: {len(items)} items")

zh_items = transform("docs/FAQ/faq.zh.md", "zh")
en_items = transform("docs/FAQ/faq.en.md", "en")
print("zh items:", len(zh_items), "en items:", len(en_items))

emit("content/zh/qa.yaml",
     "RemeMate 常见问题",
     "RemeMate 怎么用：从收词、复习到输出，每一步怎么操作、出问题怎么办，给新用户的图文版常见问题。",
     zh_items)
emit("content/en/qa.yaml",
     "RemeMate FAQ",
     "How RemeMate works, feature by feature: collect the words you meet, review them, and use them in your own writing. Illustrated answers for new users.",
     en_items)

# sanity: any forbidden chars in answers (raw HTML / leading # lines / # hrefs)
for loc, items in (("zh", zh_items), ("en", en_items)):
    for q, a in items:
        if "<" in a or ">" in a:
            print("RAW HTML?", loc, q[:40])
        for line in a.splitlines():
            if line.lstrip().startswith("#"):
                print("HEADING IN ANSWER?", loc, q[:40], line[:40])
        if re.search(r"\]\(#", a):
            print("ANCHOR LEFT?", loc, q[:40])
print("done")
