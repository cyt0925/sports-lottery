# 今日運彩總覽

一頁看完今日賽事、盤口、傷兵、火燙／冰冷球員、球隊近況、相關新聞與規則式建議。
純靜態網站，零主機費用，資料由 GitHub Actions 每小時自動更新。

## 架構

```
.（repo 根目錄）
├── index.html / style.css / app.js   網頁（讀 data/today.json）
├── data/today.json                   排程產生的資料（自動 commit）
├── data/sample.json                  本機測試用的範例資料
└── pipeline/
    ├── fetch.py                      抓資料 + 規則式建議
    ├── taiwan_odds.py                玩運彩盤口頁解析與配對
    ├── playsport.py                  歐籃、日籃：以玩運彩為主幹的賽事與球隊歷史戰績
    ├── euroleague.py / bleague.py    EuroLeague 官方 API、B.LEAGUE 排名頁
    ├── svleague.py                   SV.LEAGUE 日本排球
    ├── newsinj.py                    Google 新聞傷兵
    ├── elreport.py                   歐籃傷兵報告文章（解 Google 轉址、抓內文）
    ├── players.py                    球員層級：缺陣影響幾分、主力名單
    ├── story.py                      白話分析段落
    ├── names_zh.py                   球隊中文名、狀態中文
    ├── probe_playsport.py            探路用（印網頁結構到 log，平常不跑）
    └── make_sample.py                產生範例資料
.github/workflows/sports-data.yml     每小時排程
```

## 資料來源（全部免費、不用 key）

| 球種 | 賽程、比分、盤口 | 隊徽、排名、近況 | 傷兵 |
|---|---|---|---|
| NBA | ESPN 公開接口＋玩運彩台灣盤 | ESPN（含球員近 5 場火燙／冰冷） | ESPN 傷兵名單 |
| 歐洲籃球（歐冠、歐盃、其他歐洲賽事） | 玩運彩 allianceid 8（台灣盤、國際盤、玩家預測比例） | EuroLeague 官方 API（隊徽、排名、主客分明的賽果、球員場均）；對不上的球隊用玩運彩的歷史戰績 | Google 新聞（英文）＋每輪的傷兵報告文章，用官方球員名單對出誰缺陣、少他差幾分 |
| 日本籃球（B.LEAGUE） | 玩運彩 allianceid 97 | B.LEAGUE 官網排名頁（東西區、主客戰績、近 5 場）、球隊頁的球員平均 | Google 新聞（日文），用官網名單對出缺陣的人、少他差幾分 |
| 日本排球（SV.LEAGUE） | SV.LEAGUE 官網（沒有盤口，勝率依近況粗估） | 官網賽果自己算的排名、球隊選手頁名單 | Google 新聞（日文），對到就標缺陣（隊長、主攻、接應、舉球算主力） |
| 足球、冰球、美足（收在「更多球種」） | ESPN＋玩運彩 | ESPN | ESPN |

沒有官方傷兵名單的聯盟，傷兵區會寫清楚「新聞裡有沒有提到」，不會留白；傷兵快報也會把這些新聞列進去。NBA 的傷兵會查本季（沒有就上季）場均得分與上場時間，換算成大概差幾分讓分；歐籃則從每輪的傷兵報告文章對球員全名。
國際盤是美國莊家的參考值；台灣盤來自玩運彩，抓不到時卡片就不顯示那一塊，不影響其他功能。

## 本機測試

```bash
python3 pipeline/make_sample.py          # 產生 data/sample.json
cd sports && python3 -m http.server 8080        # 開 http://localhost:8080/?data=sample
python3 pipeline/fetch.py                # 真實抓一次（需要能連 ESPN、玩運彩等）
python3 pipeline/fetch.py --leagues eurobasket,jpvolley   # 只抓某幾個聯盟
```

## 建議怎麼算（規則式，不是 AI 預測）

1. 以美國莊家賠率去掉抽水後的勝率為基準。
2. 看好的一方若有主力缺陣（球隊得分／籃板／助攻王在缺陣名單）扣分；對手主力缺陣加分。
3. 近 10 場勝率 7 成以上加分、3 成以下扣分；對手 3 連勝以上扣分。
4. 主力近 5 場比季平均高 15% 以上算「火燙」加分，低 15% 以上算「冰冷」扣分。
5. 調整後勝率達門檻才給「傾向」，否則寫「觀望」。
6. 大小分：兩隊近 5 場平均總分與盤口差距超過門檻才給方向。

免責：這只是整理資料的工具，不保證任何結果。
