# 아이폰용 업비트 백테스트 앱

## 빠른 실행 (인터넷이 연결된 PC 또는 클라우드)

```bash
pip install -r requirements-backtest.txt
streamlit run backtest_app.py --server.address 0.0.0.0 --server.port 8501
```

같은 Wi-Fi의 아이폰에서는 `http://컴퓨터의내부IP:8501`로 접속합니다.

## 아이폰만으로 접속하려면

이 폴더를 GitHub 저장소에 올린 뒤 Streamlit Community Cloud에서 `backtest_app.py`를 메인 파일로 배포합니다. 배포가 끝나면 발급된 `https://...streamlit.app` 주소를 아이폰 Safari에서 엽니다. GitHub/Streamlit 계정 생성 및 배포 승인은 사용자가 직접 해야 합니다.

## 주의
- 업비트 공개 API에서 과거 5분봉을 실시간으로 내려받습니다. 1년치 5개 종목은 수집에 시간이 걸릴 수 있습니다.
- API 제한 또는 네트워크 오류 시 다시 실행하거나 종목/기간을 나눠 테스트하세요.
- 실제 매매가 아닌 과거 데이터 기반 시뮬레이션입니다. 결과는 미래 수익을 보장하지 않습니다.
- 5분봉 내부에서 손절과 익절이 모두 닿으면 손절이 먼저 체결된 것으로 보수적으로 처리합니다.
