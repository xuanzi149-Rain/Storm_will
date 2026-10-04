import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.services.support import answer, classify, redact, source_info
from app.services.embedder import LocalNgramEmbeddings
from main import app


class SupportTests(unittest.TestCase):
    def test_classification_and_clarification(self):
        self.assertEqual(classify("Atrust VPN 无法连接"), "VPN")
        result = answer("校园网", school="北京邮电大学")
        self.assertEqual(result["status"], "need_detail")
        self.assertIn("具体症状", result["answer"])

    def test_supported_answer_has_source(self):
        doc = Document(page_content="校外访问校内资源可使用 VPN。", metadata={
            "source": "data/sample_docs/使用说明.pdf", "page": 2, "authority": "official", "school": "北京邮电大学"
        })
        with patch("app.services.support.retrieve", return_value=[(doc, 0.9)]), patch(
            "app.services.support.generate_answer", return_value="请按资料使用 VPN。"
        ):
            result = answer("校外无法访问校内网站，VPN 怎么使用？", "已尝试重新登录", "北京邮电大学")
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["sources"], [{"title": "使用说明.pdf", "page": 3, "authority": "官方网页整理", "url": ""}])
        self.assertIn("已尝试重新登录", result["repair_summary"])

    def test_unsupported_question_does_not_generate(self):
        with patch("app.services.support.retrieve", return_value=[]), patch(
            "app.services.support.generate_answer"
        ) as generate:
            result = answer("VPN 显示未知错误怎么办？", school="北京邮电大学")
        self.assertEqual(result["status"], "unsupported")
        generate.assert_not_called()

    def test_unverified_document_cannot_drive_steps(self):
        doc = Document(page_content="旧版配置说明", metadata={"source": "旧手册.pdf", "authority": "unverified", "school": "北京邮电大学"})
        with patch("app.services.support.retrieve", return_value=[(doc, 0.9)]), patch(
            "app.services.support.generate_answer"
        ) as generate:
            result = answer("校园网连接失败怎么办？", school="北京邮电大学")
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["sources"][0]["authority"], "非官方/未核验资料")
        generate.assert_not_called()

    def test_unverified_and_secret_redaction(self):
        doc = Document(page_content="example", metadata={"source": "example.txt"})
        self.assertEqual(source_info(doc)["authority"], "非官方/未核验资料")
        self.assertNotIn("123456", redact("验证码:123456"))

    def test_api_contract(self):
        response = TestClient(app).post("/api/v1/query", json={"school": "北京邮电大学", "question": "校园网"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "need_detail")
        self.assertEqual(TestClient(app).post("/api/v1/query", json={"question": ""}).status_code, 422)

    def test_school_scope(self):
        self.assertEqual(answer("VPN 无法连接怎么办？")["status"], "need_school")
        schools = TestClient(app).get("/api/v1/schools").json()
        self.assertEqual(len(schools), 38)
        self.assertIn("北京邮电大学", schools)
        self.assertNotIn("北京工业大学", schools)
        other = Document(page_content="北邮 VPN 说明", metadata={
            "source": "北邮VPN.txt", "authority": "official", "school": "北京邮电大学"
        })
        with patch("app.services.support.retrieve", return_value=[(other, 0.9)]) as retrieve:
            result = answer("VPN 无法连接怎么办？", school="北京大学")
        retrieve.assert_called_once_with("VPN 无法连接怎么办？", "北京大学")
        self.assertEqual(result["status"], "unsupported")

    def test_local_embeddings_retrieve_shared_chinese_terms(self):
        embeddings = LocalNgramEmbeddings()
        query = embeddings.embed_query("校园网认证失败")
        related = embeddings.embed_query("校园网认证失败如何排查")
        unrelated = embeddings.embed_query("图书馆借阅记录")
        similarity = lambda a, b: sum(x * y for x, y in zip(a, b))
        self.assertEqual(len(query), embeddings.dimensions)
        self.assertEqual(query, embeddings.embed_query("校园网认证失败"))
        self.assertGreater(similarity(query, related), similarity(query, unrelated))


if __name__ == "__main__":
    unittest.main()
