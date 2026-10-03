from fastapi import FastAPI
from app.api.routes import router
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="校园网络服务智能助手",
    description="面向校园网、账号和 VPN 问题的资料检索与报修辅助",
    version="0.2.0",
)

app.include_router(router, prefix="/api/v1")

@app.get("/")
def root():
    return {"message": "RAG API is running. Visit /docs for the API explorer."}