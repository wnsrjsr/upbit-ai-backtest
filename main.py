import time
import logging
from datetime import datetime, timezone, timedelta

import pyupbit
from config import CFG
from paper_broker import PaperBroker
from strategy import analyze

KST = timezone(timedelta(hours=9))

logging.basicConfig(
    level=getattr(logging, CFG["log_level"].upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log", encoding="utf-8")]
)
log = logging.getLogger("upbit-paper-bot")


def kst_now():
    return datetime.now(KST)


def main():
    broker = PaperBroker(
        initial_cash=CFG["initial_cash"],
        fee_rate=CFG["fee_rate"],
        slippage=CFG["slippage"],
        db_path=CFG["db_path"],
    )
    markets = CFG["markets"]
    interval = CFG["interval"]
    poll_seconds = CFG["poll_seconds"]
    last_candle = {}
    last_signal = {}

    log.info("UPBIT PAPER BOT 시작 | 초기자금=%s원 | 마켓=%s", f'{CFG["initial_cash"]:,.0f}', markets)
    log.info("모의투자 전용: 실제 주문/API 인증키를 사용하지 않습니다.")

    while True:
        try:
            now = kst_now()
            broker.roll_day_if_needed(now.date().isoformat())

            # Mobile dashboard control file: pause prevents new trades and exits.
            # Existing positions remain open and continue to be monitored.
            try:
                import json
                with open("data/control.json", "r", encoding="utf-8") as f:
                    remote_control = json.load(f)
                paused = bool(remote_control.get("paused", False))
            except (FileNotFoundError, ValueError):
                paused = False

            if paused:
                log.info("모바일 대시보드에서 일시정지됨: 신규 진입/자동 청산을 모두 중단합니다.")
                time.sleep(poll_seconds)
                continue

            snapshots = {}
            for market in markets:
                try:
                    df = pyupbit.get_ohlcv(market, interval=interval, count=120)
                    if df is None or len(df) < 60:
                        log.warning("%s 캔들 데이터 부족", market)
                        continue

                    # 마지막 행은 진행 중일 수 있으므로 직전 완료 캔들만 사용
                    candle_time = df.index[-2]
                    closed = df.iloc[:-1].copy()
                    price = float(pyupbit.get_current_price(market) or closed["close"].iloc[-1])
                    snapshots[market] = price
                    is_new_candle = market not in last_candle or candle_time > last_candle[market]
                    if is_new_candle:
                        last_candle[market] = candle_time
                        last_signal[market] = analyze(closed)
                    score, reason = last_signal.get(market, (0, "신호 대기"))

                    action = broker.evaluate_market(
                        market=market,
                        price=price,
                        score=score,
                        reason=reason,
                        now=now,
                        max_positions=CFG["max_positions"],
                        max_coin_weight=CFG["max_coin_weight"],
                        risk_per_trade=CFG["risk_per_trade"],
                        stop_loss=CFG["stop_loss"],
                        take_profit=CFG["take_profit"],
                        buy_score=CFG["buy_score"],
                        sell_score=CFG["sell_score"],
                        min_order_krw=CFG["min_order_krw"],
                    )
                    if action:
                        log.info("%s", action)
                except Exception:
                    log.exception("%s 처리 중 오류", market)
                time.sleep(0.15)

            if snapshots:
                equity = broker.mark_to_market(snapshots)
                log.info("잔고=%s원 | 평가자산=%s원 | 누적손익=%s원 | 보유=%d종목",
                         f"{broker.cash:,.0f}", f"{equity:,.0f}",
                         f"{equity-CFG['initial_cash']:,.0f}", len(broker.positions))

            time.sleep(poll_seconds)
        except KeyboardInterrupt:
            log.info("사용자 요청으로 종료합니다.")
            break
        except Exception:
            log.exception("메인 루프 오류. 30초 후 재시도")
            time.sleep(30)


if __name__ == "__main__":
    main()
