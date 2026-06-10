# universe.py — 各市场标的清单（代码 + 显示名）。dashboard.py 会扫这些算信号榜+烤图。
# 想加/减股票：直接改下面的列表即可，重跑 dashboard.py 就生效。
# 马股用 Bursa 代码 + ".KL"；加密用 "<币>-USD"；指数用 "^..."；商品用 "GC=F" 这类。

MARKETS = {
    "us": ("🇺🇸 美股", [
        ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "Nvidia"), ("AMZN", "Amazon"),
        ("GOOGL", "Alphabet"), ("META", "Meta"), ("TSLA", "Tesla"), ("AVGO", "Broadcom"),
        ("AMD", "AMD"), ("NFLX", "Netflix"), ("ADBE", "Adobe"), ("CRM", "Salesforce"),
        ("ORCL", "Oracle"), ("JPM", "JPMorgan"), ("V", "Visa"), ("MA", "Mastercard"),
        ("BAC", "Bank of America"), ("COST", "Costco"), ("WMT", "Walmart"), ("HD", "Home Depot"),
        ("XOM", "Exxon"), ("CVX", "Chevron"), ("UNH", "UnitedHealth"), ("LLY", "Eli Lilly"),
        ("JNJ", "J&J"), ("PG", "P&G"), ("KO", "Coca-Cola"), ("DIS", "Disney"),
        ("QQQ", "Nasdaq100 ETF"), ("SPY", "S&P500 ETF"), ("VOO", "Vanguard S&P"), ("SMH", "Semis ETF"),
    ]),
    "crypto": ("₿ 加密", [
        ("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"), ("SOL-USD", "Solana"),
        ("BNB-USD", "BNB"), ("XRP-USD", "XRP"), ("ADA-USD", "Cardano"),
        ("DOGE-USD", "Dogecoin"), ("AVAX-USD", "Avalanche"), ("LINK-USD", "Chainlink"),
        ("DOT-USD", "Polkadot"), ("LTC-USD", "Litecoin"), ("BCH-USD", "Bitcoin Cash"),
        ("ATOM-USD", "Cosmos"), ("UNI-USD", "Uniswap"),
    ]),
    "my": ("🇲🇾 马股", [
        ("1155.KL", "Maybank 马银行"), ("1295.KL", "Public Bank 大众"), ("1023.KL", "CIMB 联昌"),
        ("5819.KL", "Hong Leong Bank 丰隆银行"), ("1066.KL", "RHB Bank 兴业"), ("1015.KL", "AMMB 大马银行"),
        ("5347.KL", "Tenaga 国能"), ("5183.KL", "Petronas Chem 国油化学"), ("6033.KL", "Petronas Gas 国油气体"),
        ("5681.KL", "Petronas Dagangan 国油贸易"), ("3816.KL", "MISC"), ("7277.KL", "Dialog 戴乐"),
        ("6742.KL", "YTL Power 杨忠礼电力"), ("4677.KL", "YTL Corp 杨忠礼"), ("6888.KL", "Axiata"),
        ("6012.KL", "Maxis"), ("4863.KL", "TM 电讯"), ("6947.KL", "CelcomDigi"),
        ("5225.KL", "IHH Healthcare"), ("2445.KL", "KLK 吉隆坡甲洞"), ("1961.KL", "IOI Corp"),
        ("5285.KL", "SD Guthrie"), ("4197.KL", "Sime Darby 森那美"), ("3182.KL", "Genting 云顶"),
        ("4715.KL", "Genting Malaysia 云顶大马"), ("7113.KL", "Top Glove 顶级手套"), ("5168.KL", "Hartalega"),
        ("0166.KL", "Inari 怡纳利"), ("5296.KL", "MR DIY"), ("5099.KL", "Capital A 亚航"),
        ("8869.KL", "Press Metal 齐力工业"), ("5398.KL", "Gamuda 金务大"), ("1818.KL", "Bursa 大马交易所"),
        # —— 中小盘 / 热门散户票 ——
        ("5014.KL", "MAHB 大马机场"), ("5246.KL", "Westports 西港"), ("3034.KL", "Hap Seng 合成"),
        ("4707.KL", "Nestle 雀巢"), ("4065.KL", "PPB Group"), ("3689.KL", "F&N"),
        ("7084.KL", "QL Resources"), ("6599.KL", "AEON 永旺"), ("7052.KL", "Padini"),
        ("2836.KL", "Carlsberg"), ("3255.KL", "Heineken"), ("0138.KL", "MyEG"),
        ("6399.KL", "Astro"), ("7106.KL", "Supermax 速柏玛"), ("7153.KL", "Kossan 高产柅品"),
        ("3867.KL", "MPI 太平洋科技"), ("5005.KL", "Unisem"), ("0128.KL", "Frontken"),
        ("8664.KL", "SP Setia"), ("8583.KL", "Mah Sing 马星"), ("5211.KL", "Sunway 双威"),
        ("5263.KL", "SunCon 双威建筑"), ("3336.KL", "IJM Corp"), ("2488.KL", "Alliance Bank 安联银行"),
        ("5185.KL", "Affin Bank 艾芬银行"), ("2291.KL", "Genting Plant 云顶种植"), ("7293.KL", "Yinson"),
        ("5199.KL", "Hibiscus 大红花石油"), ("5210.KL", "Bumi Armada"),
    ]),
    "macro": ("🟡 商品/指数", [
        ("GC=F", "黄金 Gold"), ("SI=F", "白银 Silver"), ("CL=F", "原油 Crude Oil"),
        ("^GSPC", "标普500 S&P500"), ("^IXIC", "纳指综合 Nasdaq"), ("^DJI", "道指 Dow"),
        ("^KLSE", "马股综指 KLCI"), ("^HSI", "恒生 Hang Seng"),
    ]),
}

# 板块顺序（决定网页标签顺序）
ORDER = ["us", "crypto", "my", "macro"]

# 重点盯盘清单：只给这几只烤"分钟/小时全周期"(1m/5m/15m/1h/4h)。
# 其余标的盘中数据太大、Yahoo会限流，只保留日线。想加重点标的就改这里。
FOCUS = [
    "GC=F", "SI=F", "CL=F",                 # 黄金 白银 原油
    "BTC-USD", "ETH-USD",                   # 加密
    "^GSPC", "^IXIC", "QQQ", "NVDA",        # 美股/指数
    "^KLSE", "1155.KL", "1295.KL",          # 马股综指 + 马银行 大众
]


def all_items():
    """[(symbol, name, market_key), ...] 全部标的。"""
    out = []
    for mk in ORDER:
        for sym, name in MARKETS[mk][1]:
            out.append((sym, name, mk))
    return out
