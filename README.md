# 校园网络服务智能助手

面向北京邮电大学校园网、统一身份认证与 VPN 问题的参赛演示系统。用户描述症状后，系统会追问缺失信息、检索资料、给出有来源的建议，并生成可复制的报修摘要。**本项目不是学校官方服务，也不会创建真实工单。**

## 功能与架构

`Streamlit 页面 → FastAPI /api/v1/query → 分诊 → Chroma 检索 → Gemini 依据资料回答`。无足够官方资料时，系统提示联系正式服务渠道；非官方资料不会单独驱动故障处理建议。问答资料包括三份根据北邮信息化技术中心公开网页整理的简要摘录，以及一份明确标为未核验的学生手册。资料来源、页码和原始链接会在页面展示。来源列表见 [设计文档](docs/competition-design.md)。

## 本地运行

建议 Python 3.11。

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填写 GEMINI_API_KEY
python ingest.py
uvicorn main:app --reload
```

另开终端运行：

```bash
streamlit run streamlit_ui/app.py
```

页面默认在 `http://localhost:8501`，API 文档在 `http://localhost:8000/docs`。验证：`python -m unittest discover -s tests -v`。

## API

`POST /api/v1/query`，请求示例：

```json
{"question":"校外无法访问校内网站，VPN 怎么使用？","attempts":"已尝试重新登录"}
```

响应包含 `status`（`need_detail`、`answered`、`unsupported` 或 `error`）、`category`、`answer`、带文件名/页码/原始链接的 `sources`，以及 `repair_summary`。

## 资料更新

把获准公开展示的 PDF/TXT 放入 `data/sample_docs/`，在 `data/sources.json` 为文件记录 `authority`、`school` 和 `url`。只有确认为学校官方发布的资料才标记 `official`；未登记文件默认未核验。运行 `python ingest.py` 重建索引。现有学生手册自述非官方，文件在当前工作区中未纳入 Git，发布前需确认是否有展示权并决定是否包含。

## 公网部署

项目提供 `Dockerfile` 和 `start.sh`，供支持 Docker 的托管平台使用。部署时将仓库根目录设为构建上下文，配置私密环境变量 `GEMINI_API_KEY`，平台将 `PORT` 注入容器；容器启动会重建知识库索引，同时启动本地 API 与对外 Streamlit 页面。首次启动需要能访问 Gemini API。托管平台还需提供稳定公网 URL。完成部署后，务必用另一台设备访问 URL 并跑通三类演示案例。仓库目前没有绑定任何托管账号，因此这里不提供未经验证的公网地址。
