import time
from datetime import date, datetime, timedelta
import requests
import pandas as pd
import streamlit as st
import plotly.express as px

API = 'https://api.upbit.com/v1/candles/minutes/5'
MARKETS = ['KRW-BTC','KRW-ETH','KRW-XRP','KRW-SOL','KRW-DOGE']

st.set_page_config(page_title='업비트 전략 백테스트', page_icon='📊', layout='wide')
st.title('업비트 5분봉 전략 백테스트')
st.caption('모의 백테스트 전용 · 업비트 공개 시세 사용 · 실제 주문 기능 없음')

@st.cache_data(show_spinner=False, ttl=86400)
def fetch_market(market, start_s, end_s):
    start = pd.Timestamp(start_s, tz='Asia/Seoul')
    end = pd.Timestamp(end_s, tz='Asia/Seoul')
    cursor = end
    chunks = []
    sess = requests.Session()
    while cursor > start:
        params = {'market': market, 'count': 200, 'to': cursor.strftime('%Y-%m-%dT%H:%M:%S')}
        resp = sess.get(API, params=params, timeout=25)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        df = pd.DataFrame(rows)
        df['time'] = pd.to_datetime(df['candle_date_time_kst']).dt.tz_localize('Asia/Seoul')
        df = df.rename(columns={'opening_price':'open','high_price':'high','low_price':'low','trade_price':'close','candle_acc_trade_volume':'volume'})
        chunks.append(df[['time','open','high','low','close','volume']])
        oldest = df['time'].min()
        if oldest >= cursor:
            break
        cursor = oldest
        time.sleep(0.12)
    if not chunks:
        return pd.DataFrame(columns=['open','high','low','close','volume'])
    out = pd.concat(chunks).drop_duplicates('time').set_index('time').sort_index()
    return out.loc[(out.index >= start) & (out.index <= end)]


def indicators(df):
    c, v = df.close.astype(float), df.volume.astype(float)
    e9 = c.ewm(span=9, adjust=False).mean()
    e21 = c.ewm(span=21, adjust=False).mean()
    e50 = c.ewm(span=50, adjust=False).mean()
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    d = c.diff(); gain=d.clip(lower=0).ewm(alpha=1/14,adjust=False).mean(); loss=(-d.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    rsi=100-(100/(1+gain/loss.replace(0,1e-12)))
    va=v.rolling(20).mean()
    score=pd.Series(0,index=df.index,dtype=int)
    score += (e9>e21).astype(int)*2-1
    score += (c>e50).astype(int)*2-1
    score += ((hist>0)&(hist>=hist.shift(1))).astype(int)
    score -= (hist<0).astype(int)
    score += rsi.between(45,68).astype(int)
    score -= (rsi>75).astype(int)
    score += ((va.notna())&(v>va*1.2)&(c>=c.shift(1))).astype(int)
    return score


def run_backtest(data, initial, fee, slip, stop_loss, take_profit, buy_score, sell_score, max_positions, weight, risk, daily_limit, mdd_limit):
    idx = sorted(set().union(*[set(x.index) for x in data.values()]))
    frames = {m: d.reindex(idx).ffill() for m,d in data.items()}
    scores = {m: indicators(d) for m,d in data.items()}
    cash=float(initial); positions={}; trades=[]; daily={}; equity_rows=[]; peak=float(initial); halted_day=None; halted_all=False; day_start=float(initial)
    prev_day=None
    for i, ts in enumerate(idx):
        day=ts.date()
        if day != prev_day:
            prev_day=day; day_start=cash+sum(p['qty']*frames[m].close.iloc[i-1] for m,p in positions.items()) if i else cash; halted_day=None
        # 현재 봉의 고저가로 기존 포지션 청산. 같은 봉 손절/익절 동시 터치 시 보수적으로 손절 우선.
        for m in list(positions):
            row=frames[m].iloc[i]
            if pd.isna(row.close): continue
            p=positions[m]; reason=None; raw=None
            if row.low <= p['stop']:
                reason='손절'; raw=min(float(row.open),p['stop']) if row.open < p['stop'] else p['stop']
            elif row.high >= p['take']:
                reason='익절'; raw=max(float(row.open),p['take']) if row.open > p['take'] else p['take']
            elif i>0 and scores[m].iloc[i-1] <= sell_score:
                reason='매도 신호'; raw=float(row.open)
            if reason:
                px=raw*(1-slip); gross=p['qty']*px; out_fee=gross*fee; proceeds=gross-out_fee; pnl=proceeds-p['cost_basis']; cash+=proceeds
                trades.append({'time':ts,'market':m,'side':'SELL','price':px,'qty':p['qty'],'fee':out_fee,'pnl':pnl,'reason':reason,'return_pct':pnl/p['cost_basis']*100})
                del positions[m]
        marks={m:float(frames[m].close.iloc[i]) for m in data if pd.notna(frames[m].close.iloc[i])}
        equity=cash+sum(p['qty']*marks.get(m,p['entry']) for m,p in positions.items()); peak=max(peak,equity)
        if equity <= day_start*(1-daily_limit): halted_day=day
        if equity <= peak*(1-mdd_limit): halted_all=True
        # 이전 완료 봉의 점수로 이번 봉 시가 진입, 미래정보 사용 방지
        if i>0 and not halted_all and halted_day != day and len(positions)<max_positions:
            for m in data:
                if m in positions or len(positions)>=max_positions: continue
                row=frames[m].iloc[i]
                if pd.isna(row.open) or pd.isna(scores[m].iloc[i-1]) or scores[m].iloc[i-1] < buy_score: continue
                equity=cash+sum(p['qty']*marks.get(k,p['entry']) for k,p in positions.items())
                budget=min(equity*risk/stop_loss,equity*weight,cash)
                if budget < 5000: continue
                exec_px=float(row.open)*(1+slip); buy_fee=budget*fee; qty=(budget-buy_fee)/exec_px
                cash-=budget; positions[m]={'qty':qty,'entry':exec_px,'cost_basis':budget,'stop':exec_px*(1-stop_loss),'take':exec_px*(1+take_profit)}
                trades.append({'time':ts,'market':m,'side':'BUY','price':exec_px,'qty':qty,'fee':buy_fee,'pnl':0.0,'reason':f'매수 점수 {int(scores[m].iloc[i-1])}','return_pct':0.0})
        equity=cash+sum(p['qty']*marks.get(m,p['entry']) for m,p in positions.items())
        peak=max(peak,equity)
        equity_rows.append({'time':ts,'equity':equity,'cash':cash,'drawdown_pct':(equity/peak-1)*100})
    # 마지막 봉 종가로 강제 평가청산
    if idx:
        ts=idx[-1]
        for m,p in list(positions.items()):
            price=float(frames[m].close.iloc[-1])*(1-slip); gross=p['qty']*price; f=gross*fee; proceeds=gross-f; pnl=proceeds-p['cost_basis']; cash+=proceeds
            trades.append({'time':ts,'market':m,'side':'SELL','price':price,'qty':p['qty'],'fee':f,'pnl':pnl,'reason':'기간 종료 평가청산','return_pct':pnl/p['cost_basis']*100})
        equity_rows[-1]['equity']=cash; equity_rows[-1]['cash']=cash
    return pd.DataFrame(equity_rows),pd.DataFrame(trades)

with st.sidebar:
    st.header('백테스트 설정')
    start=st.date_input('시작일',date(2025,1,1))
    end=st.date_input('종료일',date(2025,12,31))
    initial=st.number_input('초기 투자금 (원)',min_value=100000,max_value=1000000000,value=10000000,step=1000000)
    markets=st.multiselect('거래 종목',MARKETS,default=MARKETS)
    fee=st.number_input('수수료 (%)',min_value=0.0,max_value=1.0,value=0.05,step=0.01)/100
    slip=st.number_input('슬리피지 (%)',min_value=0.0,max_value=1.0,value=0.05,step=0.01)/100
    st.caption('기존 설정: 손절 2.5% · 익절 5% · 매수 점수 3 · 매도 점수 -1')
    run=st.button('2025년 백테스트 실행',type='primary',use_container_width=True)

if run:
    if start>=end or not markets:
        st.error('기간과 거래 종목을 확인해 주세요.')
    else:
        all_data={}
        with st.spinner('업비트에서 5분봉 과거 데이터를 수집하고 있습니다. 종목별로 수 분 걸릴 수 있습니다.'):
            try:
                for m in markets:
                    st.write(f'{m} 데이터 수집 중…')
                    all_data[m]=fetch_market(m,start.isoformat(),end.isoformat()+'T23:59:59')
                    if all_data[m].empty: raise ValueError(f'{m} 데이터가 없습니다.')
            except Exception as e:
                st.error(f'데이터 수집 실패: {e}. 잠시 후 다시 시도하거나 기간을 줄여 주세요.')
                st.stop()
        with st.spinner('전략 시뮬레이션 중…'):
            eq,tr=run_backtest(all_data,initial,fee,slip,0.025,0.05,3,-1,3,0.20,0.01,0.03,0.10)
        if eq.empty:
            st.warning('계산할 데이터가 없습니다.')
        else:
            final=float(eq.equity.iloc[-1]); ret=(final/initial-1)*100
            sells=tr[tr.side=='SELL'] if not tr.empty else pd.DataFrame()
            wins=sells[sells.pnl>0] if not sells.empty else sells
            loss=sells[sells.pnl<0] if not sells.empty else sells
            c1,c2,c3,c4=st.columns(4)
            c1.metric('최종 평가자산',f'{final:,.0f}원',f'{ret:+.2f}%')
            c2.metric('실현 매도 횟수',f'{len(sells):,}회')
            c3.metric('승률',f'{len(wins)/len(sells)*100:.1f}%' if len(sells) else '—')
            c4.metric('최대 낙폭',f'{eq.drawdown_pct.min():.2f}%')
            st.subheader('자산 변화')
            st.plotly_chart(px.line(eq,x='time',y='equity',title='계좌 평가자산 (KRW)'),use_container_width=True)
            eq['date']=pd.to_datetime(eq.time).dt.date
            daily_eq=eq.groupby('date').tail(1).copy(); daily_eq['daily_return_pct']=daily_eq.equity.pct_change().fillna(daily_eq.equity.iloc[0]/initial-1)*100
            daily_eq['pnl']=daily_eq.equity.diff().fillna(daily_eq.equity.iloc[0]-initial)
            st.subheader('일별 손익')
            st.dataframe(daily_eq[['date','equity','pnl','daily_return_pct']].rename(columns={'date':'날짜','equity':'평가자산(원)','pnl':'일손익(원)','daily_return_pct':'일수익률(%)'}),use_container_width=True,hide_index=True)
            st.subheader('월별 수익률')
            daily_eq['month']=pd.to_datetime(daily_eq.date.astype(str)).dt.to_period('M').astype(str)
            monthly=daily_eq.groupby('month').agg(start_equity=('equity','first'),end_equity=('equity','last'))
            monthly['return_pct']=(monthly.end_equity/monthly.start_equity-1)*100
            st.dataframe(monthly.reset_index().rename(columns={'month':'월','return_pct':'월수익률(%)'}),use_container_width=True,hide_index=True)
            st.subheader('거래 내역')
            st.dataframe(tr,use_container_width=True,hide_index=True)
            st.download_button('일별 손익 CSV 다운로드',daily_eq.to_csv(index=False).encode('utf-8-sig'),'daily_backtest.csv','text/csv')
            st.download_button('전체 거래 CSV 다운로드',tr.to_csv(index=False).encode('utf-8-sig'),'trades_backtest.csv','text/csv')
            st.info('백테스트 가정: 완료된 봉 신호를 다음 봉 시가에 체결, 손절·익절은 봉 고저가로 검사하며 같은 봉에서 둘 다 닿으면 손절 우선. 거래소 호가·체결 지연·유동성은 완벽히 재현하지 못합니다.')
else:
    st.markdown('''### 사용 방법\n1. 기간과 종목을 선택합니다.\n2. **2025년 백테스트 실행**을 누릅니다.\n3. 업비트 공개 API에서 데이터를 받아 수익률·손실률을 계산합니다.\n4. 일별·월별 결과와 거래 내역을 확인하고 CSV로 저장합니다.\n\n초기값은 기존 프로그램 설정인 1,000만 원, 5개 종목, 수수료 0.05%, 슬리피지 0.05%입니다.''')
