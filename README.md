# 校园网络服务智能助手

面向北京市高校校园网、统一身份认证与 VPN 问题的资料检索和报修辅助系统。用户选择学校、描述症状后，系统检索该校资料，给出有来源的建议和可复制的报修摘要。**本项目不是学校官方服务，也不会创建真实工单。**

## 资料范围

教育部截至 2026 年 6 月 17 日的普通高校名单包含 92 所在京学校。[data/beijing_schools.txt](data/beijing_schools.txt) 只保留已收录网络服务资料的 38 所学校，网站学校列表与 API 均以此为准；其余 54 所暂不显示。截至 2026 年 10 月 4 日，共收录 80 份官方来源文件，逐校文件见 [data/coverage.json](data/coverage.json)。

资料包括官网网页正文及可抽取文字的原始 PDF。部分官网指南以图片说明操作，图片内容尚未 OCR；无法访问或无可抽取文字的文件未计入覆盖。北邮那份未核验的学生手册不作为官方故障处理依据。

## 工作流程

`Streamlit 页面 → FastAPI /api/v1/query → 分诊 → 按学校筛选 Chroma 检索 → Gemini 依据资料回答`。检索只使用所选学校的片段，给出处理步骤时只使用标记为 `official` 的资料。网页显示来源文件、页码和原始链接。

向量索引默认使用本地字符 n-gram 嵌入，建立索引和检索不依赖外部接口；生成回答仍需要可连接的 Gemini API。本地嵌入适合中文术语匹配，但语义泛化能力弱于在线嵌入模型。

## 本地运行

建议 Python 3.11。

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填写用于生成回答的 GEMINI_API_KEY
python ingest.py
uvicorn main:app --reload
```

另开终端运行 `streamlit run streamlit_ui/app.py`。页面默认在 `http://localhost:8501`，API 文档在 `http://localhost:8000/docs`。验证命令：`python -m unittest discover -s tests -v`。

## API

`GET /api/v1/schools` 返回学校名单。`POST /api/v1/query` 请求示例：

```json
{"school":"北京邮电大学","question":"校外无法访问校内网站，VPN 怎么使用？","attempts":"已尝试重新登录"}
```

响应包含 `status`（`need_school`、`need_detail`、`answered`、`unsupported` 或 `error`）、`category`、`answer`、带文件名/页码/原始链接的 `sources`，以及 `repair_summary`。

## 资料更新

[data/official_urls.json](data/official_urls.json) 是经人工挑选的官方来源列表，每条记录指定学校、官方域名和原始 URL。运行以下命令抓取网页正文或原始 PDF，生成失败记录和覆盖报告，再重建索引：

```bash
PYTHONPATH=. python scripts/import_official_sources.py
python ingest.py
```

导入结果见 `data/import_report.json`；`data/sources.json` 保存每个本地文件的 `authority`、`school` 和来源 URL。也可手动把获准公开展示的 PDF/TXT 放入 `data/sample_docs/` 并登记来源。只有确认为学校官方发布的资料才标记 `official`；未登记文件默认未核验。`school` 必须使用 `data/beijing_schools.txt` 中的完整校名。

新增学校时，先导入并核验该校资料，再将校名加入 `data/beijing_schools.txt`，并更新来源目录与覆盖报告。

索引重建先写入新目录，成功后替换旧索引，并保留 `chroma_db.backup-*` 备份。如设置 `EMBEDDING_PROVIDER=gemini`，须重新建索引且需要可访问 Gemini 嵌入接口。

## 公网部署

项目提供 `Dockerfile` 和 `start.sh`。将仓库根目录设为构建上下文，配置私密环境变量 `GEMINI_API_KEY`，平台将 `PORT` 注入容器；容器启动会重建索引，同时启动 API 与 Streamlit 页面。生成回答需要访问 Gemini API。部署后需用另一台设备访问公网 URL，并跑通多校演示案例。
