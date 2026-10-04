"""Small support workflow around the existing RAG store."""

import logging
import re
import time
from pathlib import Path

from app.core.config import settings
from app.services.rag_chain import answer_text, generate_answer, retrieve
from app.services.schools import beijing_schools

logger = logging.getLogger(__name__)

CATEGORY_WORDS = {
    "VPN": ("vpn", "校外访问", "远程访问", "atrust", "webvpn"),
    "账号": ("账号", "账户", "登录", "密码", "认证", "otp", "忘记"),
    "校园网": ("校园网", "wifi", "wi-fi", "网络", "断网", "连不上", "上不了网",
              "宿舍", "网口", "网线", "交换机", "上网", "有线", "ip"),
}
SYMPTOM_WORDS = ("报错", "错误", "失败", "无法", "不能", "连不上", "打不开", "断开", "超时", "忘记", "不知道", "怎么", "如何", "哪里", "在哪", "申请", "使用", "坏了", "没反应")
SENSITIVE = re.compile(r"(?i)(密码|口令|验证码|otp|token)\s*[:：=]\s*\S+")


def redact(value: str) -> str:
    return SENSITIVE.sub(lambda match: f"{match.group(1)}：[已隐藏]", value)


def classify(question: str) -> str:
    lower = question.lower()
    for category, words in CATEGORY_WORDS.items():
        if any(word in lower for word in words):
            return category
    return "其他"


def needs_detail(question: str, category: str) -> bool:
    """Ask for more detail only when the question carries no symptom at all.

    This used to also return early for category == "其他", which rejected
    questions like "宿舍网口坏了" before any retrieval happened — even though
    the corpus does cover them.
    """
    lower = question.lower().strip()
    return len(lower) < 7 or not any(word in lower for word in SYMPTOM_WORDS)


def repair_summary(question: str, attempts: str, category: str) -> str:
    return (
        f"问题类别：{category}\n"
        f"问题描述：{redact(question.strip())}\n"
        f"已尝试操作：{redact(attempts.strip()) or '尚未提供'}"
    )


AUTHORITY_LABELS = {
    "official": "官方网页整理",
    # Student-written or team-curated material that may inform an answer, but is
    # not published by the school and must be labelled as such on the page.
    "team": "非官方资料（学生/团队整理）",
}
ANSWER_AUTHORITIES = ("official", "team")


def source_info(doc) -> dict:
    path = Path(doc.metadata.get("source", "未知来源"))
    page = doc.metadata.get("page")
    authority = doc.metadata.get("authority", "unverified")
    return {
        "title": path.name,
        "page": page + 1 if isinstance(page, int) else None,
        "authority": AUTHORITY_LABELS.get(authority, "非官方/未核验资料"),
        "url": doc.metadata.get("url", ""),
    }


def _short_name(source: str) -> str:
    return source.replace("\\", "/").rsplit("/", 1)[-1]


def answer(question: str, attempts: str = "", school: str = "") -> dict:
    started = time.monotonic()
    status = "unknown"
    kept: list = []
    category = "其他"
    try:
        question = question.strip()
        if not question:
            raise ValueError("请描述遇到的问题")
        category = classify(question)
        base = {
            "category": category,
            "sources": [],
            "repair_summary": repair_summary(question, attempts, category),
        }
        if not school:
            status = "need_school"
            return {**base, "status": status, "answer": "请先选择所在学校，以便只检索该校的官方资料。"}
        if school not in beijing_schools():
            raise ValueError("请选择北京市普通高等学校名单中的学校")
        if needs_detail(question, category):
            status = "need_detail"
            return {**base, "status": status, "answer": "请补充具体症状：使用的设备、所处位置、出现的错误提示，以及已经尝试过的操作。"}
        # A category outside CATEGORY_WORDS is no longer rejected outright: the
        # question is retrieved normally, and the corpus decides the outcome.

        safe_question = redact(question)
        try:
            matches = retrieve(safe_question, school)
        except Exception as exc:
            logger.warning(
                "retrieve failed school=%s error=%s: %s", school, type(exc).__name__, exc
            )
            status = "error"
            return {**base, "status": status, "answer": "资料检索暂时不可用。请稍后重试，或联系学校正式服务渠道。"}

        # An absolute cut-off barely separates relevant from irrelevant text under
        # the local n-gram embeddings (measured: relevant 0.099 vs irrelevant 0.077),
        # so a relative cut-off against the best hit is applied on top of it.
        floor = 0.08 if settings.embedding_provider == "local" else 0.45
        ratio = 0.65 if settings.embedding_provider == "local" else 0.75
        same_school = [
            (doc, score) for doc, score in matches
            if doc.metadata.get("school") == school
        ]
        best = max((score for _, score in same_school), default=0.0)
        documents = [
            doc for doc, score in same_school
            if score >= floor and score >= best * ratio
        ]
        kept = documents
        logger.info(
            "score school=%s best=%.4f floor=%.2f ratio=%.2f kept=%s dropped=%s",
            school, best, floor, ratio,
            [_short_name(doc.metadata.get("source", "?")) for doc in documents],
            [_short_name(doc.metadata.get("source", "?")) for doc, score in same_school
             if not (score >= floor and score >= best * ratio)],
        )

        if not documents:
            status = "unsupported"
            return {**base, "status": status, "answer": f"当前没有足够的{school}官方资料回答这个问题。建议联系该校正式服务渠道，并附上报修摘要。"}

        official_documents = [doc for doc in documents if doc.metadata.get("authority") == "official"]
        answer_documents = [doc for doc in documents if doc.metadata.get("authority") in ANSWER_AUTHORITIES]
        if not answer_documents:
            status = "unsupported"
            return {**base, "status": status, "answer": "只检索到非官方或未核验资料，无法据此给出故障处理步骤。请联系学校正式服务渠道。", "sources": [source_info(doc) for doc in documents]}

        sources = []
        for doc in answer_documents:
            item = source_info(doc)
            if item not in sources:
                sources.append(item)
        try:
            # answer_text once more: it is cheap and keeps the "empty answer"
            # guard working no matter what the generator returned.
            response = redact(answer_text(generate_answer(safe_question, answer_documents))).strip()
            if not response:
                raise ValueError("empty answer")
        except Exception as exc:
            detail = str(exc).replace(settings.gemini_api_key, "[REDACTED]") if settings.gemini_api_key else str(exc)
            logger.error("Answer generation failed (%s): %s", type(exc).__name__, detail)
            status = "error"
            return {**base, "status": status, "answer": "回答服务暂时不可用。请稍后重试，或联系学校正式服务渠道。"}
        if not official_documents:
            # Answered purely from non-official material: say so in the copyable summary.
            logger.info("answered from non-official material only school=%s", school)
            base["repair_summary"] += "\n说明：本回答依据非学校官方发布的学生/团队整理资料，请以学校官方渠道为准。"
        status = "answered"
        return {**base, "status": status, "answer": response, "sources": sources}
    finally:
        # One line per request: enough to answer "why did this question get
        # answered like that" without logging the question text itself.
        logger.info(
            "request category=%s status=%s question_chars=%d docs=%d elapsed=%.2fs",
            category, status, len(question), len(kept), time.monotonic() - started,
        )
