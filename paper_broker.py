import sqlite3
from datetime import datetime


class PaperBroker:
    def __init__(self, initial_cash, fee_rate, slippage, db_path):
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.fee_rate = float(fee_rate)
        self.slippage = float(slippage)
        self.db_path = db_path
        self.positions = {}
        self.peak_equity = float(initial_cash)
        self.day = None
        self.day_start_equity = float(initial_cash)
        self.halted = False
        self._init_db()
        self._load_state()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS state
                (id INTEGER PRIMARY KEY CHECK(id=1), cash REAL, peak_equity REAL,
                 day TEXT, day_start_equity REAL, halted INTEGER)""")
            c.execute("""CREATE TABLE IF NOT EXISTS positions
                (market TEXT PRIMARY KEY, qty REAL, avg_price REAL, stop_price REAL,
                 take_price REAL, opened_at TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS trades
                (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, market TEXT,
                 side TEXT, price REAL, qty REAL, fee REAL, pnl REAL, reason TEXT)""")

    def _load_state(self):
        with self._conn() as c:
            row = c.execute("SELECT cash,peak_equity,day,day_start_equity,halted FROM state WHERE id=1").fetchone()
            if row:
                self.cash, self.peak_equity, self.day, self.day_start_equity, halted = row
                self.halted = bool(halted)
            else:
                self.day = datetime.now().date().isoformat()
            rows = c.execute("SELECT market,qty,avg_price,stop_price,take_price,opened_at FROM positions").fetchall()
            self.positions = {r[0]: {"qty":r[1], "avg":r[2], "stop":r[3], "take":r[4], "opened":r[5]} for r in rows}
            self._save_state()

    def _save_state(self):
        with self._conn() as c:
            c.execute("""INSERT OR REPLACE INTO state
                (id,cash,peak_equity,day,day_start_equity,halted)
                VALUES (1,?,?,?,?,?)""",
                (self.cash, self.peak_equity, self.day, self.day_start_equity, int(self.halted)))

    def _save_position(self, market):
        p = self.positions.get(market)
        with self._conn() as c:
            if p:
                c.execute("INSERT OR REPLACE INTO positions VALUES (?,?,?,?,?,?)",
                          (market,p["qty"],p["avg"],p["stop"],p["take"],p["opened"]))
            else:
                c.execute("DELETE FROM positions WHERE market=?", (market,))

    def roll_day_if_needed(self, day):
        if self.day != day:
            self.day = day
            self.day_start_equity = self.mark_to_market({})
            self._save_state()

    def mark_to_market(self, prices):
        total = self.cash
        for market, p in self.positions.items():
            price = prices.get(market, p["avg"])
            total += p["qty"] * price
        self.peak_equity = max(self.peak_equity, total)
        self._save_state()
        return total

    def _log_trade(self, market, side, price, qty, fee, pnl, reason, now):
        with self._conn() as c:
            c.execute("INSERT INTO trades(time,market,side,price,qty,fee,pnl,reason) VALUES (?,?,?,?,?,?,?,?)",
                      (now.isoformat(),market,side,price,qty,fee,pnl,reason))

    def _sell(self, market, price, reason, now):
        p = self.positions[market]
        exec_price = price * (1 - self.slippage)
        gross = p["qty"] * exec_price
        fee = gross * self.fee_rate
        proceeds = gross - fee
        pnl = proceeds - p["qty"] * p["avg"]
        self.cash += proceeds
        qty = p["qty"]
        del self.positions[market]
        self._save_position(market)
        self._log_trade(market,"SELL",exec_price,qty,fee,pnl,reason,now)
        self._save_state()
        return f"[모의매도] {market} {reason} | 실현손익 {pnl:,.0f}원"

    def evaluate_market(self, market, price, score, reason, now, max_positions,
                        max_coin_weight, risk_per_trade, stop_loss, take_profit,
                        buy_score, sell_score, min_order_krw):
        if price <= 0:
            return None

        # 보유 중이면 손절/익절/추세 이탈을 먼저 검사
        if market in self.positions:
            p = self.positions[market]
            if price <= p["stop"]:
                return self._sell(market, price, "손절", now)
            if price >= p["take"]:
                return self._sell(market, price, "익절", now)
            if score <= sell_score:
                return self._sell(market, price, "매도 신호", now)
            return None

        if self.halted or score < buy_score or len(self.positions) >= max_positions:
            return None

        equity = self.mark_to_market({market: price})
        # 일일 손실 한도 및 고점 대비 최대 낙폭 제한
        if equity <= self.day_start_equity * 0.97:
            self.halted = True
            self._save_state()
            return "[거래중지] 일일 손실 한도 -3% 도달"
        if equity <= self.peak_equity * 0.90:
            self.halted = True
            self._save_state()
            return "[거래중지] 고점 대비 낙폭 -10% 도달"

        risk_budget = equity * risk_per_trade
        risk_sized = risk_budget / stop_loss
        allocation_cap = equity * max_coin_weight
        order_krw = min(risk_sized, allocation_cap, self.cash)
        if order_krw < min_order_krw:
            return None

        exec_price = price * (1 + self.slippage)
        fee = order_krw * self.fee_rate
        spend = order_krw
        qty = (spend - fee) / exec_price
        if qty <= 0:
            return None

        self.cash -= spend
        self.positions[market] = {
            "qty": qty, "avg": exec_price,
            "stop": exec_price * (1-stop_loss),
            "take": exec_price * (1+take_profit),
            "opened": now.isoformat()
        }
        self._save_position(market)
        self._log_trade(market,"BUY",exec_price,qty,fee,0,reason,now)
        self._save_state()
        return f"[모의매수] {market} {spend:,.0f}원 | 점수={score} | {reason}"

    def reset_halt(self):
        self.halted = False
        self._save_state()
