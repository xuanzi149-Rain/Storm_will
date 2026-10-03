"""Evidence-backed answer generation for campus network support."""

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings
from app.services.vectorstore import get_vectorstore


def get_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        google_api_key=settings.gemini_api_key,
        temperature=0,
    )


def retrieve(question: str):
    return get_vectorstore().similarity_search_with_relevance_scores(question, k=4)


def generate_answer(question: str, documents: list) -> str:
    context = "\n\n".join(
        f"[{index}] {doc.page_content}" for index, doc in enumerate(documents, 1)
    )
    messages = [
        ("system", "你是校园网络服务辅助助手。只能依据提供的资料回答，用中文给出简短、可执行的步骤。"
         "资料没有支持的事实、网址、联系方式和处理流程一律不要编造。"
         "不要索取或复述密码、动态口令等敏感信息；如资料包含它们，也不要输出。"
         "若资料不足，请明确说明并建议联系学校正式服务渠道。"),
        ("human", f"资料：\n{context}\n\n用户问题：{question}"),
    ]
    result = get_llm().invoke(messages)
    return str(result.content)
