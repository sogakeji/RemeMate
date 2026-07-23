"""集中导入所有 model，确保 SQLAlchemy metadata 完整。

新增 model 文件后必须在此 import，否则 Flask-Migrate autogenerate 抓不到。
"""
from app.models.user import User, UserSettings, UserQuota, TokenUsageLog
from app.models.word import WordList, Word, Definition, ReviewLog
from app.models.output import OutputEntry
from app.models.intake import IntakeSource, SourceSegment, WordCandidate
from app.models.reading import ReadingDocument, ReadingLookup
from app.models.social import SentenceUpvote
from app.models.conversation import Conversation, Message
from app.models.push import PushLog
from app.models.partner import LanguagePartner
from app.models.recap import PartnerRecap, PartnerRecapItem
from app.models.packet import (
    PartnerPacket, PartnerPacketIntake, PartnerPacketItem,
    PartnerPacketItemAdoption, PartnerPacketThank,
)
from app.models.review_story import LearningFunnelEvent, ReviewStoryRun

__all__ = [
    "User", "UserSettings", "UserQuota", "TokenUsageLog",
    "WordList", "Word", "Definition", "ReviewLog",
    "OutputEntry",
    "IntakeSource", "SourceSegment", "WordCandidate",
    "ReadingDocument", "ReadingLookup",
    "SentenceUpvote",
    "Conversation", "Message",
    "PushLog",
    "LanguagePartner",
    "PartnerRecap",
    "PartnerRecapItem",
    "PartnerPacket", "PartnerPacketItem", "PartnerPacketThank",
    "PartnerPacketIntake", "PartnerPacketItemAdoption",
    "ReviewStoryRun", "LearningFunnelEvent",
]
