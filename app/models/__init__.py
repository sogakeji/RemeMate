"""集中导入所有 model，确保 SQLAlchemy metadata 完整。

新增 model 文件后必须在此 import，否则 Flask-Migrate autogenerate 抓不到。
"""
from app.models.user import User, UserSettings, UserQuota, TokenUsageLog
from app.models.word import WordList, Word, Definition, ReviewLog
from app.models.output import OutputEntry
from app.models.intake import IntakeSource, SourceSegment, WordCandidate
from app.models.social import SentenceUpvote
from app.models.conversation import Conversation, Message
from app.models.push import PushLog

__all__ = [
    "User", "UserSettings", "UserQuota", "TokenUsageLog",
    "WordList", "Word", "Definition", "ReviewLog",
    "OutputEntry",
    "IntakeSource", "SourceSegment", "WordCandidate",
    "SentenceUpvote",
    "Conversation", "Message",
    "PushLog",
]
