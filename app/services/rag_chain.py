"""Evidence-backed answer generation for campus network support."""

import logging
import re
import time

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings
from app.services.vectorstore import get_vectorstore

logger = logging.getLogger(__name__)

# Some model builds emit a bare image/file marker as its own content part.
MENTION_ONLY = re.compile(r"(?i)^(图片|图像|附件|视频|文件|image|photo|attachment|video|file)\s*[:：]?\s*$")

SOURCE_KINDS = {
    "official": "官方资料",
    "team": "非官方资料（团队整理）",
}


def _first_text(value) -> str:
    """Return the first non-empty string inside a string, list or mapping."""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _first_text(item)
            if found:
                return found
    elif isinstance(value, dict):
        for item in value.values():
            found = _first_text(item)
            if found:
                return found
    return ""


def _field(block, name: str) -> str:
    """Read one field from a dict block or an object block, without str()-ing it."""
    value = block.get(name) if isinstance(block, dict) else getattr(block, name, None)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return _first_text(value)


def answer_text(content) -> str:
    """Turn a chat-model response into user-facing text.

    `AIMessage.content` is a plain string for text-only models, but Gemini 3.x
    returns a list of content blocks such as
    ``[{'type': 'text', 'text': '...', 'extras': {'signature': '...'}}]``.
    Stringifying that list leaks the Python repr (and the thought signature) to
    the page, so extract the text parts instead.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, (list, tuple)):
        parts = []
        for block in content:
            text = _field(block, "text")
            if not text and isinstance(block, dict) and block.get("type") == "text":
                # Some providers nest the text under a different key.
                text = _first_text(block.get("content")) or _first_text(block.get("value"))
            text = text.strip()
            if not text or MENTION_ONLY.match(text):
                continue
            parts.append(text)
        return "\n\n".join(parts)

    return _first_text(content).strip() or str(content).strip()


def _short_name(source: str) -> str:
    """File name only — logs stay readable and never leak a full host path."""
    return source.replace("\\", "/").rsplit("/", 1)[-1]


def get_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        google_api_key=settings.gemini_api_key,
        temperature=0,
        transport="rest",
        # timeout: per-request limit. max_retries: TOTAL attempts (1 = no retry),
        # not "retries after the first try" — the library maps it to attempts.
        # The default of 6 could spend minutes on a failing call while the page
        # had already given up, still burning quota.
        timeout=30,
        max_retries=2,
    )


def retrieve(question: str, school: str):
    started = time.monotonic()
    matches = get_vectorstore().similarity_search_with_relevance_scores(
        question, k=8, filter={"school": school}
    )
    matches = sorted(matches, key=lambda pair: pair[1], reverse=True)
    logger.info(
        "retrieve school=%s docs=%s scores=%s elapsed=%.2fs",
        school,
        [_short_name(doc.metadata.get("source", "?")) for doc, _ in matches],
        [round(score, 4) for _, score in matches],
        time.monotonic() - started,
    )
    return matches


def generate_answer(question: str, documents: list) -> str:
    context = "\n\n".join(
        f"[{index}] 学校：{doc.metadata.get('school', '')}"
        f"　来源类型：{SOURCE_KINDS.get(doc.metadata.get('authority'), '未核验资料')}"
        f"\n{doc.page_content}"
        for index, doc in enumerate(documents, 1)
    )
    messages = [
        ("system", "你是校园网络问题服务辅助助手。只能依据提供的资料回答，用中文给出简短、可执行的步骤。"
         "资料没有支持的事实、网址、联系方式和处理流程一律不要编造。"
         "资料分为「官方资料」和「非官方资料（团队整理）」，两者冲突时以官方资料为准。"
         "「非官方资料」可以用于说明有哪些系统、入口及其用途；但具体的故障排查步骤、"
         "联系电话、办理地点，只有在官方资料支持时才能作为操作指引给出。"
         "如果给出的指引主要依据非官方资料，回答中必须说明这些内容并非学校官方发布，请通过学校官方渠道核实。"
         "资料中标注为第三方资源或非学校官方的内容，不得作为学校推荐介绍给用户。"
         "不要建议用户忽略浏览器证书警告或关闭安全防护；遇到此类旧指南，应提示通过学校官方渠道核实当前流程。"
         "不要索取或复述密码、动态口令等敏感信息；如资料包含它们，也不要输出。"
         "若资料不足，请明确说明并建议联系学校正式服务渠道。"),
        ("human", f"资料：\n{context}\n\n用户问题：{question}"),
    ]
    started = time.monotonic()
    result = get_llm().invoke(messages)
    answer = answer_text(getattr(result, "content", result))
    logger.info(
        "generate school=%s docs=%d answer_chars=%d elapsed=%.2fs",
        documents[0].metadata.get("school", "") if documents else "",
        len(documents),
        len(answer),
        time.monotonic() - started,
    )
    return answer
