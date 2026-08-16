"""只读公开内容：Q&A / Blog 的唯一读取入口。

源是仓库内 YAML / Markdown，不扫请求路径、不读数据库。
路由只拿本模块返回的对象做 URL、404 和模板。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape
from pathlib import Path, PurePosixPath
import re
from zoneinfo import ZoneInfo

LOCALES = ("en", "zh")
DEFAULT_LOCALE = "en"
HTML_LANG = {"en": "en", "zh": "zh-Hans"}
_BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")

_REPO_CONTENT_ROOT = Path(__file__).resolve().parents[2] / "content"
_REPO_STATIC_ROOT = Path(__file__).resolve().parents[1] / "static"
_ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_cache = None
_cache_root = None
_static_root = None

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UNSAFE_HREF_RE = re.compile(r"^\s*(?:javascript|data|vbscript):", re.I)


class PublicContentError(ValueError):
    """A content file is malformed or inconsistent."""


@dataclass(frozen=True)
class ImageAsset:
    src: str
    alt: str
    caption: str | None = None


@dataclass(frozen=True)
class QaItem:
    question: str
    answer: str
    images: tuple[ImageAsset, ...] = ()


@dataclass(frozen=True)
class QaPage:
    locale: str
    title: str
    description: str
    indexable: bool
    items: tuple[QaItem, ...]


@dataclass(frozen=True)
class Post:
    locale: str
    slug: str
    title: str
    description: str
    series: str | None
    keywords: tuple[str, ...]
    date: date
    visible_from: date | None
    updated: date | None
    published: bool
    indexable: bool
    body_markdown: str
    body_html: str
    image: ImageAsset | None = None


@dataclass(frozen=True)
class PostSummary:
    locale: str
    slug: str
    title: str
    description: str
    series: str | None
    date: date
    visible_from: date | None
    indexable: bool


@dataclass(frozen=True)
class IndexableUrl:
    path: str
    locale: str | None = None
    alternate_path: str | None = None


@dataclass
class _Catalog:
    qa: dict[str, QaPage] = field(default_factory=dict)
    posts: dict[tuple[str, str], Post] = field(default_factory=dict)


def configure_content_root(root: Path | str | None) -> None:
    """Tests inject a temporary tree; None restores the repo catalog."""
    global _cache, _cache_root
    _cache = None
    _cache_root = None if root is None else Path(root)


def configure_static_root(root: Path | str | None) -> None:
    """Tests inject a temporary static tree; None restores app/static."""
    global _cache, _static_root
    _cache = None
    _static_root = None if root is None else Path(root)


def reset_content_cache() -> None:
    global _cache
    _cache = None


def public_path(kind: str, locale: str, slug: str | None = None) -> str:
    locale = _require_locale(locale)
    prefix = "" if locale == DEFAULT_LOCALE else f"/{locale}"
    if kind == "qa":
        return f"{prefix}/qa"
    if kind == "blog":
        return f"{prefix}/blog"
    if kind == "post":
        if not slug:
            raise PublicContentError("post path requires a slug")
        return f"{prefix}/blog/{slug}"
    raise PublicContentError(f"unknown public path kind: {kind}")


def _business_date() -> date:
    return datetime.now(_BUSINESS_TIMEZONE).date()


def _is_visible(post: Post) -> bool:
    return post.published and (
        post.visible_from is None or post.visible_from <= _business_date()
    )


def list_published_posts(locale: str) -> list[PostSummary]:
    locale = _require_locale(locale)
    posts = [
        post
        for (post_locale, _slug), post in _catalog().posts.items()
        if post_locale == locale and _is_visible(post)
    ]
    posts.sort(key=lambda post: (post.date, post.slug), reverse=True)
    return [
        PostSummary(
            locale=post.locale,
            slug=post.slug,
            title=post.title,
            description=post.description,
            series=post.series,
            date=post.date,
            visible_from=post.visible_from,
            indexable=post.indexable,
        )
        for post in posts
    ]


def get_published_post(locale: str, slug: str) -> Post | None:
    locale = _require_locale(locale)
    post = _catalog().posts.get((locale, slug))
    if post is None or not _is_visible(post):
        return None
    return post


def get_qa_page(locale: str) -> QaPage:
    locale = _require_locale(locale)
    try:
        return _catalog().qa[locale]
    except KeyError as exc:
        raise PublicContentError(f"missing Q&A page for locale {locale}") from exc


def iter_indexable_urls(*, registration_enabled: bool) -> list[IndexableUrl]:
    urls = [
        IndexableUrl(path="/", locale=None),
        IndexableUrl(path="/login", locale=None),
    ]
    if registration_enabled:
        urls.append(IndexableUrl(path="/register", locale=None))

    if all(get_qa_page(locale).indexable for locale in LOCALES):
        for locale in LOCALES:
            other = "zh" if locale == "en" else "en"
            urls.append(
                IndexableUrl(
                    path=public_path("qa", locale),
                    locale=locale,
                    alternate_path=public_path("qa", other),
                )
            )

    seen_slugs: set[str] = set()
    for (_locale, slug), post in _catalog().posts.items():
        if slug in seen_slugs or not _is_visible(post) or not post.indexable:
            continue
        pair = {
            locale: _catalog().posts.get((locale, slug))
            for locale in LOCALES
        }
        if not all(
            other is not None and _is_visible(other) and other.indexable
            for other in pair.values()
        ):
            continue
        seen_slugs.add(slug)
        for locale in LOCALES:
            other = "zh" if locale == "en" else "en"
            urls.append(
                IndexableUrl(
                    path=public_path("post", locale, slug),
                    locale=locale,
                    alternate_path=public_path("post", other, slug),
                )
            )
    return urls


def absolute_url(base_url: str | None, path: str) -> str:
    origin = (base_url or "https://rememate.com").rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{origin}{path}"


def render_limited_markdown(source: str, *, image_scope: str | None = None) -> str:
    if "<" in source or ">" in source:
        raise PublicContentError("raw HTML is not allowed in public markdown")

    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            text = " ".join(part.strip() for part in paragraph if part.strip())
            if text:
                blocks.append(f"<p>{_inline(text, image_scope=image_scope)}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            items = "".join(
                f"<li>{_inline(item, image_scope=image_scope)}</li>"
                for item in list_items
            )
            blocks.append(f"<ul>{items}</ul>")
            list_items.clear()

    for raw_line in source.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            flush_paragraph()
            flush_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(
                f"<h{level}>{_inline(heading.group(2).strip(), image_scope=image_scope)}</h{level}>"
            )
            continue
        if line.startswith("- "):
            flush_paragraph()
            list_items.append(line[2:].strip())
            continue
        if line.startswith("#") or line.startswith("-"):
            raise PublicContentError(f"unsupported markdown block: {line}")
        flush_list()
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    return "".join(blocks)


def _catalog() -> _Catalog:
    global _cache
    if _cache is None:
        _cache = _load_catalog(_cache_root or _REPO_CONTENT_ROOT)
    return _cache


def _load_catalog(root: Path) -> _Catalog:
    catalog = _Catalog()
    if not root.exists():
        raise PublicContentError(f"content root does not exist: {root}")

    for locale in LOCALES:
        qa_path = root / locale / "qa.yaml"
        if not qa_path.is_file():
            raise PublicContentError(f"missing {qa_path}")
        catalog.qa[locale] = _load_qa(locale, qa_path)

        blog_dir = root / locale / "blog"
        if not blog_dir.is_dir():
            continue
        for path in sorted(blog_dir.glob("*.md")):
            post = _load_post(locale, path)
            key = (locale, post.slug)
            if key in catalog.posts:
                raise PublicContentError(f"duplicate post {locale}/{post.slug}")
            catalog.posts[key] = post

    return catalog


def _load_qa(locale: str, path: Path) -> QaPage:
    data = _parse_simple_yaml(path.read_text(encoding="utf-8"))
    items_raw = data.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        raise PublicContentError(f"{path} must contain a non-empty items list")
    items = []
    for item in items_raw:
        if not isinstance(item, dict):
            raise PublicContentError(f"{path} items must be mappings")
        question = _required_text(item, "question", path)
        answer = _required_text(item, "answer", path)
        images = _parse_images(
            item.get("images", []),
            f"public/qa/{locale}",
            path,
        )
        items.append(QaItem(question=question, answer=answer, images=images))
    return QaPage(
        locale=locale,
        title=_required_text(data, "title", path),
        description=_required_text(data, "description", path),
        indexable=_optional_bool(data, "indexable", False),
        items=tuple(items),
    )


def _load_post(locale: str, path: Path) -> Post:
    raw = path.read_text(encoding="utf-8")
    meta, body = _split_front_matter(raw, path)
    slug = _required_text(meta, "slug", path)
    if not _SLUG_RE.fullmatch(slug):
        raise PublicContentError(f"{path} has invalid slug {slug!r}")
    if path.stem != slug:
        raise PublicContentError(f"{path} filename must match slug {slug}")
    published = _optional_bool(meta, "published", False)
    indexable = _optional_bool(meta, "indexable", False)
    if indexable and not published:
        raise PublicContentError(f"{path} cannot be indexable unless published")
    body_html = (
        render_limited_markdown(
            body,
            image_scope=f"public/blog/{slug}",
        )
        if body.strip()
        else ""
    )
    return Post(
        locale=locale,
        slug=slug,
        title=_required_text(meta, "title", path),
        description=_required_text(meta, "description", path),
        series=_optional_text(meta, "series"),
        keywords=_optional_keywords(meta, path),
        date=_required_date(meta, "date", path),
        visible_from=_optional_date(meta, "visible_from", path),
        updated=_optional_date(meta, "updated", path),
        published=published,
        indexable=indexable,
        body_markdown=body,
        body_html=body_html,
        image=_optional_image(
            meta,
            "image",
            "image_alt",
            f"public/blog/{slug}",
            path,
        ),
    )


def _split_front_matter(raw: str, path: Path) -> tuple[dict, str]:
    if not raw.startswith("---\n"):
        raise PublicContentError(f"{path} must start with YAML front matter")
    end = raw.find("\n---\n", 4)
    if end == -1:
        raise PublicContentError(f"{path} front matter is not closed")
    meta = _parse_simple_yaml(raw[4:end])
    body = raw[end + 5:]
    return meta, body


def _parse_simple_yaml(text: str) -> dict:
    """Parse the tiny mapping/list subset used by public content files."""
    data: dict = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            index += 1
            continue
        if raw.startswith(" ") or raw.startswith("-"):
            raise PublicContentError(f"unexpected YAML indent: {raw}")
        if ":" not in raw:
            raise PublicContentError(f"invalid YAML line: {raw}")
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "items":
            if value:
                raise PublicContentError("items must be a block list")
            items, index = _parse_item_list(lines, index + 1)
            data[key] = items
            continue
        data[key] = _parse_scalar(value)
        index += 1
    return data


def _parse_item_list(lines: list[str], start: int) -> tuple[list[dict], int]:
    items: list[dict] = []
    current: dict | None = None
    index = start
    while index < len(lines):
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            index += 1
            continue
        if not raw.startswith(" "):
            break
        stripped = raw.strip()
        if stripped.startswith("- "):
            current = {}
            items.append(current)
            rest = stripped[2:]
            if ":" not in rest:
                raise PublicContentError(f"invalid YAML list item: {raw}")
            key, value = rest.split(":", 1)
            current[key.strip()] = _parse_scalar(value.strip())
        elif current is not None and stripped == "images:":
            images, index = _parse_nested_image_list(lines, index + 1)
            current["images"] = images
            continue
        elif current is not None and stripped and ":" in stripped:
            key, value = stripped.split(":", 1)
            current[key.strip()] = _parse_scalar(value.strip())
        else:
            raise PublicContentError(f"invalid YAML list continuation: {raw}")
        index += 1
    if not items:
        raise PublicContentError("items list is empty")
    return items, index


def _parse_nested_image_list(lines: list[str], start: int) -> tuple[list[dict], int]:
    images: list[dict] = []
    current: dict | None = None
    index = start
    while index < len(lines):
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            index += 1
            continue
        if len(raw) - len(raw.lstrip()) < 4:
            break
        stripped = raw.strip()
        if stripped.startswith("- "):
            current = {}
            images.append(current)
            rest = stripped[2:]
            if ":" not in rest:
                raise PublicContentError(f"invalid image list item: {raw}")
            key, value = rest.split(":", 1)
            current[key.strip()] = _parse_scalar(value.strip())
        elif current is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            current[key.strip()] = _parse_scalar(value.strip())
        else:
            raise PublicContentError(f"invalid image list continuation: {raw}")
        index += 1
    return images, index


def _parse_scalar(value: str):
    if value == "":
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _required_text(data: dict, key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PublicContentError(f"{path} missing {key}")
    return value.strip()


def _optional_bool(data: dict, key: str, default: bool) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    raise PublicContentError(f"{key} must be a boolean")


def _optional_text(data: dict, key: str) -> str | None:
    value = data.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not value.strip():
        raise PublicContentError(f"{key} must be text")
    return value.strip()


def _optional_keywords(data: dict, path: Path) -> tuple[str, ...]:
    value = data.get("keywords")
    if value in (None, ""):
        return ()
    if not isinstance(value, str):
        raise PublicContentError(f"{path} keywords must be comma-separated text")
    keywords = tuple(item.strip() for item in value.split(",") if item.strip())
    if not keywords:
        raise PublicContentError(f"{path} keywords must not be empty")
    return keywords


def _required_date(data: dict, key: str, path: Path) -> date:
    value = _required_text(data, key, path)
    if not _DATE_RE.fullmatch(value):
        raise PublicContentError(f"{path} has invalid {key}")
    return date.fromisoformat(value)


def _optional_date(data: dict, key: str, path: Path) -> date | None:
    value = data.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise PublicContentError(f"{path} has invalid {key}")
    return date.fromisoformat(value)


def _parse_images(value, scope: str, path: Path) -> tuple[ImageAsset, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise PublicContentError(f"{path} images must be a list")
    assets = []
    for item in value:
        if not isinstance(item, dict):
            raise PublicContentError(f"{path} image entries must be mappings")
        src = _required_text(item, "src", path)
        alt = _required_text(item, "alt", path)
        caption = item.get("caption")
        if caption not in (None, "") and not isinstance(caption, str):
            raise PublicContentError(f"{path} image caption must be text")
        assets.append(
            ImageAsset(
                src=_validate_asset_path(src, scope, path),
                alt=alt,
                caption=caption.strip() if isinstance(caption, str) else None,
            )
        )
    return tuple(assets)


def _optional_image(
    data: dict,
    image_key: str,
    alt_key: str,
    scope: str,
    path: Path,
) -> ImageAsset | None:
    src = data.get(image_key)
    alt = data.get(alt_key)
    if src in (None, "") and alt in (None, ""):
        return None
    if not isinstance(src, str) or not src.strip():
        raise PublicContentError(f"{path} missing {image_key}")
    if not isinstance(alt, str) or not alt.strip():
        raise PublicContentError(f"{path} missing {alt_key}")
    return ImageAsset(
        src=_validate_asset_path(src.strip(), scope, path),
        alt=alt.strip(),
    )


def _validate_asset_path(src: str, scope: str, path: Path) -> str:
    if "\\" in src or src.startswith(("/", "http:", "https:", "data:", "javascript:")):
        raise PublicContentError(f"{path} has unsafe image path")
    candidate = PurePosixPath(src)
    required_scope = PurePosixPath(scope)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PublicContentError(f"{path} has unsafe image path")
    if candidate.parent != required_scope and not str(candidate).startswith(f"{scope}/"):
        raise PublicContentError(f"{path} image must stay under {scope}")
    if candidate.suffix.lower() not in _ALLOWED_IMAGE_SUFFIXES:
        raise PublicContentError(f"{path} has unsupported image type")
    root = (_static_root or _REPO_STATIC_ROOT).resolve()
    asset = (root / Path(*candidate.parts)).resolve()
    try:
        asset.relative_to(root)
    except ValueError as exc:
        raise PublicContentError(f"{path} has unsafe image path") from exc
    if not asset.is_file():
        raise PublicContentError(f"{path} image does not exist: {src}")
    return str(candidate)


def _static_image_url(src: str) -> str:
    return "/static/" + "/".join(PurePosixPath(src).parts)


def _require_locale(locale: str) -> str:
    if locale not in LOCALES:
        raise PublicContentError(f"unsupported locale: {locale}")
    return locale


def _inline(text: str, *, image_scope: str | None = None) -> str:
    placeholders: list[str] = []

    def hold(html: str) -> str:
        placeholders.append(html)
        return f"\x00{len(placeholders) - 1}\x00"

    def code(match: re.Match[str]) -> str:
        return hold(f"<code>{escape(match.group(1))}</code>")

    def strong(match: re.Match[str]) -> str:
        return hold(f"<strong>{escape(match.group(1))}</strong>")

    def image(match: re.Match[str]) -> str:
        if image_scope is None:
            raise PublicContentError("markdown image requires an image scope")
        alt, src = match.group(1), match.group(2).strip()
        if not alt.strip():
            raise PublicContentError("markdown image requires alt text")
        asset = _validate_asset_path(src, image_scope, Path("markdown"))
        return hold(
            f'<img src="{escape(_static_image_url(asset), quote=True)}" '
            f'alt="{escape(alt.strip(), quote=True)}" loading="lazy">'
        )

    def link(match: re.Match[str]) -> str:
        label, href = match.group(1), match.group(2).strip()
        if _UNSAFE_HREF_RE.match(href) or href.startswith("#"):
            raise PublicContentError(f"unsafe markdown href: {href}")
        if not (
            href.startswith("/")
            or href.startswith("https://")
            or href.startswith("http://")
            or href.startswith("mailto:")
        ):
            raise PublicContentError(f"unsafe markdown href: {href}")
        return hold(
            f'<a href="{escape(href, quote=True)}">{escape(label)}</a>'
        )

    marked = re.sub(r"`([^`]+)`", code, text)
    marked = re.sub(r"\*\*([^*]+)\*\*", strong, marked)
    marked = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", image, marked)
    marked = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, marked)
    parts = re.split(r"(\x00\d+\x00)", marked)
    rendered: list[str] = []
    for part in parts:
        held = re.fullmatch(r"\x00(\d+)\x00", part)
        if held:
            rendered.append(placeholders[int(held.group(1))])
        else:
            rendered.append(escape(part))
    return "".join(rendered)
