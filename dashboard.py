# dashboard.py — 交互式 HTML 市场仪表盘。
#   ① 扫 universe.py 里的全部标的，按"透明打分"算入场信号，每个板块出 Top 10 榜
#   ② 蜡烛图 + 成交量 + RSI 副图；顶部搜索框可在已烤进的清单里任意切换看图
#   ③ 选中哪只，下方就显示它的评分明细 + 趋势/RSI/ADX/ATR + 仓位建议
# 浏览器有 CORS 不能直连 Yahoo，所以由 Python 取数算好内嵌进 dashboard.html。
# 用法： venv\Scripts\python.exe dashboard.py   然后双击 dashboard.html
# 加/减股票：改 universe.py 再重跑。
import os
import json
import datetime as dt
import pandas as pd
import indicators as ind
import universe as U

ACCOUNT, RISK_PCT, ATR_MULT = 10000, 1.0, 1.5     # 仓位计算参数（按需改）
BARS_DAILY = 140                                   # 日线图保留根数
BARS_INTRADAY = 160                                # 盘中图保留根数（控制文件大小）
HERE = os.path.dirname(os.path.abspath(__file__))


def fnum(x):
    return None if x is None or pd.isna(x) else round(float(x), 4)


def build_series(df, intraday, bars):
    """把一段K线压成并列数组(含 SMA20/50/RSI)。日线 time=日期串，盘中 time=epoch秒。"""
    c = df["Close"]
    s20 = ind.sma(c, 20); s50 = ind.sma(c, 50); rsi = ind.rsi(c, 14)
    df = df.tail(bars); s20 = s20.tail(bars); s50 = s50.tail(bars); rsi = rsi.tail(bars)
    t = [int(ts.timestamp()) if intraday else ts.strftime("%Y-%m-%d") for ts in df.index]
    return dict(
        t=t,
        o=[round(float(x), 4) for x in df["Open"]],
        h=[round(float(x), 4) for x in df["High"]],
        l=[round(float(x), 4) for x in df["Low"]],
        c=[round(float(x), 4) for x in df["Close"]],
        v=[float(x) for x in df["Volume"]],
        s20=[fnum(x) for x in s20],
        s50=[fnum(x) for x in s50],
        rsi=[fnum(x) for x in rsi],
    )


def resample_4h(df1h):
    """用 1 小时K线合成 4 小时(yfinance 没有原生 4h)。"""
    if df1h is None or len(df1h) < 8:
        return None
    o = df1h["Open"].resample("4h").first()
    h = df1h["High"].resample("4h").max()
    l = df1h["Low"].resample("4h").min()
    cc = df1h["Close"].resample("4h").last()
    v = df1h["Volume"].resample("4h").sum()
    r = pd.concat([o, h, l, cc, v], axis=1)
    r.columns = ["Open", "High", "Low", "Close", "Volume"]
    return r.dropna()


def intraday_frames(sym):
    """重点标的：取 1m/5m/15m/1h，并由1h合成4h。返回 {tf: series}。"""
    out = {}
    for key, interval, period in [("1m", "1m", "5d"), ("5m", "5m", "1mo"), ("15m", "15m", "1mo")]:
        d = ind.load(sym, period=period, interval=interval)
        if d is not None and len(d) >= 40:
            out[key] = build_series(d, True, BARS_INTRADAY)
    dh = ind.load(sym, period="6mo", interval="60m")
    if dh is not None and len(dh) >= 40:
        out["1h"] = build_series(dh, True, BARS_INTRADAY)
        d4 = resample_4h(dh)
        if d4 is not None and len(d4) >= 20:
            out["4h"] = build_series(d4, True, BARS_INTRADAY)
    return out


def process(sym, name, mk):
    """取一只标的的数据：算指标→打分→压缩成图表数据。返回 (meta, series) 或 None。"""
    df = ind.load(sym, period="1y", interval="1d")
    if df is None or len(df) < 60:
        return None
    c, v = df["Close"], df["Volume"]
    s20 = ind.sma(c, 20); s50 = ind.sma(c, 50); r = ind.rsi(c, 14)
    macd_l, macd_s, _ = ind.macd(c)
    adx_, pdi, mdi = ind.adx(df, 14)
    atr_ = ind.atr(df, 14)
    v20 = v.rolling(20).mean()

    price = float(c.iloc[-1]); prev = float(c.iloc[-2])
    p20 = float(s20.iloc[-1]); p50 = float(s50.iloc[-1])
    rsi_v = float(r.iloc[-1]); adx_v = float(adx_.iloc[-1])
    pdi_v = float(pdi.iloc[-1]); mdi_v = float(mdi.iloc[-1])
    macd_v = float(macd_l.iloc[-1]); sig_v = float(macd_s.iloc[-1])
    atr_v = float(atr_.iloc[-1])
    vol_now = float(v.iloc[-1])
    vol_avg = float(v20.iloc[-1]) if pd.notna(v20.iloc[-1]) else 0.0
    chg = (price / prev - 1) * 100 if prev else 0.0

    # —— 20日突破检测（进场规则引擎用）：今天刚突破"前20日最高/最低"（不含当天），昨天还没破 ——
    hi20 = df["High"].rolling(20).max().shift(1)
    lo20 = df["Low"].rolling(20).min().shift(1)
    bo_l = bo_s = False
    if len(df) >= 23 and pd.notna(hi20.iloc[-1]) and pd.notna(hi20.iloc[-2]):
        bo_l = price > float(hi20.iloc[-1]) and float(c.iloc[-2]) <= float(hi20.iloc[-2])
        bo_s = price < float(lo20.iloc[-1]) and float(c.iloc[-2]) >= float(lo20.iloc[-2])
    h20_v = fnum(hi20.iloc[-1])   # 画在图上的"前20日高/低"参考线
    l20_v = fnum(lo20.iloc[-1])

    # —— 高周期(周线)定方向：把同一年日线 resample 成周线，看大方向 ——
    # KhanSaab 纪律：高周期定方向、低周期找入场；高低周期冲突就不该顺势进场。
    wk = df.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    wk_up = wk_dn = False
    if len(wk) >= 22:
        w20s = ind.sma(wk["Close"], 20)
        wpx = float(wk["Close"].iloc[-1]); w20v = float(w20s.iloc[-1])
        w20_prev = float(w20s.iloc[-3]) if pd.notna(w20s.iloc[-3]) else w20v
        if pd.notna(w20v):
            wk_up = wpx > w20v and w20v >= w20_prev   # 周线在20周均线上方且均线上行
            wk_dn = wpx < w20v and w20v <= w20_prev   # 周线在下方且均线下行

    above = price > p20
    below = price < p20
    # 近5日内是否刚上穿 / 下破 20MA
    cross_up = above and any(
        pd.notna(s20.iloc[-k]) and float(c.iloc[-k]) <= float(s20.iloc[-k]) for k in range(2, 7))
    cross_dn = below and any(
        pd.notna(s20.iloc[-k]) and float(c.iloc[-k]) >= float(s20.iloc[-k]) for k in range(2, 7))
    surge = vol_avg > 0 and vol_now > 1.2 * vol_avg

    # —— 做多分 ——
    cl, long_s = [], 0
    def addl(label, ok, w):
        nonlocal long_s
        if ok: long_s += w
        cl.append([label, bool(ok)])
    addl("周线同向（高周期向上）", wk_up, 18)
    addl("趋势向上（价>20MA>50MA）", price > p20 > p50, 22)
    addl("近5日上穿20MA", cross_up, 12)
    addl("RSI 50–70（有动能不超买）", 50 <= rsi_v <= 70, 12)
    addl("放量（>1.2×20日均量）", surge, 8)
    addl("ADX≥20（有趋势）", adx_v >= 20, 8)
    addl("多头占优（+DI>−DI）", pdi_v > mdi_v, 8)
    addl("MACD 金叉（多头）", macd_v > sig_v, 12)
    if rsi_v > 75: long_s -= 12            # 超买追高扣分
    if wk_dn: long_s = int(long_s * 0.5)   # 高低周期方向冲突→砍半（冲突不顺势进场）
    long_s = max(0, min(100, long_s))

    # —— 做空分（镜像）——
    cs, short_s = [], 0
    def adds(label, ok, w):
        nonlocal short_s
        if ok: short_s += w
        cs.append([label, bool(ok)])
    adds("周线同向（高周期向下）", wk_dn, 18)
    adds("趋势向下（价<20MA<50MA）", price < p20 < p50, 22)
    adds("近5日下破20MA", cross_dn, 12)
    adds("RSI 30–50（弱动能未极端超卖）", 30 <= rsi_v <= 50, 12)
    adds("放量下跌（>1.2×20日均量）", surge, 8)
    adds("ADX≥20（有趋势）", adx_v >= 20, 8)
    adds("空头占优（−DI>+DI）", mdi_v > pdi_v, 8)
    adds("MACD 死叉（空头）", macd_v < sig_v, 12)
    if rsi_v < 25: short_s -= 12           # 超卖追空（反弹风险）扣分
    if wk_up: short_s = int(short_s * 0.5) # 高低周期方向冲突→砍半
    short_s = max(0, min(100, short_s))

    trend = "多头" if price > p20 > p50 else ("空头" if price < p20 < p50 else "纠缠")
    regime = "有趋势" if adx_v >= 25 else ("震荡" if adx_v < 20 else "趋势弱")
    wk_dir = "周线多头" if wk_up else ("周线空头" if wk_dn else "周线走平/无方向")
    # 有潜能 = 真的在走趋势：ADX≥20（有趋势强度）且 均线方向干净（不纠缠）。沉睡/震荡的过滤掉。
    alive = (adx_v >= 20) and (trend in ("多头", "空头"))
    risk_r = ATR_MULT * atr_v               # 一倍风险 = 止损距离
    units = (ACCOUNT * RISK_PCT / 100) / risk_r if risk_r > 0 else 0

    meta = dict(sym=sym, name=name, mkt=mk, price=price, chg=chg,
                long=long_s, short=short_s, cl=cl, cs=cs,
                trend=trend, regime=regime, adx=adx_v, wk=wk_dir, alive=bool(alive),
                di=("多占优" if pdi_v > mdi_v else "空占优"),
                rsi=rsi_v, atr=atr_v, r=risk_r, units=units, notional=units * price,
                oversold=rsi_v < 30, overbought=rsi_v > 70,
                bo_l=bool(bo_l), bo_s=bool(bo_s), h20=h20_v, l20=l20_v,
                ma20=p20, ma50=p50)   # 回踩入场检测用（entry_rules.check_pullback）

    # 日线图表数据
    series = build_series(df, intraday=False, bars=BARS_DAILY)
    return meta, series


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,Arial,sans-serif;background:#0a0e1a;color:#e8eaf0;padding:18px;max-width:1100px;margin:0 auto}
h1{font-size:21px}.sub{color:#7c879c;font-size:12px;margin-bottom:14px}
.rfx{font-size:13px;background:#1a73e8;border:none;color:#fff;padding:6px 13px;border-radius:8px;cursor:pointer;vertical-align:middle;margin-left:8px;min-height:34px}
.rfx:active{background:#1559b8}
.warn{background:#2a1f12;border:1px solid #5a3d1a;color:#e0b070;font-size:12px;padding:8px 12px;border-radius:8px;margin-bottom:16px}
h2{font-size:14px;color:#9b8cff;margin:22px 0 10px;border-bottom:1px solid #222b44;padding-bottom:6px}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.tab{background:#141c30;border:1px solid #283455;color:#aab2c5;font-size:13px;padding:6px 14px;border-radius:8px;cursor:pointer}
.tab.on{background:#1a73e8;border-color:#1a73e8;color:#fff;font-weight:700}
.dirtabs{display:flex;gap:6px;margin-bottom:10px}
.dirb{background:#141c30;border:1px solid #283455;color:#aab2c5;font-size:13px;padding:5px 16px;border-radius:8px;cursor:pointer}
.dirb.on[data-d="long"]{background:#155e3b;border-color:#1d7a4d;color:#fff;font-weight:700}
.dirb.on[data-d="short"]{background:#7a1d1d;border-color:#a33;color:#fff;font-weight:700}
.lvl{background:#0a1018;border-radius:8px;padding:10px;margin-top:8px;font-size:12.5px}
.lvl .lr{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px dashed #1a2236}
.lvl .lr:last-child{border-bottom:none}.lvl .lr b{font-weight:700}
.lvl .tp{color:#36d399}.lvl .sl{color:#f87272}.lvl .en{color:#e0b070}
.lvl .note{color:#6b768c;font-size:11px;margin-top:6px}
.flag{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:10px;margin-left:6px}
.flag.os{background:#3a2a12;color:#e0b070}.flag.ob{background:#7a1d1d;color:#ffb3b3}
.flag.bo{background:#102417;color:#6ee7a8;border:1px solid #1d3a2a}
.tfbar{display:flex;gap:5px;flex-wrap:wrap;align-items:center;margin:0 0 8px}
.tf{background:#141c30;border:1px solid #283455;color:#aab2c5;font-size:13px;padding:7px 13px;border-radius:7px;cursor:pointer;min-height:36px}
.tf.on{background:#1a73e8;border-color:#1a73e8;color:#fff;font-weight:700}
.tf.dis{opacity:.3;cursor:not-allowed}
.tfbar .lbl{color:#6b768c;font-size:11px;margin-right:2px}
.board{display:flex;flex-direction:column;gap:4px}
.row{display:grid;grid-template-columns:30px 1fr 96px 132px;align-items:center;gap:8px;background:#0e1422;border:1px solid #1f2940;border-radius:9px;padding:8px 11px;cursor:pointer}
.row:hover{border-color:#39476e}.row.sel{border-color:#1a73e8;background:#10203a}
.rk{font-size:14px;font-weight:700;color:#7c879c;text-align:center}
.nm b{font-size:14px}.nm i{display:block;font-style:normal;color:#7c879c;font-size:11px;margin-top:1px}
.pxc{text-align:right;font-size:13px;line-height:1.35}
.sc{display:flex;align-items:center;gap:7px;font-size:12px;color:#aab2c5;justify-content:flex-end}
.scbar{width:62px;height:7px;background:#1a2236;border-radius:4px;overflow:hidden}
.scbar>span{display:block;height:100%;background:linear-gradient(90deg,#36d399,#9b8cff)}
.up{color:#36d399}.down{color:#f87272}
.pick{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
.pick input{background:#0e1422;border:1px solid #283455;color:#e8eaf0;font-size:13px;padding:7px 11px;border-radius:8px;min-width:240px}
.pick .tg{background:#141c30;border:1px solid #283455;color:#aab2c5;font-size:12px;padding:6px 12px;border-radius:7px;cursor:pointer}
.pick .tg.off{opacity:.45;text-decoration:line-through}
#chart,#rsi{width:100%;border:1px solid #1f2940;border-radius:10px;background:#0e1422}
#rsi{margin-top:6px}
.detail{display:grid;grid-template-columns:1.1fr 1fr;gap:12px;margin-top:6px}
.panel{background:#0e1422;border:1px solid #1f2940;border-radius:12px;padding:14px}
.panel h3{font-size:15px;margin-bottom:2px}.panel .px{font-size:24px;font-weight:700;margin:2px 0 8px}
.kv{display:flex;justify-content:space-between;font-size:12px;padding:3px 0;color:#aab2c5}.kv b{color:#e8eaf0}
.pos{background:#0a1018;border-radius:8px;padding:9px;margin-top:8px;font-size:12px;color:#9b8cff}
.bdgs{display:flex;flex-direction:column;gap:5px}
.bdg{font-size:12px;padding:5px 9px;border-radius:7px;border:1px solid #1f2940}
.bdg.ok{background:#102417;border-color:#1d3a2a;color:#6ee7a8}
.bdg.no{background:#12161f;color:#5b657a}
.scbig{font-size:13px;color:#aab2c5;margin-bottom:8px}.scbig b{font-size:22px;color:#9b8cff}
.foot{color:#6b768c;font-size:11px;margin-top:22px;border-top:1px solid #1a2236;padding-top:10px}
@media(max-width:680px){
 body{padding:12px}h1{font-size:19px}
 .detail{grid-template-columns:1fr}
 .row{grid-template-columns:24px 1fr 84px;padding:9px 10px}.row .sc{display:none}
 .nm b{font-size:13px}.pxc{font-size:12px}
 .tab,.dirb,.tf,.tg{font-size:12px;padding:7px 11px;min-height:36px}
 .pick input{min-width:0;flex:1 1 100%}
 .lvl .lr{font-size:12px}
}
"""

APP_JS = """
const MK_NAMES={_hot:'🔥 全场潜力',us:'🇺🇸 美股',crypto:'₿ 加密',my:'🇲🇾 马股',macro:'🟡 商品/指数'};
const isM=window.innerWidth<560;const H=isM?330:400,RH=isM?105:130;
const opts={layout:{background:{type:'solid',color:'#0e1422'},textColor:'#9aa3b2',fontSize:11},
 grid:{vertLines:{color:'#16203a'},horzLines:{color:'#16203a'}},
 timeScale:{borderColor:'#2a3550',timeVisible:true,secondsVisible:false},
 rightPriceScale:{borderColor:'#2a3550'},crosshair:{mode:0},
 handleScroll:true,handleScale:true};
const cEl=document.getElementById('chart'),rEl=document.getElementById('rsi');
const chart=LightweightCharts.createChart(cEl,Object.assign({},opts,{height:H}));
const rchart=LightweightCharts.createChart(rEl,Object.assign({},opts,{height:RH}));
const candle=chart.addCandlestickSeries({upColor:'#36d399',downColor:'#f87272',wickUpColor:'#36d399',wickDownColor:'#f87272',borderVisible:false});
const vol=chart.addHistogramSeries({priceScaleId:'vol',priceFormat:{type:'volume'}});
chart.priceScale('vol').applyOptions({scaleMargins:{top:0.82,bottom:0}});
const ma20=chart.addLineSeries({color:'#e67e00',lineWidth:1,priceLineVisible:false,lastValueVisible:false});
const ma50=chart.addLineSeries({color:'#2e7d32',lineWidth:1,priceLineVisible:false,lastValueVisible:false});
const rsiS=rchart.addLineSeries({color:'#9b8cff',lineWidth:1,priceLineVisible:false});
rsiS.createPriceLine({price:70,color:'#c0392b',lineStyle:2,lineWidth:1,axisLabelVisible:true});
rsiS.createPriceLine({price:30,color:'#2e7d32',lineStyle:2,lineWidth:1,axisLabelVisible:true});
function lineprices(){const m=META[cur];if(!m||!showLv)return [];const r=m.r,p=m.price;
 return dir==='long'?[p,p-r,p+r]:[p,p+r,p-r];}   // 入场/止损/TP1 保证在缩放范围内
candle.applyOptions({autoscaleInfoProvider:orig=>{const res=orig();if(!res)return res;
 const ps=lineprices();if(!ps.length)return res;let mn=res.priceRange.minValue,mx=res.priceRange.maxValue;
 ps.forEach(v=>{mn=Math.min(mn,v);mx=Math.max(mx,v);});
 return{priceRange:{minValue:mn,maxValue:mx},margins:res.margins};}});

const TF_ORDER=['1m','5m','15m','1h','4h','1d'];
const TF_LABELS={'1m':'1分','5m':'5分','15m':'15分','1h':'1时','4h':'4时','1d':'日线'};
let market='_hot',dir='long',cur=null,tf='1d',show20=true,show50=true,showLv=true;
let priceLines=[];
const _cache={};
function build(s,t){const k=s+'|'+t;if(_cache[k])return _cache[k];const d=DATA[s][t];
 const cd=[],vo=[],m20=[],m50=[],rs=[];
 for(let i=0;i<d.t.length;i++){const x=d.t[i];
  cd.push({time:x,open:d.o[i],high:d.h[i],low:d.l[i],close:d.c[i]});
  vo.push({time:x,value:d.v[i],color:d.c[i]>=d.o[i]?'rgba(54,211,153,.45)':'rgba(248,114,114,.45)'});
  if(d.s20[i]!=null)m20.push({time:x,value:d.s20[i]});
  if(d.s50[i]!=null)m50.push({time:x,value:d.s50[i]});
  if(d.rsi[i]!=null)rs.push({time:x,value:d.rsi[i]});}
 return _cache[k]={candles:cd,volume:vo,sma20:m20,sma50:m50,rsi:rs};}
function fmtPx(v){if(v==null)return '-';return v>=1000?v.toLocaleString(undefined,{maximumFractionDigits:2}):(v>=1?v.toFixed(2):v.toFixed(4));}
function chgHtml(x){const s=x>=0?'+':'';return '<span class="'+(x>=0?'up':'down')+'">'+s+x.toFixed(2)+'%</span>';}
function boardSyms(){return (MARKETS[market]||[]).slice().sort((a,b)=>META[b][dir]-META[a][dir]).slice(0,10);}

function renderTabs(){let h='';for(const k of ORDER){h+='<div class="tab'+(k===market?' on':'')+'" data-k="'+k+'">'+MK_NAMES[k]+'</div>';}
 document.getElementById('tabs').innerHTML=h;
 document.querySelectorAll('#tabs .tab').forEach(t=>t.onclick=()=>{market=t.dataset.k;renderTabs();renderBoard();});}
function renderBoard(){const syms=boardSyms();let h='';
 syms.forEach((s,i)=>{const m=META[s];if(!m)return;const sc=m[dir];
  const bo=dir==='long'?m.bo_l:m.bo_s;   // 🎯今日刚突破前20日高/低（与盯盘员进场引擎同一检测）
  h+='<div class="row'+(s===cur?' sel':'')+'" data-s="'+s+'">'
   +'<span class="rk">'+(i+1)+'</span>'
   +'<span class="nm"><b>'+s+(bo?' 🎯':'')+'</b><i>'+m.name+'</i></span>'
   +'<span class="pxc">'+fmtPx(m.price)+'<br>'+chgHtml(m.chg)+'</span>'
   +'<span class="sc"><span class="scbar"><span style="width:'+sc+'%"></span></span>'+sc+'</span>'
   +'</div>';});
 document.getElementById('board').innerHTML=h||'<div style="color:#7c879c;padding:10px">无数据</div>';
 document.querySelectorAll('#board .row').forEach(r=>r.onclick=()=>select(r.dataset.s));}
function drawLines(){priceLines.forEach(p=>{try{candle.removePriceLine(p);}catch(e){}});priceLines=[];
 if(!showLv)return;const m=META[cur];if(!m)return;const r=m.r,p=m.price;let sl,tps,et;
 if(dir==='long'){sl=p-r;tps=[p+r,p+2*r,p+3*r];et='BUY 入场';}
 else{sl=p+r;tps=[p-r,p-2*r,p-3*r];et='SELL 入场';}
 priceLines.push(candle.createPriceLine({price:p,color:'#e0b070',lineWidth:2,lineStyle:0,axisLabelVisible:true,title:et}));
 priceLines.push(candle.createPriceLine({price:sl,color:'#f87272',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'SL 止损'}));
 ['TP1','TP2','TP3'].forEach((t,i)=>priceLines.push(candle.createPriceLine({price:tps[i],color:'#36d399',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:t})));
 const bl=dir==='long'?m.h20:m.l20;   // 进场引擎盯的那道坎：前20日高(做多)/低(做空)
 if(bl!=null)priceLines.push(candle.createPriceLine({price:bl,color:'#9bb3ff',lineWidth:1,lineStyle:3,axisLabelVisible:true,title:dir==='long'?'20日高':'20日低'}));}
function drawChart(){const d=build(cur,tf);
 candle.setData(d.candles);vol.setData(d.volume);
 ma20.setData(show20?d.sma20:[]);ma50.setData(show50?d.sma50:[]);rsiS.setData(d.rsi);
 chart.timeScale().fitContent();rchart.timeScale().fitContent();drawLines();}
function renderTFs(){const avail=DATA[cur]||{};let h='<span class="lbl">周期</span>';
 TF_ORDER.forEach(k=>{const ok=!!avail[k],on=k===tf;
  h+='<button class="tf'+(on?' on':'')+(ok?'':' dis')+'" data-tf="'+k+'"'+(ok?'':' disabled')+'>'+TF_LABELS[k]+'</button>';});
 document.getElementById('tfbar').innerHTML=h;
 document.querySelectorAll('#tfbar .tf:not(.dis)').forEach(b=>b.onclick=()=>{tf=b.dataset.tf;renderTFs();drawChart();});}
function select(s){if(!DATA[s])return;cur=s;if(!DATA[s][tf])tf='1d';
 renderTFs();
 candle.setData([]);vol.setData([]);ma20.setData([]);ma50.setData([]);rsiS.setData([]);
 drawChart();
 document.querySelectorAll('#board .row').forEach(r=>r.classList.toggle('sel',r.dataset.s===cur));
 document.getElementById('pick').value=s;renderDetail();}
function renderDetail(){const m=META[cur];if(!m)return;
 const tcls=m.trend==='多头'?'up':(m.trend==='空头'?'down':'');
 const comps=dir==='long'?m.cl:m.cs;
 let bd='';comps.forEach(c=>{bd+='<div class="bdg '+(c[1]?'ok':'no')+'">'+(c[1]?'✓ ':'· ')+c[0]+'</div>';});
 // 交易参考价位（机械 ATR 风险倍数法）
 const r=m.r,p=m.price;let stop,tp,dname,dcls;
 if(dir==='long'){stop=p-r;tp=[p+r,p+2*r,p+3*r];dname='做多 Long';dcls='up';}
 else{stop=p+r;tp=[p-r,p-2*r,p-3*r];dname='做空 Short';dcls='down';}
 let warn='';
 if(dir==='long'&&m.overbought)warn='<div class="note">⚠ RSI 已超买，现价追多风险高，等回踩更稳。</div>';
 if(dir==='short'&&m.oversold)warn='<div class="note">⚠ RSI 已超卖，现价追空易被反弹打，等反抽到阻力更稳。</div>';
 const lvl='<div class="lvl">'
   +'<div class="lr"><span>方向</span><b class="'+dcls+'">'+dname+'</b></div>'
   +'<div class="lr en"><span>参考入场</span><b>'+fmtPx(p)+'</b></div>'
   +'<div class="lr sl"><span>止损（'+ATRM+'×ATR）</span><b>'+fmtPx(stop)+'　（R='+fmtPx(r)+'）</b></div>'
   +'<div class="lr tp"><span>TP1（1R · 盈亏1:1）</span><b>'+fmtPx(tp[0])+'</b></div>'
   +'<div class="lr tp"><span>TP2（2R · 盈亏1:2）</span><b>'+fmtPx(tp[1])+'</b></div>'
   +'<div class="lr tp"><span>TP3（3R · 盈亏1:3）</span><b>'+fmtPx(tp[2])+'</b></div>'
   +warn+'<div class="note">机械参考价位（入场≈现价，止损='+ATRM+'×ATR，TP=1/2/3倍风险）。<b>不是预测、不是买卖信号</b>。回踩/反抽入场比追价更稳。</div></div>';
 let flag='';
 if(dir==='long'&&m.bo_l)flag+='<span class="flag bo">🎯 今日突破20日高</span>';
 if(dir==='short'&&m.bo_s)flag+='<span class="flag bo">🎯 今日跌破20日低</span>';
 if(m.oversold)flag+='<span class="flag os">超卖 RSI<30</span>';
 else if(m.overbought)flag+='<span class="flag ob">超买 RSI>70</span>';
 document.getElementById('detail').innerHTML=
  '<div class="panel"><h3>'+m.sym+' · '+m.name+flag+'</h3>'
   +'<div class="px '+tcls+'">'+fmtPx(m.price)+' <span style="font-size:14px">'+chgHtml(m.chg)+'</span></div>'
   +'<div class="kv"><span>趋势</span><b class="'+tcls+'">'+m.trend+'</b></div>'
   +'<div class="kv"><span>ADX</span><b>'+m.adx.toFixed(0)+'（'+m.regime+'）· '+m.di+'</b></div>'
   +'<div class="kv"><span>周线（高周期）</span><b class="'+(m.wk==='周线多头'?'up':(m.wk==='周线空头'?'down':''))+'">'+m.wk+'</b></div>'
   +'<div class="kv"><span>RSI(14)</span><b>'+m.rsi.toFixed(0)+'</b></div>'
   +'<div class="kv"><span>ATR(14)</span><b>'+fmtPx(m.atr)+'</b></div>'
   +'<div class="pos">仓位（<b>示例参数</b> 账户$'+ACCT.toLocaleString()+' / 单笔险'+RISKP+'% / 止损'+ATRM+'×ATR）：'
     +'最大 '+m.units.toFixed(4)+' 单位 ≈ $'+Math.round(m.notional).toLocaleString()
     +'<br><span style="color:#e0b070">⚠ 这是公开页的演示数；真实下单数量以 Telegram 推送为准</span></div></div>'
  +'<div class="panel"><div class="scbig">'+(dir==='long'?'做多':'做空')+'信号分 <b>'+m[dir]+'</b> / 100</div>'
   +'<div class="bdgs">'+bd+'</div>'+lvl+'</div>';}

document.querySelectorAll('.dirb').forEach(b=>b.onclick=()=>{dir=b.dataset.d;
 document.querySelectorAll('.dirb').forEach(x=>x.classList.toggle('on',x.dataset.d===dir));
 renderBoard();if(cur){renderDetail();drawLines();}});
document.getElementById('pick').addEventListener('change',function(){const v=this.value.trim().toUpperCase();
 if(META[v]){market=META[v].mkt;renderTabs();renderBoard();select(v);}});
document.getElementById('t20').onclick=function(){show20=!show20;this.classList.toggle('off');if(cur){const d=build(cur,tf);ma20.setData(show20?d.sma20:[]);}};
document.getElementById('t50').onclick=function(){show50=!show50;this.classList.toggle('off');if(cur){const d=build(cur,tf);ma50.setData(show50?d.sma50:[]);}};
document.getElementById('tlv').onclick=function(){showLv=!showLv;this.classList.toggle('off');drawLines();};
function sync(a,b){a.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)try{b.timeScale().setVisibleLogicalRange(r);}catch(e){}});}
sync(chart,rchart);sync(rchart,chart);
new ResizeObserver(()=>{chart.applyOptions({width:cEl.clientWidth});rchart.applyOptions({width:rEl.clientWidth});}).observe(cEl);

renderTabs();renderBoard();
// 深链接：Telegram 消息里的「📊 仪表盘看图」带 #s=代码(&d=long/short) → 打开直接选中该标的并切到对应做多/做空视角
let deep=null,deepDir=null;
try{const hm=location.hash.match(/^#s=([^&]+)(?:&d=(long|short))?$/);if(hm){deep=decodeURIComponent(hm[1]).toUpperCase();deepDir=hm[2]||null;}}catch(e){}
if(deep&&META[deep]){
 if(deepDir){dir=deepDir;document.querySelectorAll('.dirb').forEach(x=>x.classList.toggle('on',x.dataset.d===dir));}
 market=META[deep].mkt;renderTabs();renderBoard();select(deep);}
else select(boardSyms()[0]);
"""


def main():
    today = dt.date.today().isoformat()
    # 生成时间（马来西亚 MYT = UTC+8），让网页显示"数据更新于何时"
    myt = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=8)
    gen = myt.strftime("%Y-%m-%d %H:%M")
    meta_all, data_all, markets = {}, {}, {}
    ok, fail = 0, 0
    for sym, name, mk in U.all_items():
        res = process(sym, name, mk)
        if not res:
            fail += 1
            print(f"  跳过(无数据): {sym}")
            continue
        meta, series = res
        meta_all[sym] = meta
        data_all[sym] = {"1d": series}
        if sym in U.FOCUS:                       # 重点标的：加烤盘中全周期
            tfs = intraday_frames(sym)
            data_all[sym].update(tfs)
            print(f"  ★ 盘中: {sym} → {'/'.join(tfs.keys()) or '无'}")
        markets.setdefault(mk, []).append(sym)
        ok += 1
    # 只让"有潜能/在走趋势"的标的进榜；沉睡/震荡的过滤掉（仍可在搜索框查看其图表）。
    # 默认按做多分排（前端切做空时会按做空分重排）。
    sleeping = 0
    for mk in markets:
        alive_syms = [s for s in markets[mk] if meta_all[s].get("alive")]
        sleeping += len(markets[mk]) - len(alive_syms)
        alive_syms.sort(key=lambda s: meta_all[s]["long"], reverse=True)
        markets[mk] = alive_syms
    # 🔥 全场潜力：跨所有市场，把趋势最强的挑出来（按 做多/做空 取较高分），最多15只
    hot = sorted((s for s in meta_all if meta_all[s].get("alive")),
                 key=lambda s: max(meta_all[s]["long"], meta_all[s]["short"]), reverse=True)[:15]
    markets["_hot"] = hot
    alive_total = len(hot)
    order = ["_hot"] + [mk for mk in U.ORDER if markets.get(mk)]
    print(f"  趋势过滤: 活跃 {sum(1 for s in meta_all if meta_all[s].get('alive'))} 只 / 沉睡过滤 {sleeping} 只")

    # 搜索框 datalist（全部标的）
    opts_html = "".join(
        f'<option value="{s}">{meta_all[s]["name"]}</option>' for s in meta_all)

    libpath = os.path.join(HERE, "lightweight-charts.js")
    lib = open(libpath, encoding="utf-8").read() if os.path.exists(libpath) else ""

    consts = (f"const META={json.dumps(meta_all, ensure_ascii=False)};"
              f"const DATA={json.dumps(data_all)};"
              f"const MARKETS={json.dumps(markets)};"
              f"const ORDER={json.dumps(order)};"
              f"const ACCT={ACCOUNT},RISKP={RISK_PCT},ATRM={ATR_MULT};")

    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sen 市场仪表盘 — {today}</title><style>{CSS}</style></head><body>
<h1>📊 Sen 市场仪表盘 <button class="rfx" onclick="location.reload()">🔄 刷新</button></h1>
<div class="sub">🕒 数据更新 <b style="color:#9bb3ff">{gen} MYT</b> · 每约30分钟自动刷新，点 🔄 看最新 · 扫 {ok} 个标的 · <b style="color:#ffce6b">活跃 {alive_total} 只在走趋势</b>，沉睡/震荡 {sleeping} 只已过滤 · 数据 yfinance</div>
<div class="warn">⚠ 信号分只是<b>透明的筛子</b>（<b>周线高周期定向</b> + 日线趋势/动能/量/ADX/MACD 逐条打分；高低周期方向冲突自动砍半）；入场/TP 价位是<b>机械的 ATR 风险倍数</b>，<b>都不是买卖信号、不是预测、不是理财建议</b>。历史≠未来；要动手先 Paper 验证、控仓位、只用亏得起的钱。</div>

<h2>🏆 信号榜 Top 10（点一行看它的图 + 价位）</h2>
<div style="color:#6b768c;font-size:11px;margin:-4px 0 8px">🔥 <b>全场潜力</b>=跨所有市场挑趋势最强的；其余分市场看。只列<b>在走趋势</b>的（ADX≥20 且均线方向干净），<b>不动的、震荡绞肉的已自动过滤</b>（仍可在下方搜索框查看任意代码）。</div>
<div class="tabs" id="tabs"></div>
<div class="dirtabs">
 <button class="dirb on" data-d="long">📈 做多榜</button>
 <button class="dirb" data-d="short">📉 做空榜</button>
</div>
<div class="board" id="board"></div>

<h2>📈 蜡烛图（搜任意标的 / 切周期 / 买卖线）</h2>
<div class="pick">
 <input id="pick" list="alltk" placeholder="输入代码或点上面榜单，如 AAPL / BTC-USD / 1155.KL">
 <datalist id="alltk">{opts_html}</datalist>
 <button class="tg" id="t20">SMA20</button><button class="tg" id="t50">SMA50</button>
 <button class="tg" id="tlv">买卖线</button>
</div>
<div class="tfbar" id="tfbar"></div>
<div id="chart"></div><div id="rsi"></div>
<div style="color:#6b768c;font-size:11px;margin-top:5px">⏱ 分钟/小时周期只对 <b>重点盯盘标的</b>（黄金/白银/油/BTC/ETH/标普/纳指/QQQ/NVDA/KLCI/马银行/大众）可用；其余只有日线。黄/红/绿横线=入场/止损/止盈，跟"做多·做空"方向走。</div>

<h2>🔬 选中标的详情 + 评分明细 + 仓位</h2>
<div class="detail" id="detail"></div>

<div class="foot">由 dashboard.py 生成 · 改标的清单=编辑 universe.py · 刷新数据=重跑脚本(或双击 刷新仪表盘.bat) · 历史≠未来</div>

<script>{lib}</script>
<script>{consts}</script>
<script>{APP_JS}</script>
</body></html>"""

    with open(os.path.join(HERE, "dashboard.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"仪表盘已生成: dashboard.html （成功 {ok} 个标的，跳过 {fail} 个）")


if __name__ == "__main__":
    main()
