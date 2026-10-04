import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1/query")
SCHOOLS_URL = API_URL.rsplit("/", 1)[0] + "/schools"

st.set_page_config(page_title="校园网络服务智能助手", page_icon="🌐", layout="centered")
st.title("🌐 校园网络服务智能助手")
st.caption("校园网、账号与 VPN 问题的资料检索和报修辅助；本服务并非学校官方报修系统。")
try:
    schools = requests.get(SCHOOLS_URL, timeout=10).json()
except requests.RequestException:
    schools = []
school = st.selectbox("所在学校", ["请选择学校"] + schools)

examples = [
    "校外无法访问校内网站，VPN 应该如何使用？",
    "校园网账号无法登录，我应该先检查什么？",
    "校园网连接失败，页面提示认证错误怎么办？",
]
chosen = st.selectbox("典型问题", ["自己描述问题"] + examples)
question = st.text_area("描述遇到的问题", value="" if chosen == "自己描述问题" else chosen, height=100)
attempts = st.text_area("已经尝试过什么？（可选）", height=70)
st.caption("请勿输入密码、验证码或动态口令。")

if st.button("获取建议", type="primary", use_container_width=True):
    if school == "请选择学校":
        st.warning("请先选择所在学校。")
    elif not question.strip():
        st.warning("请先描述遇到的问题。")
    else:
        try:
            response = requests.post(API_URL, json={"school": school, "question": question, "attempts": attempts}, timeout=45)
            response.raise_for_status()
            st.session_state["result"] = response.json()
            st.session_state["result_school"] = school
        except requests.RequestException:
            st.error("服务暂时不可用，请稍后重试。")

if "result" in st.session_state and st.session_state.get("result_school") == school:
    result = st.session_state["result"]
    st.subheader(f"处理建议 · {result['category']}")
    st.markdown(result["answer"], unsafe_allow_html=False)
    if result["status"] == "need_detail":
        st.info("补充症状后再次提交，可获得更准确的建议。")
    if result["sources"]:
        st.subheader("参考资料")
        for source in result["sources"]:
            page = f" · 第 {source['page']} 页" if source["page"] else ""
            if source.get("url"):
                st.markdown(f"[{source['title']}]{chr(40)}{source['url']}{chr(41)}{page} · {source['authority']}")
            else:
                st.caption(f"{source['title']}{page} · {source['authority']}")
    st.subheader("报修摘要")
    st.code(result["repair_summary"], language=None)
    st.caption("如问题未解决，可复制摘要提交到学校正式服务渠道。")
