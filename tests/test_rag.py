import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.services.support import answer, classify, redact, source_info
from main import app


class SupportTests(unittest.TestCase):
    def test_classification_and_clarification(self):
        self.assertEqual(classify("Atrust VPN 无法连接"), "VPN")
        result = answer("校园网")
        self.assertEqual(result["status"], "need_detail")
        self.assertIn("具体症状", result["answer"])

    def test_supported_answer_has_source(self):
        doc = Document(page_content="校外访问校内资源可使用 VPN。", metadata={
            "source": "data/sample_docs/使用说明.pdf", "page": 2, "authority": "official"
        })
        with patch("app.services.support.retrieve", return_value=[(doc, 0.9)]), patch(
            "app.services.support.generate_answer", return_value="请按资料使用 VPN。"
        ):
            result = answer("校外无法访问校内网站，VPN 怎么使用？", "已尝试重新登录")
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["sources"], [{"title": "使用说明.pdf", "page": 3, "authority": "官方网页整理", "url": ""}])
        self.assertIn("已尝试重新登录", result["repair_summary"])

    def test_unsupported_question_does_not_generate(self):
        with patch("app.services.support.retrieve", return_value=[]), patch(
            "app.services.support.generate_answer"
        ) as generate:
            result = answer("VPN 显示未知错误怎么办？")
        self.assertEqual(result["status"], "unsupported")
        generate.assert_not_called()

    def test_unverified_document_cannot_drive_steps(self):
        doc = Document(page_content="旧版配置说明", metadata={"source": "旧手册.pdf", "authority": "unverified"})
        with patch("app.services.support.retrieve", return_value=[(doc, 0.9)]), patch(
            "app.services.support.generate_answer"
        ) as generate:
            result = answer("校园网连接失败怎么办？")
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["sources"][0]["authority"], "非官方/未核验资料")
        generate.assert_not_called()

    def test_unverified_and_secret_redaction(self):
        doc = Document(page_content="example", metadata={"source": "example.txt"})
        self.assertEqual(source_info(doc)["authority"], "非官方/未核验资料")
        self.assertNotIn("123456", redact("验证码:123456"))

    def test_api_contract(self):
        response = TestClient(app).post("/api/v1/query", json={"question": "校园网"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "need_detail")
        self.assertEqual(TestClient(app).post("/api/v1/query", json={"question": ""}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
