# Upbit AI-style Paper Trading Bot

업비트의 **공개 시세 API만** 사용해 5분봉 기반 규칙 점수 전략을 모의 실행하는 파이썬 프로젝트입니다.
실제 주문 API, API Key, 출금 권한은 전혀 사용하지 않습니다.

> 이 프로젝트의 "AI 전략"은 머신러닝 모델이 아니라 EMA/RSI/MACD/거래량을 점수화하는 규칙 기반 전략입니다. 수익을 보장하지 않으며, 실거래 전 장기간 검증이 필요합니다.

## 1. 준비물
- Python 3.10~3.12 권장
- 인터넷 연결
- 업비트 계정/API Key 불필요

## 2. 설치

### Windows
```powershell
cd upbit_ai_paper_bot
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

PowerShell에서 가상환경 실행이 차단되면 현재 창에서 아래 명령을 실행한 뒤 다시 활성화하세요.
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### macOS
```bash
cd upbit_ai_paper_bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## 3. 설정
`config.py`에서 종목, 봉 주기, 손절/익절, 매수 점수, 초기 가상자금을 바꿀 수 있습니다.

기본값:
- 가상 초기자금: 10,000,000 KRW
- 종목: BTC, ETH, XRP, SOL, DOGE
- 봉: 5분
- 최대 동시 보유: 3종목
- 종목당 최대 배분: 평가자산의 20%
- 손절: -2.5%
- 익절: +5%
- 일일 손실 -3% 도달 시 신규 매매 중지
- 계좌 고점 대비 -10% 도달 시 신규 매매 중지
- 수수료/슬리피지 가정: 각각 0.05%

## 4. 결과 확인
- `bot.log`: 실행 로그
- `paper_trading.db`: 가상 잔고, 포지션, 거래 기록(SQLite)

거래 내역 CSV 추출:
```bash
python export_trades.py
```
`trades.csv`가 생성됩니다.

## 5. 중지 및 재시작
- 중지: 터미널에서 `Ctrl+C`
- 재시작: 같은 폴더에서 `python main.py`
- 모의 잔고와 보유 포지션은 SQLite에 저장되어 재시작 후 이어집니다.

## 6. 위험 관리 주의
- 일일 손실/고점 낙폭 중지 기능은 신규 진입을 막는 안전장치이며, 손실을 없애거나 가격 급변 시 손절 체결을 보장하지 않습니다.
- 모의 체결은 실제 호가 잔량, 지연, 부분 체결, 거래소 장애를 완벽히 재현하지 않습니다.
- 기본 수수료/슬리피지는 예시값입니다. 실제 거래 조건에 맞춰 검증하세요.
- 실제 주문 기능은 포함하지 않았습니다. 실거래 전 별도 검토, 백테스트, 장기간 모의운영이 필요합니다.
- API Key를 추가하거나 출금 권한을 부여하지 마세요. 이 버전은 공개 시세 조회만으로 동작합니다.

## 7. 전략 개요
각 완료된 5분봉에서:
- EMA9 > EMA21: +1, 반대면 -1
- 종가 > EMA50: +1, 반대면 -1
- MACD 히스토그램 개선: +1, 음수면 -1
- RSI 45~68: +1, 75 초과면 -1
- 거래량이 20봉 평균보다 20% 이상 크고 상승 마감: +1

점수가 설정한 진입 기준 이상이면 위험 한도 내에서 모의 매수합니다.
보유 중에는 손절, 익절, 추세 약화 신호를 확인합니다.


## 8. 24시간 클라우드 + 모바일 대시보드 (권장)

아이폰에서 파이썬 프로세스를 직접 24시간 유지하는 대신, Ubuntu VPS에 Docker로 실행하고 아이폰 Safari로 대시보드를 여는 방식입니다.

### 서버 준비
- Ubuntu 22.04/24.04 VPS (최소 1 vCPU, RAM 1GB 권장)
- Docker Engine 및 Docker Compose 설치
- 도메인과 HTTPS(예: Caddy 또는 Nginx + Let's Encrypt) 설정 권장

### 배포
프로젝트 폴더에서:
```bash
cp .env.example .env
nano .env  # DASHBOARD_PASSWORD를 길고 임의적인 값으로 변경
mkdir -p data
docker compose up -d --build
docker compose logs -f trader
```

### 대시보드 보안
대시보드 컨테이너는 기본적으로 서버 내부 `127.0.0.1:8080`에만 바인딩됩니다. 인터넷에 8080 포트를 직접 공개하지 마세요.
Caddy/Nginx를 통해 HTTPS와 인증을 설정한 뒤 아이폰 Safari에서 도메인으로 접속하세요. VPS 방화벽은 SSH와 HTTPS만 허용하세요.

### 주의
- 이 구성은 모의투자 전용이며 업비트 개인 API 키가 필요 없습니다.
- 대시보드의 일시정지는 매매 루프를 멈추므로 보유 포지션의 손절 감시도 멈춥니다. 일시정지 상태로 오래 두지 마세요.
- VPS 재부팅 후 Docker가 컨테이너를 재시작하지만, 네트워크/API 장애나 거래소 시세 제한이 발생할 수 있습니다.
- 실제 운용 전에는 VPS에서 장기간 모의 운영과 로그 검토가 필요합니다.
