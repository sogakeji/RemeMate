# Third-party license decisions

This document records the parser, tokenizer, and dictionary decisions for the Lute-style PDF reading MVP.

Scope: text-based PDF reader, local/offline dictionary lookup, target languages `zh`, `en`, `ja`, `fr`.

Policy:

- Do not commit production dictionary data to git.
- Keep production dictionary data under `DICTIONARY_DATA_DIR`, defaulting to `/srv/rememate-data/dictionaries`.
- Keep package dependencies and small test fixtures separate from production dictionary data.
- Treat AGPL/commercial dual licensing as unacceptable for the closed beta and future commercial server unless the project buys and records a commercial license.
- Preserve attribution/license files alongside any externally stored dictionary data.

## Parser decisions

| component/dataset | language | use | license | source URL | install path | update method | distribution posture | decision |
|---|---|---|---|---|---|---|---|---|
| PyMuPDF | all | PDF text extraction candidate | Dual licensed: GNU AGPL 3.0 or Artifex commercial license. Official PyPI metadata says: "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License". | `https://pypi.org/project/PyMuPDF/`, `https://pymupdf.readthedocs.io/en/latest/about.html` | Not installed for this MVP unless a commercial license is acquired and recorded. | Re-evaluate only if commercial license terms are approved. | Do not ship in the closed-beta server/image under AGPL. Do not add as default dependency. | Rejected as default parser for this MVP. |
| pypdf | all | Text-based PDF extraction default parser | BSD-style license. Official source `LICENSE` permits redistribution and use in source and binary forms with conditions. | `https://pypi.org/project/pypdf/`, `https://github.com/py-pdf/pypdf`, `https://raw.githubusercontent.com/py-pdf/pypdf/main/LICENSE` | Python package dependency in the app environment when parser implementation starts. | Pin in `requirements.txt`; update through normal dependency review. | Package may be included in server/image. No production data files. | Approved default parser. |
| pdfminer.six | all | Fallback parser candidate if `pypdf` extraction is insufficient | MIT License. Official source `LICENSE` permits use, copy, modify, merge, publish, distribute, sublicense, and sell copies. | `https://pypi.org/project/pdfminer.six/`, `https://github.com/pdfminer/pdfminer.six`, `https://raw.githubusercontent.com/pdfminer/pdfminer.six/master/LICENSE` | Not installed initially; optional later parser adapter. | Add only through a later dependency review if needed. | Package may be included in server/image if selected later. | Approved fallback, not MVP default. |

## Tokenizer decisions

| component/dataset | language | use | license | source URL | install path | update method | distribution posture | decision |
|---|---|---|---|---|---|---|---|---|
| fugashi | `ja` | Japanese tokenization and normalization wrapper | MIT License in official source repository. | `https://pypi.org/project/fugashi/`, `https://github.com/polm/fugashi`, `https://raw.githubusercontent.com/polm/fugashi/master/LICENSE` | Python package dependency in the app environment when Japanese lookup implementation starts. | Pin in `requirements.txt`; update through normal dependency review. | Package may be included in server/image. | Approved for Japanese tokenizer. |
| unidic-lite | `ja` | Lightweight UniDic dictionary data for fugashi tokenizer | MIT License in official source repository and PyPI classifier. | `https://pypi.org/project/unidic-lite/`, `https://github.com/polm/unidic-lite`, `https://raw.githubusercontent.com/polm/unidic-lite/master/LICENSE` | Python package dependency in the app environment when Japanese lookup implementation starts. | Pin in `requirements.txt`; update through normal dependency review. | Package may be included in server/image. | Approved for Japanese tokenizer data. |

## Dictionary decisions

| component/dataset | language | use | license | source URL | install path | update method | distribution posture | decision |
|---|---|---|---|---|---|---|---|---|
| Kaikki.org Wiktionary raw data, Chinese extraction | `zh` | Local Chinese dictionary source for exact lookup and short phrase lookup | Wiktionary-derived content. Wiktextract official license notes Wiktionary content is under CC-BY-SA or GFDL at user's choice; use CC BY-SA attribution/share-alike posture. | `https://kaikki.org/dictionary/rawdata.html`, `https://kaikki.org/dictionary/Chinese/index.html`, `https://raw.githubusercontent.com/tatuylonen/wiktextract/master/LICENSE`, `https://en.wiktionary.org/wiki/Wiktionary:Copyrights` | `/srv/rememate-data/dictionaries/zh/kaikki-wiktionary/` | Download/process from Kaikki raw data or language JSONL outside git; record dump date and source URL in that directory. | Do not commit to git. Do not bake into the default server image. Mount/provision externally with attribution/license metadata. | Approved for MVP `zh` dictionary data. |
| Kaikki.org Wiktionary raw data, English extraction | `en` | Local English dictionary source for exact lookup + lowercase lookup | Wiktionary-derived content. Wiktextract official license notes Wiktionary content is under CC-BY-SA or GFDL at user's choice; use CC BY-SA attribution/share-alike posture. | `https://kaikki.org/dictionary/rawdata.html`, `https://kaikki.org/dictionary/English/index.html`, `https://raw.githubusercontent.com/tatuylonen/wiktextract/master/LICENSE`, `https://en.wiktionary.org/wiki/Wiktionary:Copyrights` | `/srv/rememate-data/dictionaries/en/kaikki-wiktionary/` | Download/process from Kaikki raw data or language JSONL outside git; record dump date and source URL in that directory. | Do not commit to git. Do not bake into the default server image. Mount/provision externally with attribution/license metadata. | Approved for MVP `en` dictionary data. |
| Kaikki.org Wiktionary raw data, French extraction | `fr` | Local French dictionary source for exact lookup + lowercase lookup | Wiktionary-derived content. Wiktextract official license notes Wiktionary content is under CC-BY-SA or GFDL at user's choice; use CC BY-SA attribution/share-alike posture. | `https://kaikki.org/dictionary/rawdata.html`, `https://kaikki.org/dictionary/French/index.html`, `https://raw.githubusercontent.com/tatuylonen/wiktextract/master/LICENSE`, `https://en.wiktionary.org/wiki/Wiktionary:Copyrights` | `/srv/rememate-data/dictionaries/fr/kaikki-wiktionary/` | Download/process from Kaikki raw data or language JSONL outside git; record dump date and source URL in that directory. | Do not commit to git. Do not bake into the default server image. Mount/provision externally with attribution/license metadata. | Approved for MVP `fr` dictionary data. |
| jamdict Python package | `ja` | JMdict lookup library | MIT License in official source repository and PyPI metadata. | `https://pypi.org/project/jamdict/`, `https://github.com/neocl/jamdict`, `https://raw.githubusercontent.com/neocl/jamdict/master/LICENSE` | Python package dependency in the app environment when Japanese lookup implementation starts. | Pin in `requirements.txt`; update through normal dependency review. | Package may be included in server/image. Dictionary data remains external unless separately reviewed. | Approved for Japanese dictionary adapter. |
| JMdict / EDICT dictionary files | `ja` | Local Japanese dictionary data queried through jamdict or a compatible adapter | Creative Commons Attribution-ShareAlike 4.0. Official EDRDG license says dictionary files are made available under CC BY-SA 4.0. | `https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project`, `https://www.edrdg.org/edrdg/licence.html`, `https://creativecommons.org/licenses/by-sa/4.0/` | `/srv/rememate-data/dictionaries/ja/jmdict/` | Download from official EDRDG/JMdict distribution outside git; record download date, source URL, and license file in that directory. | Do not commit to git. Do not bake into the default server image. Mount/provision externally with attribution/license metadata and share-alike posture. | Approved for MVP `ja` dictionary data. |

## Implementation notes

- MVP parser implementation must use `pypdf` by default and must not add `PyMuPDF` unless a commercial license is approved later.
- Dictionary implementation may use a normalized local JSON/index format generated from the approved external data sources, stored under each language install path.
- Test fixtures may be small handcrafted entries under `tests/fixtures/dictionaries/`; fixture provenance must be recorded if copied from any third-party dictionary.
- `doctor --strict` should fail when `DICTIONARY_DATA_DIR` is missing or when any MVP language directory is missing.
