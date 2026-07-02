"""句子广场：公开造句浏览与点夯。"""
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.extensions import db
from app.models.output import OutputEntry
from app.models.social import SentenceUpvote
from app.models.user import User


def list_public_entries(user_id: int, *, language_code: str | None = None,
                        content_type: str = "all", limit: int = 50):
    """Return public, non-NSFW square entries with word/author/upvote state."""
    vote_counts = (db.session.query(
        SentenceUpvote.entry_id.label("entry_id"),
        func.count(SentenceUpvote.id).label("vote_count"),
    ).group_by(SentenceUpvote.entry_id).subquery())
    my_votes = (db.session.query(SentenceUpvote.entry_id.label("entry_id"))
                .filter(SentenceUpvote.user_id == user_id)
                .subquery())
    author = aliased(User)
    q = (db.session.query(
            OutputEntry, author,
            func.coalesce(vote_counts.c.vote_count, 0).label("vote_count"),
            (my_votes.c.entry_id.isnot(None)).label("upvoted"),
        )
        .join(author, OutputEntry.user_id == author.id)
        .outerjoin(vote_counts, vote_counts.c.entry_id == OutputEntry.id)
        .outerjoin(my_votes, my_votes.c.entry_id == OutputEntry.id)
        .filter(OutputEntry.is_public.is_(True), OutputEntry.is_nsfw.is_(False)))
    if language_code:
        q = q.filter(OutputEntry.language_code == language_code)
    if content_type == "sentence":
        q = q.filter(OutputEntry.word_id.isnot(None))
    elif content_type == "diary":
        q = q.filter(OutputEntry.word_id.is_(None))
    return (q.order_by(func.coalesce(vote_counts.c.vote_count, 0).desc(),
                       OutputEntry.created_at.desc())
            .limit(limit).all())


def upvote_entry(user_id: int, entry_id: int) -> bool:
    """Add one upvote if allowed. Returns True only when a new vote is created."""
    entry = (OutputEntry.query
             .filter_by(id=entry_id, is_public=True, is_nsfw=False)
             .first())
    if entry is None or entry.user_id == user_id:
        return False
    db.session.add(SentenceUpvote(entry_id=entry_id, user_id=user_id))
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False
