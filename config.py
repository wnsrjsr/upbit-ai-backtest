CFG = {
    # 초기 가상 원화 잔고
    "initial_cash": 10_000_000,

    # 업비트 KRW 마켓. 필요하면 종목을 추가/삭제하세요.
    "markets": ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-DOGE"],

    # 5분봉 기준, 완료된 캔들만 분석
    "interval": "minute5",
    "poll_seconds": 20,

    # 모의 체결 가정치: 수수료 0.05%, 슬리피지 0.05%
    # 실제 업비트 수수료와 체결가격은 계정/이벤트/시장 상황에 따라 다릅니다.
    "fee_rate": 0.0005,
    "slippage": 0.0005,

    # 위험 관리
    "max_positions": 3,
    "max_coin_weight": 0.20,  # 종목당 총 평가자산의 최대 20%
    "risk_per_trade": 0.01,   # 손절 도달 시 평가자산의 약 1% 위험 예산
    "stop_loss": 0.025,       # 평균 매수가 대비 -2.5%
    "take_profit": 0.05,      # 평균 매수가 대비 +5%
    "buy_score": 3,
    "sell_score": -1,
    "min_order_krw": 5000,

    "db_path": "data/paper_trading.db",
    "log_level": "INFO",
}
