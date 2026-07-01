"""造句批改：强 prompt + 结构化 JSON 输出。

针对 MemoBuddy 批改痛点（用户 2026-06-23 指出）：
- 没用目标词却自动通过 → 返回 target_word_used=false，由用户决定，不自动判过。
- 句子不完整却自动补齐 → 返回 incomplete=true 并指出，**绝不替用户补写**。
- 过度修正 → 只改真实错误，原句正确就原样返回。
（「刷新自动保存」是流程 bug，由 /write 路由的 PRG + 显式保存解决，不在本模块。）

批改只产出建议，不入库；入库由用户在 /write 显式确认。
"""
import json
from dataclasses import dataclass, field

from app.services import llm

LANG_NAMES = {"fr": "法语", "en": "英语", "ja": "日语", "de": "德语",
              "es": "西班牙语", "ru": "俄语", "zh": "中文"}

FEEDBACK_LANG_NAMES = {"zh": "中文", "fr": "法语", "en": "英语"}


@dataclass
class CorrectionResult:
    corrected: str
    translation: str
    target_word_used: bool
    incomplete: bool
    errors: list           # [{"type": "grammar|word_choice|idiom", "detail": str}]
    is_nsfw: bool
    feedback: str = ""
    # 记账用
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    degraded: bool = False  # True 表示 AI 不可用，走了兜底


_SYSTEM_TMPL = """你是严格的{lang}写作批改老师。学生在练习目标词「{word}」造句。
规则（必须严格遵守）：
1. 只修正真实存在的错误。原句若正确，corrected 必须与原句一致，不要为改而改。
2. 判断学生是否真的用到了目标词「{word}」，写入 target_word_used。没用到也不要替他改成用到。
3. 判断句子是否完整（主谓齐全、不是半句）。不完整时 incomplete=true，并在 feedback 指出，
   但【绝对不要】替学生补全或重写成完整句子。
4. 错误分级写入 errors 数组，每条 {{"type": "grammar"|"word_choice"|"idiom", "detail": "..."}}：
   grammar=语法（性数/时态/虚拟式等），word_choice=用词不当，idiom=不够地道的表达建议。
5. translation 给出该句的{feedback_lang}翻译；feedback 和 errors.detail 都用{feedback_lang}简短点评。
6. is_nsfw 标记是否含成人/不适宜公开内容。

只输出 JSON，字段：corrected, translation, target_word_used(bool),
incomplete(bool), errors(array), is_nsfw(bool), feedback。不要输出任何额外文字。"""


_DIARY_SYSTEM_TMPL = """你是严格但温和的{lang}三行日记批改老师。
学生会根据一个提示问题写三行{lang}微日记。
规则（必须严格遵守）：
1. 保持三行结构，corrected 必须也是三行，不要扩写成短文。
2. 只修正真实错误；如果原句自然正确，尽量保留原表达。
3. 判断是否完整回应了提示；严重跑题或少于三行时 incomplete=true。
4. errors 数组写主要问题，每条 {{"type": "grammar"|"word_choice"|"idiom", "detail": "..."}}。
5. translation 给出三行{feedback_lang}翻译；feedback 和 errors.detail 都用{feedback_lang}简短点评。
6. is_nsfw 标记是否含成人/不适宜公开内容。

只输出 JSON，字段：corrected, translation, target_word_used(bool),
incomplete(bool), errors(array), is_nsfw(bool), feedback。target_word_used 固定输出 true。"""


def _feedback_name(feedback_language_code):
    return FEEDBACK_LANG_NAMES.get(feedback_language_code or "zh", "中文")


def _build_messages(sentence, target_word, language_code, feedback_language_code="zh"):
    lang = LANG_NAMES.get(language_code, language_code)
    feedback_lang = _feedback_name(feedback_language_code)
    system = _SYSTEM_TMPL.format(
        lang=lang, word=target_word, feedback_lang=feedback_lang)
    user = f"目标词：{target_word}\n学生造句：{sentence}"
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def _degraded_result(sentence, feedback, *, provider="", model="",
                     prompt_tokens=0, completion_tokens=0):
    return CorrectionResult(
        corrected=sentence, translation="", target_word_used=False,
        incomplete=False, errors=[], is_nsfw=True,
        feedback=feedback,
        degraded=True,
        provider=provider, model=model,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
    )


def correct_sentence(*, sentence, target_word, language_code,
                     feedback_language_code="zh") -> CorrectionResult:
    """批改一句，返回结构化结果。AI 全挂时返回 degraded 兜底（fail-closed NSFW）。"""
    messages = _build_messages(
        sentence, target_word, language_code, feedback_language_code)
    try:
        res = llm.chat(messages, task="correction", json_mode=True)
    except llm.AllProvidersDown:
        # AI 不可用：不批改、不判过；NSFW fail-closed（隐藏公开按钮）。
        # 调用方不会允许保存降级结果，避免把未批改原句混进造句历史。
        return _degraded_result(sentence, "AI 批改暂时不可用，请稍后重试。")

    data = _parse(res.content)
    if data is None:
        # 完全解析不出 JSON：当作降级（不是"真批改"），fail-closed，给用户清晰提示，
        # 而不是伪装成"没用到目标词"误导（review 阶段四 LOW）。
        return _degraded_result(
            sentence, "批改结果解析异常，请稍后重试。",
            provider=res.provider, model=res.model,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
        )
    return _result_from_data(data, sentence, res)


def correct_diary(*, diary, prompt, language_code,
                  feedback_language_code="zh") -> CorrectionResult:
    """批改三行日记。prompt 是提示问题，diary 是用户三行回答。"""
    lang = LANG_NAMES.get(language_code, language_code)
    feedback_lang = _feedback_name(feedback_language_code)
    messages = [
        {"role": "system",
         "content": _DIARY_SYSTEM_TMPL.format(
             lang=lang, feedback_lang=feedback_lang)},
        {"role": "user", "content": f"提示问题：{prompt}\n学生三行日记：\n{diary}"},
    ]
    try:
        res = llm.chat(messages, task="correction", json_mode=True)
    except llm.AllProvidersDown:
        return _degraded_result(diary, "AI 批改暂时不可用，请稍后重试。")
    data = _parse(res.content)
    if data is None:
        return _degraded_result(
            diary, "批改结果解析异常，请稍后重试。",
            provider=res.provider, model=res.model,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
        )
    data["target_word_used"] = True
    return _result_from_data(data, diary, res)


def _result_from_data(data, fallback_sentence, res):
    return CorrectionResult(
        corrected=data.get("corrected") or fallback_sentence,
        translation=data.get("translation") or "",
        target_word_used=bool(data.get("target_word_used", False)),
        incomplete=bool(data.get("incomplete", False)),
        errors=data.get("errors") or [],
        is_nsfw=bool(data.get("is_nsfw", True)),   # 缺字段时 fail-closed
        feedback=data.get("feedback") or "",
        provider=res.provider, model=res.model,
        prompt_tokens=res.prompt_tokens, completion_tokens=res.completion_tokens,
    )


def _parse(content: str):
    """容错解析 JSON：直接失败则尝试截取首个 {...}。完全解析不出返回 None。"""
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        start = content.index("{")
        end = content.rindex("}") + 1
        return json.loads(content[start:end])
    except (ValueError, json.JSONDecodeError):
        return None    # 解析不出 → 调用方按降级 fail-closed 处理
