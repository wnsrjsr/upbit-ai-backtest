from flask import Flask, jsonify, request, render_template_string
import sqlite3, json, os
from datetime import datetime

app = Flask(__name__)
DB = os.getenv("DB_PATH", "paper_trading.db")
CONTROL = os.getenv("CONTROL_PATH", "control.json")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")

PAGE = r"""
<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#101827">
<title>코인 모의투자 대시보드</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#101827;color:#eef2ff;font:15px -apple-system,BlinkMacSystemFont,sans-serif}
main{max-width:760px;margin:auto;padding:18px}.muted{color:#9aa8bd}.card{background:#1b2940;border:1px solid #2c3d58;border-radius:16px;padding:16px;margin:12px 0}
h1{font-size:22px;margin:8px 0 4px}.big{font-size:28px;font-weight:750}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
button{border:0;border-radius:12px;padding:13px 16px;font-size:15px;font-weight:700;margin:4px 4px 4px 0}
.start{background:#22c55e;color:#06210f}.stop{background:#f59e0b;color:#281600}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:9px 5px;border-bottom:1px solid #34445e}
.good{color:#4ade80}.bad{color:#f87171}.pill{display:inline-block;border-radius:20px;padding:5px 9px;background:#33445f}
</style></head><body><main>
<h1>업비트 코인 모의투자</h1><div class="muted">클라우드 자동매매 상태 · 20초마다 갱신</div>
<div class="card"><div class="muted">총 평가자산</div><div class="big" id="equity">불러오는 중</div>
<div id="pnl" class="muted"></div><div style="margin-top:12px"><span id="status" class="pill">상태 확인 중</span></div>
<button class="stop" onclick="control(true)">일시정지</button><button class="start" onclick="control(false)">재개</button>
<div class="muted">일시정지는 신규 진입과 자동 청산을 모두 멈춥니다. 보유 포지션의 손절 감시도 중단되므로 장시간 정지하지 마세요.</div></div>
<div class="grid"><div class="card"><div class="muted">가상 현금</div><div id="cash" class="big">-</div></div>
<div class="card"><div class="muted">보유 종목</div><div id="count" class="big">-</div></div></div>
<div class="card"><b>보유 포지션</b><div id="positions" class="muted">-</div></div>
<div class="card"><b>최근 거래</b><div id="trades" class="muted">-</div></div>
<div class="muted">이 화면은 모의투자용입니다. 시세 지연·서버 장애·모의 체결 오차가 있을 수 있습니다.</div>
</main><script>
const won=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0})+'원';
async function refresh(){try{let r=await fetch('/api/status');let d=await r.json();
document.getElementById('equity').textContent=won(d.equity);
let pnl=d.pnl;let p=document.getElementById('pnl');p.textContent='누적 손익 '+won(pnl);p.className=pnl>=0?'good':'bad';
document.getElementById('cash').textContent=won(d.cash);document.getElementById('count').textContent=d.positions.length+'종목';
document.getElementById('status').textContent=d.paused?'일시정지':'运行 중 · 모의투자';
document.getElementById('positions').innerHTML=d.positions.length?'<table><tr><th>종목</th><th>수량</th><th>평단</th><th>손절/익절</th></tr>'+d.positions.map(x=>`<tr><td>${x.market}</td><td>${Number(x.qty).toFixed(6)}</td><td>${won(x.avg)}</td><td>${won(x.stop)} / ${won(x.take)}</td></tr>`).join('')+'</table>':'보유 종목 없음';
document.getElementById('trades').innerHTML=d.trades.length?'<table><tr><th>시간</th><th>종목</th><th>구분</th><th>가격</th><th>손익</th></tr>'+d.trades.map(x=>`<tr><td>${x.time}</td><td>${x.market}</td><td>${x.side}</td><td>${won(x.price)}</td><td>${won(x.pnl)}</td></tr>`).join('')+'</table>':'거래 내역 없음';
}catch(e){document.getElementById('status').textContent='서버 연결 오류'}}
async function control(paused){await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({paused})});refresh()}
refresh();setInterval(refresh,20000);
</script></body></html>
""".replace("运行 중", "실행 중")


def authorized():
    if not DASHBOARD_PASSWORD:
        return True
    return request.headers.get("X-Dashboard-Password") == DASHBOARD_PASSWORD or request.args.get("password") == DASHBOARD_PASSWORD


def read_control():
    try:
        with open(CONTROL, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"paused": False}


@app.route("/")
def index():
    if not authorized():
        return "Unauthorized", 401
    return render_template_string(PAGE)


@app.route("/api/status")
def status():
    if not authorized():
        return jsonify({"error": "unauthorized"}), 401
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        state = c.execute("SELECT cash,peak_equity,day,day_start_equity,halted FROM state WHERE id=1").fetchone()
        pos = c.execute("SELECT market,qty,avg_price,stop_price,take_price,opened_at FROM positions").fetchall()
        trades = c.execute("SELECT time,market,side,price,qty,fee,pnl,reason FROM trades ORDER BY id DESC LIMIT 20").fetchall()
    if state is None:
        return jsonify({"error": "bot database not initialized"}), 503
    positions = [dict(market=x["market"],qty=x["qty"],avg=x["avg_price"],stop=x["stop_price"],take=x["take_price"]) for x in pos]
    # Dashboard estimate uses average entry for holdings; it is not live mark-to-market.
    equity = float(state["cash"]) + sum(x["qty"]*x["avg"] for x in positions)
    return jsonify({"cash":state["cash"],"equity":equity,"pnl":equity-10_000_000,
                    "positions":positions,"trades":[dict(x) for x in trades],
                    "paused":bool(read_control().get("paused",False)),
                    "risk_halted":bool(state["halted"])})


@app.route("/api/control", methods=["POST"])
def control():
    if not authorized():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    paused = bool(data.get("paused", False))
    with open(CONTROL, "w", encoding="utf-8") as f:
        json.dump({"paused":paused}, f)
    return jsonify({"ok":True,"paused":paused})


if __name__ == "__main__":
    # Do not expose this development server directly to the public internet.
    app.run(host="0.0.0.0", port=8080)
