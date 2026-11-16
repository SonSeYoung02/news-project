from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index():
    return """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>뉴스 뷰어 백엔드</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
    }
    .card {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 48px 56px;
      text-align: center;
      max-width: 480px;
      width: 90%;
      box-shadow: 0 25px 50px rgba(0,0,0,0.4);
    }
    .dot {
      width: 14px; height: 14px;
      background: #22c55e;
      border-radius: 50%;
      display: inline-block;
      margin-right: 8px;
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(34,197,94,0.5); }
      50% { box-shadow: 0 0 0 8px rgba(34,197,94,0); }
    }
    .status {
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      color: #22c55e;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin-bottom: 24px;
    }
    h1 {
      font-size: 28px;
      font-weight: 700;
      margin-bottom: 8px;
      color: #f1f5f9;
    }
    p {
      color: #94a3b8;
      font-size: 15px;
      margin-bottom: 32px;
    }
    .links {
      display: flex;
      gap: 12px;
      justify-content: center;
      flex-wrap: wrap;
    }
    a {
      display: inline-block;
      padding: 10px 20px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 500;
      text-decoration: none;
      transition: background 0.2s;
    }
    .btn-primary {
      background: #3b82f6;
      color: #fff;
    }
    .btn-primary:hover { background: #2563eb; }
    .btn-secondary {
      background: #334155;
      color: #cbd5e1;
    }
    .btn-secondary:hover { background: #475569; }
    .info {
      margin-top: 32px;
      padding-top: 24px;
      border-top: 1px solid #334155;
      font-size: 13px;
      color: #64748b;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="status"><span class="dot"></span>백엔드 실행중</div>
    <h1>뉴스 뷰어 API</h1>
    <p>FastAPI 서버가 정상적으로 동작하고 있습니다.</p>
    <div class="links">
      <a href="/docs" class="btn-primary">Swagger 문서</a>
      <a href="/articles" class="btn-secondary">기사 목록 API</a>
    </div>
    <div class="info">http://localhost:8000</div>
  </div>
</body>
</html>
"""
