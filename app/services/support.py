"""Small support workflow around the existing RAG store."""

import re
from pathlib import Path

from app.core.config import settings
from app.services.rag_chain import generate_answer, retrieve
from app.services.schools import beijing_schools

CATEGORY_WORDS = {
    "VPN": ("vpn", "校外访问", "远程访问", "atrust"),
    "账号": ("账号", "账户", "登录", "密码", "认证", "otp"),
    "校园网": ("校园网", "wifi", "wi-fi", "网络", "断网", "连不上", "上不了网"),
}
SYMPTOM_WORDS = ("报错", "错误", "失败", "无法", "不能", "连不上", "打不开", "断开", "超时", "忘记", "不知道", "怎么", "如何", "哪里", "在哪", "申请", "使用")
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
    lower = question.lower().strip()
    return category != "其他" and (
        len(lower) < 7 or not any(word in lower for word in SYMPTOM_WORDS)
    )


def repair_summary(question: str, attempts: str, category: str) -> str:
    return (
        f"问题类别：{category}\n"
        f"问题描述：{redact(question.strip())}\n"
        f"已尝试操作：{redact(attempts.strip()) or '尚未提供'}\n"
        "当前状态：问题仍未解决，请协助核查。"
    )


def source_info(doc) -> dict:
    path = Path(doc.metadata.get("source", "未知来源"))
    page = doc.metadata.get("page")
    authority = doc.metadata.get("authority", "unverified")
    return {
        "title": path.name,
        "page": page + 1 if isinstance(page, int) else None,
        "authority": "官方网页整理" if authority == "official" else "非官方/未核验资料",
        "url": doc.metadata.get("url", ""),
    }


def answer(question: str, attempts: str = "", school: str = "") -> dict:
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
        return {**base, "status": "need_school", "answer": "请先选择所在学校，以便只检索该校的官方资料。"}
    if school not in beijing_schools():
        raise ValueError("请选择北京市普通高等学校名单中的学校")
    if needs_detail(question, category):
        return {**base, "status": "need_detail", "answer": "请补充具体症状：使用的设备、所处位置、出现的错误提示，以及已经尝试过的操作。"}
    if category == "其他":
        return {**base, "status": "unsupported", "answer": "目前仅支持校园网、账号和 VPN 相关问题。请补充相关场景，或联系学校正式服务渠道。"}

    safe_question = redact(question)
    try:
        matches = retrieve(safe_question, school)
    except Exception:
        return {**base, "status": "error", "answer": "资料检索暂时不可用。请稍后重试，或联系学校正式服务渠道。"}
    threshold = 0.08 if settings.embedding_provider == "local" else 0.45
    documents = [
        doc for doc, score in matches
        if score >= threshold and doc.metadata.get("school") == school
    ]
    if not documents:
        return {**base, "status": "unsupported", "answer": f"当前没有足够的{school}官方资料回答这个问题。建议联系该校正式服务渠道，并附上报修摘要。"}

    official_documents = [doc for doc in documents if doc.metadata.get("authority") == "official"]
    if not official_documents:
        return {**base, "status": "unsupported", "answer": "只检索到非官方或未核验资料，无法据此给出故障处理步骤。请联系学校正式服务渠道。", "sources": [source_info(doc) for doc in documents]}

    sources = []
    for doc in official_documents:
        item = source_info(doc)
        if item not in sources:
            sources.append(item)
    try:
        response = redact(generate_answer(safe_question, official_documents))
    except Exception:
        return {**base, "status": "error", "answer": "回答服务暂时不可用。请稍后重试，或联系学校正式服务渠道。"}
    return {**base, "status": "answered", "answer": response, "sources": sources}
