# -*- coding: utf-8 -*-
"""歐洲國內籃球聯賽的球隊：英文隊名裡的關鍵字 -> 中文名、查新聞用的名字。

中文名盡量照台灣運彩的叫法（巴斯干尼亞、加那利1939、考納斯綠林…），找不到的就顯示英文原名。
同一個關鍵字也拿來把國內聯賽的球隊跟歐冠、歐盃官方資料的球隊對起來（同一支球隊兩邊的賽程合在一起算休息天數）。
關鍵字比對前會先去掉重音、轉小寫；越長、越特別的關鍵字放越前面。"""
import re
import unicodedata

# (關鍵字們, 中文名, 查新聞用的名字)
TEAMS = [
    # 西班牙 ACB
    (("real madrid",), "皇家馬德里", "Real Madrid baloncesto"),
    (("barcelona", "barca"), "巴塞隆納", "Barça basket"),
    (("baskonia", "saski"), "巴斯干尼亞", "Baskonia"),
    (("valencia",), "瓦倫西亞", "Valencia Basket"),
    (("1939 canarias", "tenerife", "la laguna"), "加那利1939", "La Laguna Tenerife basket"),
    (("gran canaria",), "格蘭卡納利亞", "Gran Canaria baloncesto"),
    (("joventut", "badalona"), "尤文圖特", "Joventut Badalona"),
    (("unicaja", "malaga"), "馬拉加", "Unicaja Malaga"),
    (("manresa",), "曼雷薩", "Baxi Manresa"),
    (("breogan",), "布雷奧甘", "Rio Breogan"),
    (("lleida",), "萊里達", "Hiopos Lleida"),
    (("burgos",), "布爾戈斯", "San Pablo Burgos"),
    (("coruna",), "拉科魯尼亞", "Basquet Coruña"),
    (("bilbao",), "畢爾包", "Bilbao Basket"),
    (("obradoiro",), "奧布拉多伊羅", "Obradoiro"),
    (("zaragoza",), "薩拉戈薩", "Basket Zaragoza"),
    (("girona",), "赫羅納", "Basquet Girona"),
    (("murcia",), "莫夕亞", "UCAM Murcia"),
    (("andorra",), "安道爾", "MoraBanc Andorra"),
    (("granada",), "格拉納達", "Covirán Granada"),
    (("palma",), "帕爾馬", "Palmer Basket Palma"),
    (("estudiantes",), "埃斯圖迪安特斯", "Movistar Estudiantes"),
    # 義大利 LBA
    (("olimpia milano", "milano", "milan"), "米蘭", "Olimpia Milano"),
    (("virtus",), "波隆那", "Virtus Bologna"),
    (("fortitudo",), "波隆那堡壘", "Fortitudo Bologna"),
    (("venezia", "reyer", "venice"), "威尼斯", "Reyer Venezia"),
    (("sassari", "dinamo"), "薩薩里", "Dinamo Sassari"),
    (("trieste",), "的里雅斯特", "Pallacanestro Trieste"),
    (("cantu",), "坎圖", "Pallacanestro Cantù"),
    (("reggiana", "reggio emilia"), "雷焦艾米利亞", "Pallacanestro Reggiana"),
    (("verona", "scaligera"), "維洛納", "Scaligera Verona"),
    (("scafati",), "斯卡法蒂", "Givova Scafati"),
    (("derthona", "tortona"), "托爾托納", "Derthona Tortona"),
    (("trento", "aquila"), "特倫托", "Aquila Trento"),
    (("brescia",), "布雷西亞", "Germani Brescia"),
    (("napoli",), "拿坡里", "Napoli Basket"),
    (("varese",), "瓦雷澤", "Pallacanestro Varese"),
    (("pistoia",), "皮斯托亞", "Pistoia Basket"),
    (("treviso",), "特雷維索", "Treviso Basket"),
    (("trapani",), "特拉帕尼", "Trapani Shark"),
    (("cremona",), "克雷莫納", "Vanoli Cremona"),
    (("udine",), "烏迪內", "Apu Udine"),
    (("roma",), "羅馬", "Roma basket"),
    (("pesaro",), "佩薩羅", "Victoria Libertas Pesaro"),
    # 土耳其 BSL
    (("fenerbahce",), "費內巴切", "Fenerbahce Beko"),
    (("efes",), "艾菲斯", "Anadolu Efes"),
    (("galatasaray",), "加拉塔薩雷", "Galatasaray basketball"),
    (("besiktas",), "貝西克塔斯", "Besiktas basketball"),
    (("turk telekom",), "土耳其電信", "Turk Telekom basketball"),
    (("tofas",), "托法什", "Tofas Bursa"),
    (("bahcesehir",), "花園城市學院", "Bahcesehir Koleji"),
    (("karsiyaka",), "卡爾希亞卡", "Karsiyaka basketball"),
    (("darussafaka",), "達魯沙法卡", "Darussafaka basketball"),
    (("bursaspor",), "布爾薩體育", "Bursaspor basketball"),
    (("petkim", "aliaga"), "佩特金體育", "Aliaga Petkimspor"),
    (("manisa",), "馬尼薩", "Manisa basketball"),
    (("merkezefendi",), "梅爾克澤芬迪", "Merkezefendi basketball"),
    (("buyukcekmece",), "布于克切克梅杰", "Buyukcekmece basketball"),
    (("trabzon",), "特拉布宗", "Trabzonspor basketball"),
    (("esenler", "erokspor"), "埃森勒", "Esenler Erokspor"),
    (("mersin",), "梅爾辛", "Mersin basketball"),
    (("gaziantep",), "加濟安泰普", "Gaziantep basketball"),
    (("yalova",), "亞洛瓦", "Yalovaspor basketball"),
    (("konya",), "科尼亞", "Konyaspor basketball"),
    # 希臘
    (("olympiacos", "olympiakos"), "奧林匹亞科斯", "Olympiacos BC"),
    (("panathinaikos",), "帕納辛奈科斯", "Panathinaikos BC"),
    (("aek",), "雅典AEK", "AEK Athens basketball"),
    (("paok",), "PAOK", "PAOK basketball"),
    (("aris",), "阿里斯", "Aris Thessaloniki basketball"),
    (("peristeri",), "佩里斯特里", "Peristeri basketball"),
    (("promitheas",), "普羅米修斯", "Promitheas Patras"),
    (("kolossos", "rhodes"), "羅德島", "Kolossos Rodou"),
    (("lavrio",), "拉夫里奧", "Lavrio basketball"),
    (("maroussi",), "馬魯西", "Maroussi basketball"),
    (("karditsa",), "卡迪察", "Karditsa basketball"),
    (("iraklis",), "伊拉克利斯", "Iraklis basketball"),
    (("panionios",), "帕尼奧尼奧斯", "Panionios basketball"),
    (("mykonos",), "米科諾斯", "Mykonos basketball"),
    (("apollon",), "阿波羅帕特雷", "Apollon Patras"),
    (("vikos",), "維科斯", "Vikos Falcons"),
    (("ionikos",), "伊奧尼科斯", "Ionikos basketball"),
    # 法國 LNB
    (("monaco",), "摩納哥", "AS Monaco Basket"),
    (("paris",), "巴黎", "Paris Basketball"),
    (("asvel", "villeurbanne"), "艾思維爾", "LDLC ASVEL"),
    (("bourg",), "布爾格", "JL Bourg"),
    (("le mans", "sarthe"), "勒芒薩爾特", "Le Mans Sarthe Basket"),
    (("strasbourg", "sig "), "史特拉斯堡", "SIG Strasbourg"),
    (("cholet",), "紹萊", "Cholet Basket"),
    (("nanterre",), "楠泰爾", "Nanterre 92"),
    (("limoges",), "利摩日", "Limoges CSP"),
    (("dijon",), "第戎", "JDA Dijon"),
    (("gravelines", "dunkerque"), "格拉沃利訥", "BCM Gravelines-Dunkerque"),
    (("le portel", "portel"), "勒波特爾", "ESSM Le Portel"),
    (("saint-quentin", "saint quentin"), "聖康坦", "Saint-Quentin Basket"),
    (("chalon",), "夏龍", "Elan Chalon"),
    (("boulazac",), "布拉扎克", "Boulazac basket"),
    (("nancy",), "南錫", "SLUC Nancy"),
    (("roanne",), "羅阿訥", "Chorale Roanne"),
    (("elan bearnais", "bearnais", "pau"), "波城", "Elan Bearnais Pau"),
    (("blois",), "布洛瓦", "ADA Blois"),
    # 德國 BBL
    (("bayern",), "拜仁慕尼黑", "Bayern Munich basketball"),
    (("alba",), "柏林阿爾巴", "Alba Berlin"),
    (("ulm",), "烏爾姆", "ratiopharm Ulm"),
    (("bonn",), "波昂", "Telekom Baskets Bonn"),
    (("ludwigsburg",), "路德維希堡", "MHP Riesen Ludwigsburg"),
    (("chemnitz",), "凱姆尼茲", "Niners Chemnitz"),
    (("wurzburg",), "維爾茨堡", "Würzburg Baskets"),
    (("oldenburg",), "奧登堡", "EWE Baskets Oldenburg"),
    (("bamberg",), "班貝格", "Bamberg Baskets"),
    (("hamburg",), "漢堡", "Veolia Towers Hamburg"),
    (("gottingen",), "哥廷根", "BG Göttingen"),
    (("heidelberg",), "海德堡", "MLP Academics Heidelberg"),
    (("rostock",), "羅斯托克海狼", "Rostock Seawolves"),
    (("braunschweig",), "布倫瑞克", "Basketball Löwen Braunschweig"),
    (("vechta",), "費希塔", "Rasta Vechta"),
    (("frankfurt",), "法蘭克福", "Frankfurt Skyliners"),
    (("weissenfels", "weißenfels"), "魏森費爾斯", "Mitteldeutscher BC"),
    (("bayreuth",), "拜羅伊特", "Bayreuth basketball"),
    (("jena",), "耶拿", "Science City Jena"),
    (("trier",), "特里爾", "Gladiators Trier"),
    # 立陶宛 LKL
    (("zalgiris",), "考納斯綠林", "Zalgiris Kaunas"),
    (("rytas",), "維爾紐斯里塔斯", "Rytas Vilnius"),
    (("wolves",), "維爾紐斯狼", "Wolves Vilnius"),
    (("lietkabelis",), "利特卡貝利斯", "Lietkabelis"),
    (("neptunas",), "克萊佩達海王星", "Neptunas Klaipeda"),
    (("siauliai",), "希奧利艾", "Siauliai basketball"),
    (("juventus", "utena"), "烏田納", "Juventus Utena"),
    (("pieno", "pasvalys"), "帕斯瓦利斯", "Pieno zvaigzdes"),
    (("gargzdai",), "加爾日代", "Gargzdai basketball"),
    (("jonava",), "約納瓦", "Jonava basketball"),
    (("nevezis", "kedainiai"), "凱代尼艾", "Nevezis Kedainiai"),
    (("taurage",), "陶拉格", "Taurage basketball"),
    (("mazeikiai",), "馬热伊基艾", "Mazeikiai basketball"),
    # 以色列
    (("maccabi tel aviv", "maccabi playtika"), "馬卡比特拉維夫", "Maccabi Tel Aviv basketball"),
    (("hapoel tel aviv", "hapoel tel-aviv", "hapoel ibi", "hapoel shlomo"), "哈波特拉維夫", "Hapoel Tel Aviv basketball"),
    (("jerusalem",), "哈波耶路撒冷", "Hapoel Jerusalem basketball"),
    (("holon",), "霍隆", "Hapoel Holon"),
    (("herzliya",), "赫茲利亞", "Bnei Herzliya"),
    (("rishon",), "里雄", "Maccabi Rishon LeZion"),
    (("haifa",), "海法", "Hapoel Haifa basketball"),
    (("ness ziona",), "內斯茲約納", "Ironi Ness Ziona"),
    (("galil",), "加利利", "Hapoel Galil Elyon"),
    (("ramat gan",), "拉馬特甘", "Maccabi Ramat Gan"),
    (("beer sheva", "be'er sheva"), "貝爾謝巴", "Hapoel Beer Sheva basketball"),
    (("eilat",), "埃拉特", "Hapoel Eilat"),
    (("kiryat ata",), "基里亞特阿塔", "Ironi Kiryat Ata"),
    (("haemek", "ha'emek", "emek"), "哈波哈埃梅克", "Hapoel HaEmek basketball"),
    (("ashdod",), "阿什杜德", "Maccabi Ashdod basketball"),
    # 亞得里亞海 ABA
    (("crvena", "zvezda", "red star"), "貝爾格勒紅星", "Crvena Zvezda basketball"),
    (("partizan",), "貝爾格勒游擊隊", "Partizan basketball"),
    (("buducnost",), "布杜克諾斯特", "Buducnost VOLI"),
    (("cedevita", "olimpija"), "采迪維塔", "Cedevita Olimpija"),
    (("igokea",), "伊戈克亞", "Igokea"),
    (("mega",), "梅加", "Mega Basket"),
    (("fmp",), "FMP", "FMP Beograd"),
    (("split",), "斯普利特", "KK Split"),
    (("zadar",), "札達爾", "KK Zadar"),
    (("krka",), "克爾卡", "Krka Novo Mesto"),
    (("borac",), "博拉茨", "Borac Cacak"),
    (("spartak", "subotica"), "蘇博蒂察斯巴達", "Spartak Subotica"),
    (("cluj",), "克盧日大學", "U-BT Cluj-Napoca"),
    (("dubai",), "杜拜", "Dubai Basketball"),
    (("bosna",), "波士納", "Bosna Sarajevo"),
    (("sc derby", "derby"), "德比", "SC Derby Podgorica"),
    (("studentski",), "斯圖登茨基", "Studentski centar"),
    (("vienna", "wien"), "維也納", "BC Vienna"),
    # 其他常在歐盃、籃球冠軍聯賽出現的
    (("balkan",), "巴爾幹", "Balkan Botevgrad"),
    (("slask", "wroclaw"), "弗羅茨瓦夫", "Slask Wroclaw"),
    (("london lions", "london"), "倫敦獅", "London Lions"),
    (("prometey",), "普羅米修斯", "Prometey basketball"),
    (("riga", "vef"), "里加", "VEF Riga"),
    (("sofia", "levski"), "索菲亞", "Levski Sofia basketball"),
]

LEAGUE_HINT = {
    "acb": " baloncesto", "lba": " basket", "bsl": " basketbol", "gbl": " basketball", "lnb": " basket",
    "bbl": " basketball", "lkl": " krepsinis", "isr": " basketball", "aba": " basketball",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ç", "c").replace("ž", "z").replace("š", "s").replace("ė", "e")
    return re.sub(r"\s+", " ", s.lower()).strip()


def _hit(n, kws):
    for k in kws:
        if re.search(r"(^|[^a-z])" + re.escape(k.strip()) + r"($|[^a-z])", n):
            return k
    return None


def lookup(name):
    """回傳 (中文名, 查新聞用名, 關鍵字)；找不到就 (None, 原名, None)。"""
    n = norm(name)
    for kws, zh, q in TEAMS:
        k = _hit(n, kws)
        if k:
            return zh, q, kws[0]
    return None, name, None


def same_club(a, b):
    """兩個英文隊名是不是同一支球隊（用同一組關鍵字對得上）。"""
    na, nb = norm(a), norm(b)
    for kws, _zh, _q in TEAMS:
        if _hit(na, kws) and _hit(nb, kws):
            return True
    return False
