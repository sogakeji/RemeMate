# Lute-style PDF Reading MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PDF-first reading workflow where closed-beta users upload a text-based PDF, read it in RemeMate, select words, see local-dictionary results, and add candidates whose final word example is the original PDF sentence.

**Architecture:** Add a focused `reading` module with parser, dictionary, context extraction, service, and blueprint boundaries. Keep the existing intake/candidate/commit pipeline as the only path into `words` and `definitions`, preserving hidden language word lists, dedupe, SRS initialization, RLS, and user isolation.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate/Alembic, PostgreSQL RLS, Jinja2/HTMX, pytest. Parser default is `pypdf` because PyMuPDF's official PyPI metadata is AGPL/commercial dual licensed and is not accepted for the closed-beta/future commercial server default. Dictionary data is local/offline and external to git.

---

## Hard Stop Before Code

Task 1 is a hard gate. Do not start code tasks until all of these are true:

- Parser choice approved: PyMuPDF rejected as default; `pypdf` selected.
- `zh/en/fr` dictionary datasets selected with license, install path, update method, and distribution posture.
- `ja` tokenizer/dictionary stack selected with license, install path, update method, and distribution posture.
- If any language cannot pass license/data review, reduce MVP language set in the spec and commit that spec change before implementation.

## File Structure

### New files

- `docs/THIRD_PARTY.md`: dependency and dictionary license decisions.
- `app/models/reading.py`: `ReadingDocument`, `ReadingLookup`.
- `app/services/reading/__init__.py`: package marker.
- `app/services/reading/parsers.py`: selected PDF parser adapter.
- `app/services/reading/dictionary.py`: dictionary interface and fixture/local adapter.
- `app/services/reading/context.py`: sentence extraction and offset validation.
- `app/services/reading/service.py`: document CRUD, lookup, position, lookup-to-candidate.
- `app/blueprints/reading/__init__.py`: reading routes.
- `app/templates/reading/index.html`, `new.html`, `show.html`, `_lookup_card.html`.
- `migrations/versions/<revision>_add_reading_documents.py`.
- Reading tests under `tests/unit/` and `tests/integration/`.
- Small fixtures under `tests/fixtures/dictionaries/` and `tests/fixtures/pdfs/`.

### Modified files

- `requirements.txt`: add only approved parser/dictionary packages.
- `config.py`: add `DICTIONARY_DATA_DIR`, reading limits.
- `app/models/__init__.py`: import reading models.
- `app/models/intake.py`: add `WordCandidate.source_example`; optionally `IntakeSource.reading_document_id` if chosen.
- `app/services/intake.py`: commit prefers `source_example` over editable `example`; support `reading_pdf` source type.
- `tests/conftest.py`: clean `reading_lookups` before `word_candidates`; clean `reading_documents` before `intake_sources`/users.
- `app/__init__.py`: register reading blueprint.
- `app/templates/base.html`: add “阅读” nav link.
- `cli/commands.py`: doctor dictionary checks.
- `tests/integration/test_cli.py`: doctor tests.
- `docs/HANDOFF.md`, `docs/deploy-closed-beta.md`: handoff/deploy notes.

---

## Task 1: Third-party license and data-source gate

**Files:**
- Create: `docs/THIRD_PARTY.md`
- Modify: `docs/superpowers/specs/2026-07-03-lute-reading-mvp-design.md` if parser/language scope changes

- [ ] **Step 1: Create the third-party decision table**

Create `docs/THIRD_PARTY.md` with parser, tokenizer, and dictionary sections. Include columns: component/dataset, language, use, license, source URL, install path, update method, distribution posture, decision.

- [ ] **Step 2: Fill parser decision**

Confirm PyMuPDF license from official docs. If unacceptable for closed beta/future commercial server use, select `pypdf` or `pdfminer.six` and update the spec to remove PyMuPDF as default.

- [ ] **Step 3: Fill all dictionary decisions**

Select and document exact data sources for `zh/en/fr/ja`. Do not leave `TODO` for a target MVP language. If one language cannot be sourced safely, reduce the MVP language set in spec before code.

- [ ] **Step 4: Commit and stop if unresolved**

```bash
git add docs/THIRD_PARTY.md docs/superpowers/specs/2026-07-03-lute-reading-mvp-design.md docs/superpowers/plans/2026-07-03-lute-reading-mvp.md
git commit -m "docs: record reading MVP third-party license decisions"
```

Expected: commit exists and all target languages have explicit decisions. If not, stop.

---

## Task 2: Reading models, migration, cleanup, RLS

**Files:**
- Create: `app/models/reading.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/intake.py`
- Modify: `tests/conftest.py`
- Create: `migrations/versions/<revision>_add_reading_documents.py`
- Test: `tests/integration/test_reading_documents.py`, `tests/integration/test_reading_rls.py`

- [ ] **Step 1: Write failing DB/model tests**

Create tests for:

- unique `(user_id, content_hash)`
- rejecting unsupported `language_code='de'`
- rejecting negative `page_count`
- reading cleanup works across tests

Run:

```bash
.venv/bin/python -m pytest tests/integration/test_reading_documents.py -q
```

Expected: FAIL because models do not exist.

- [ ] **Step 2: Add models**

Create `ReadingDocument` and `ReadingLookup`. Add `ReadingDocument.intake_source_id` nullable FK to `intake_sources.id` with `ondelete='SET NULL'`. This gives durable one-document-to-one-reading-source reuse.

Add `WordCandidate.source_example = db.Column(db.Text, nullable=True)`.

- [ ] **Step 3: Update imports and cleanup order**

Update `app/models/__init__.py`.

Update `tests/conftest.py` `_TABLES` order:

```python
_TABLES = [
    "push_log", "token_usage_log", "user_quota", "user_settings",
    "sentence_upvotes", "messages", "conversations",
    "reading_lookups", "word_candidates", "source_segments",
    "reading_documents", "intake_sources",
    "output_entries", "review_logs", "definitions", "words", "word_lists",
    "users",
]
```

- [ ] **Step 4: Create migration with exact RLS policy style**

Use project fail-closed expression:

```python
UID = "NULLIF(current_setting('app.current_user_id', true), '')::int"
```

Migration requirements:

- create `reading_documents`, `reading_lookups`
- add `word_candidates.source_example`
- add `reading_documents.intake_source_id`
- constraints for supported languages, nonnegative page/context, context order
- indexes named explicitly
- `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`
- `ALTER TABLE ... FORCE ROW LEVEL SECURITY`
- drop/recreate policies:
  - SELECT/DELETE: `USING (user_id = UID)`
  - INSERT: `WITH CHECK (user_id = UID)`
  - UPDATE: `USING (user_id = UID) WITH CHECK (user_id = UID)`

Use `DROP POLICY IF EXISTS` before every create, matching `1ca04f710530_rls.py`.

- [ ] **Step 5: Add RLS tests**

Create `tests/integration/test_reading_rls.py` based on existing `test_rls.py` patterns:

- app-role query without GUC returns no rows or fails closed
- user B cannot select/update/delete user A reading document
- insert/update with mismatched `user_id` rejected by `WITH CHECK`

- [ ] **Step 6: Upgrade dev/test DB and run tests**

```bash
.venv/bin/python -m flask db upgrade
.venv/bin/python -m pytest tests/integration/test_reading_documents.py tests/integration/test_reading_rls.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/models/reading.py app/models/__init__.py app/models/intake.py tests/conftest.py migrations/versions/*_add_reading_documents.py tests/integration/test_reading_documents.py tests/integration/test_reading_rls.py
git commit -m "feat: add reading document persistence"
```

---

## Task 3: Context sentence extraction

**Files:**
- Create: `app/services/reading/__init__.py`
- Create: `app/services/reading/context.py`
- Test: `tests/unit/test_reading_context.py`

- [ ] **Step 1: Write failing tests**

Cover English, French, Chinese, Japanese punctuation, offset mismatch, and long sentence truncation.

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_reading_context.py -q
```

Expected: FAIL because module missing.

- [ ] **Step 2: Implement `extract_context_sentence`**

Implement a small dataclass result with `sentence`, `start`, `end`, `offset_matched`. Use language boundary sets:

- `zh/ja`: `。！？\n`
- `en/fr`: `.!?\n`

If selected text does not match expected term, search within a 200-char window. Always keep target term in the returned truncated sentence.

- [ ] **Step 3: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/unit/test_reading_context.py -q
git add app/services/reading/__init__.py app/services/reading/context.py tests/unit/test_reading_context.py
git commit -m "feat: add reading context extraction"
```

---

## Task 4: Dictionary service with approved fixture adapter

**Files:**
- Create: `app/services/reading/dictionary.py`
- Create: `tests/fixtures/dictionaries/{zh,en,ja,fr}/entries.json`
- Test: `tests/unit/test_reading_dictionary.py`

- [ ] **Step 1: Write failing tests**

Cover:

- lookup hit for each `zh/en/ja/fr`
- unsupported language `de` raises
- missing dictionary returns `found=False`
- English/French lowercase normalization
- Japanese adapter path delegates to approved tokenizer/dictionary or fixture adapter in tests

- [ ] **Step 2: Implement dictionary interface**

Implement `DictionaryResult`, `Dictionary.lookup`, and fixture/local JSON adapter. Do not claim production dictionary coverage unless `DICTIONARY_DATA_DIR` has real approved data.

- [ ] **Step 3: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/unit/test_reading_dictionary.py -q
git add app/services/reading/dictionary.py tests/unit/test_reading_dictionary.py tests/fixtures/dictionaries
git commit -m "feat: add reading dictionary adapter"
```

---

## Task 5: PDF parser adapter

**Files:**
- Modify: `requirements.txt`
- Create: `app/services/reading/parsers.py`
- Test: `tests/unit/test_reading_parser.py`

- [ ] **Step 1: Add only approved parser package**

Use `pypdf`, the parser selected in `docs/THIRD_PARTY.md`. Do not add PyMuPDF unless a commercial license is approved and recorded later.

- [ ] **Step 2: Write failing tests**

Tests must create tiny PDFs inside the test using the approved parser if possible. If committing fixtures, document fixture provenance in `docs/THIRD_PARTY.md`. Cover:

- text PDF extracts expected text
- empty/no-text PDF raises `EmptyPdfText`
- size/page/char limits raise clear exceptions

- [ ] **Step 3: Implement parser adapter**

Expose:

```python
parse_pdf_bytes(file_bytes, filename, *, max_bytes, max_pages, max_chars) -> ParsedDocument
```

Return `title`, `text`, `page_count`. Raise typed exceptions for too large, too many pages, empty text, parse error.

- [ ] **Step 4: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/unit/test_reading_parser.py -q
git add requirements.txt app/services/reading/parsers.py tests/unit/test_reading_parser.py tests/fixtures/pdfs docs/THIRD_PARTY.md
git commit -m "feat: add text PDF parser adapter"
```

---

## Task 6: Reading service core

**Files:**
- Create: `app/services/reading/service.py`
- Modify: `app/services/intake.py`
- Test: `tests/integration/test_reading_lookup_candidate.py`

- [ ] **Step 1: Audit source type assumptions**

Run:

```bash
rg "csv|text_extract|quick_add|source_type" app tests migrations
```

Update comments, branches, or tests that assume only three source types. Keep `reading_pdf` out of CSV/text processing branches.

- [ ] **Step 2: Write failing service tests**

Cover:

- create document and list document
- update last position validates schema/ranges
- invalid positions rejected: negative char offset, offset > content length, scroll ratio <0/>1, nonnumeric payload
- lookup creates `ReadingLookup` with context sentence
- add lookup creates candidate with `example` and `source_example`
- candidate edit cannot override final `Definition.example`
- two lookups from one document reuse one `IntakeSource` through `ReadingDocument.intake_source_id`
- existing word in same language prevents duplicate candidate and returns existing-word state

- [ ] **Step 3: Implement service**

Functions:

- `create_document`
- `get_document`
- `list_documents`
- `delete_document`
- `update_last_position`
- `lookup_term`
- `add_lookup_to_candidate`

`add_lookup_to_candidate` must use or create `ReadingDocument.intake_source_id` and create candidates through a shared helper. When creating the `reading_pdf` source, it must call the existing implicit language-list path:

```python
wl = words_svc.get_or_create_language_list(user_id, document.language_code)
source = IntakeSource(
    user_id=user_id,
    source_type="reading_pdf",
    language_code=document.language_code,
    word_list_id=wl.id,
    original_name=document.source_filename or document.title,
    status="done",
    total_segments=0,
)
```

Add a test that a reading candidate commits into the correct implicit language word list for `document.language_code`.

Prefer extending `intake._write_candidates` to accept `source_example`, `context_start`, `context_end`, `note`; if keeping direct creation, document why and test all fields.

- [ ] **Step 4: Modify intake commit**

In `commit_intake_source`, write:

```python
example = c.source_example or c.example
```

`Definition.example` must use `example`.

- [ ] **Step 5: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/integration/test_reading_lookup_candidate.py -q
git add app/services/reading/service.py app/services/intake.py tests/integration/test_reading_lookup_candidate.py
git commit -m "feat: bridge reading lookups to candidates"
```

---

## Task 7: Reading shelf and read-only document routes

**Files:**
- Create: `app/blueprints/reading/__init__.py`
- Create: `app/templates/reading/index.html`
- Create: `app/templates/reading/new.html`
- Create: `app/templates/reading/show.html`
- Modify: `app/__init__.py`
- Modify: `app/templates/base.html`
- Test: `tests/integration/test_reading_routes.py`

- [ ] **Step 1: Write failing route tests**

Cover login required, shelf lists only current user's docs, reader shows content, user B gets 404 for user A document.

- [ ] **Step 2: Implement blueprint shell and templates**

Routes use canonical URLs without trailing slash:

- `GET /reading`
- `GET /reading/new`
- `GET /reading/<doc_id>`
- `POST /reading/<doc_id>/delete`

Register blueprint and nav link.

- [ ] **Step 3: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/integration/test_reading_routes.py -q
git add app/blueprints/reading app/templates/reading app/__init__.py app/templates/base.html tests/integration/test_reading_routes.py
git commit -m "feat: add reading shelf and reader pages"
```

---

## Task 8: PDF upload route

**Files:**
- Modify: `app/blueprints/reading/__init__.py`
- Modify: `app/services/reading/service.py`
- Test: `tests/integration/test_reading_routes.py`

- [ ] **Step 1: Add failing upload tests**

Cover supported upload, unsupported language, non-PDF extension, parser empty-text error, duplicate upload redirects/reuses existing document.

- [ ] **Step 2: Implement `POST /reading` upload**

Validate language in `zh/en/ja/fr`, file extension `.pdf`, parse with selected parser, hash `content_text`, create/reuse document.

- [ ] **Step 3: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/integration/test_reading_routes.py -q
git add app/blueprints/reading/__init__.py app/services/reading/service.py tests/integration/test_reading_routes.py
git commit -m "feat: upload PDFs into reading shelf"
```

---

## Task 9: Lookup card API and add-candidate action

**Files:**
- Modify: `app/blueprints/reading/__init__.py`
- Create: `app/templates/reading/_lookup_card.html`
- Test: `tests/integration/test_reading_routes.py`

- [ ] **Step 1: Add failing tests**

Cover `POST /reading/<doc_id>/lookup`, CSRF, card includes dictionary meaning and context sentence, existing-word state, `POST /reading/lookups/<id>/add-candidate`, cross-user lookup blocked.

- [ ] **Step 2: Implement lookup and add routes**

Return `_lookup_card.html`. Add-candidate route redirects to existing candidate page or returns card state with “已加入候选”.

- [ ] **Step 3: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/integration/test_reading_routes.py -q
git add app/blueprints/reading/__init__.py app/templates/reading/_lookup_card.html tests/integration/test_reading_routes.py
git commit -m "feat: add reading lookup card actions"
```

---

## Task 10: Reader selection JS and position updates

**Files:**
- Modify: `app/templates/reading/show.html`
- Modify: `app/blueprints/reading/__init__.py`
- Test: `tests/integration/test_reading_routes.py`

- [ ] **Step 1: Add route tests for position endpoint**

Cover valid update, invalid negative offset, invalid scroll ratio, cross-user blocked.

- [ ] **Step 2: Implement `POST /reading/<doc_id>/position`**

Call `update_last_position` and return 204/JSON OK.

- [ ] **Step 3: Implement minimal reader JS**

Do not tokenize whole document. On text selection, compute offsets relative to the exact rendered text container, POST lookup with CSRF, inject returned card.

- [ ] **Step 4: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/integration/test_reading_routes.py tests/integration/test_reading_lookup_candidate.py -q
git add app/templates/reading/show.html app/blueprints/reading/__init__.py tests/integration/test_reading_routes.py
git commit -m "feat: wire reader selection and progress"
```

---

## Task 11: Doctor/config/deploy docs

**Files:**
- Modify: `config.py`
- Modify: `cli/commands.py`
- Modify: `tests/integration/test_cli.py`
- Modify: `.env.example` if present
- Modify: `docs/deploy-closed-beta.md`

- [ ] **Step 1: Add failing doctor tests**

Extend `tests/integration/test_cli.py`:

- missing `DICTIONARY_DATA_DIR` gives WARN
- `doctor --strict` fails on missing dictionary dir
- configured fixture dir reports OK or target language status

- [ ] **Step 2: Add config and doctor checks**

Add `DICTIONARY_DATA_DIR`, `READING_MAX_PDF_BYTES`, `READING_MAX_PDF_PAGES`, `READING_MAX_PDF_CHARS`. Doctor should WARN by default and fail under `--strict` through existing strict warning behavior.

- [ ] **Step 3: Update deploy docs**

Mention dictionary directory and reading limits in closed-beta deployment notes.

- [ ] **Step 4: Run tests and commit**

```bash
.venv/bin/python -m pytest tests/integration/test_cli.py -q
git add config.py cli/commands.py tests/integration/test_cli.py .env.example docs/deploy-closed-beta.md
git commit -m "feat: add reading dictionary doctor checks"
```

---

## Task 12: Full validation and handoff

**Files:**
- Modify: `docs/HANDOFF.md`

- [ ] **Step 1: Run focused tests**

```bash
.venv/bin/python -m pytest \
  tests/unit/test_reading_context.py \
  tests/unit/test_reading_dictionary.py \
  tests/unit/test_reading_parser.py \
  tests/integration/test_reading_documents.py \
  tests/integration/test_reading_rls.py \
  tests/integration/test_reading_lookup_candidate.py \
  tests/integration/test_reading_routes.py \
  tests/integration/test_cli.py -q
```

Expected: all PASS.

- [ ] **Step 2: Run full suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: all PASS. Record count.

- [ ] **Step 3: Run DB/doctor checks**

```bash
.venv/bin/python -m flask db current
.venv/bin/python -m flask doctor
```

Expected: current is head; doctor reports dictionary state.

- [ ] **Step 4: Optional local server reload**

Only if local gunicorn belongs to this repo:

```bash
pgrep -af "gunicorn -c gunicorn.conf.py wsgi:app"
kill -HUP <master_pid>
curl -fsS http://127.0.0.1:8891/healthz
```

Expected: `{"status":"ok"}`.

- [ ] **Step 5: Update handoff**

Append branch, routes, parser decision, dictionary data dir, migration head, test count, and limitations.

- [ ] **Step 6: Commit**

```bash
git add docs/HANDOFF.md
git commit -m "docs: hand off PDF reading MVP"
```

---

## Execution Notes

- Keep one commit per task.
- Use app-level `user_id` filtering plus RLS for all new tables.
- Every write route needs CSRF.
- Reading candidates must preserve PDF source sentence through commit.
- Do not implement around unresolved licenses.
