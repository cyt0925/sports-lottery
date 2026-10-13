#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生 loader.svg：8-bit 像素風的爸爸娃娃側面跑步（逐格動畫、透明背景）。
改這裡再跑一次就會重畫：python3 pipeline/make_loader.py
"""
import math
import os

W, H = 40, 48          # 畫布格數
SCALE = 6              # 每格幾 px
FRAMES = 8
DUR = 0.64             # 一圈秒數

PAL = {
    "S": "#e9a978",  # 皮膚
    "D": "#c9875c",  # 皮膚陰影／鬍碴
    "K": "#1e1b1e",  # 頭髮、眼睛
    "G": "#d9ad3c",  # 眼鏡金框
    "L": "#f6f1e6",  # 鏡片反光／白
    "W": "#f7f4ee",  # 白（牙齒、短褲、鞋、襪）
    "V": "#d8d2c4",  # 白的陰影
    "R": "#c8372f",  # 紅（嘴巴、襪條紋、領口）
    "T": "#ef6b5e",  # 舌頭
    "B": "#2448a6",  # 球衣藍
    "N": "#17327a",  # 球衣藍陰影
    "C": "#5a8ae0",  # 球衣淺藍紋
    "Y": "#e6b63a",  # 隊徽金
    "A": "#9c9790",  # 鞋底灰
    "Z": "#3a3540",  # 影子
    "U": "#8d8a94",  # 灰塵
}


def blank():
    return [[None] * W for _ in range(H)]


def put(g, x, y, c):
    x, y = int(round(x)), int(round(y))
    if 0 <= x < W and 0 <= y < H:
        g[y][x] = c


def rect(g, x0, y0, x1, y1, c):
    for y in range(int(y0), int(y1) + 1):
        for x in range(int(x0), int(x1) + 1):
            put(g, x, y, c)


def disc(g, cx, cy, r, c):
    for y in range(int(cy - r - 1), int(cy + r + 2)):
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r + 0.3:
                put(g, x, y, c)


def line(g, x0, y0, x1, y1, c, t=2):
    """粗線：沿線每一步蓋一個 t×t 的方塊。"""
    n = max(1, int(math.hypot(x1 - x0, y1 - y0) * 2))
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        y = y0 + (y1 - y0) * i / n
        for dy in range(t):
            for dx in range(t):
                put(g, x - (t - 1) / 2 + dx, y - (t - 1) / 2 + dy, c)


def stamp(g, x0, y0, rows, trans="."):
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != trans:
                put(g, x0 + i, y0 + j, ch)


# ---------- 頭（側面朝右）：手畫格子，最重要的部分 ----------
HEAD = [
    "................KKKK....",
    "...........KKKKKKKKKKK..",
    ".......KKKKKKKKKKKKKKKK.",
    ".....KKKKKKKKKKKKKKKKKK.",
    "....KKKKKKKKKKKKKKKKKKK.",
    "...KKKKKKKKKKKKKKKKKKKK.",
    "...KKKKKKKSSSSSKKKKKKKK.",
    "..KKKKKKSSSSSSSSSKKKKK..",
    "..KKKKKSSSSSSSSSSSSSSK..",
    "..KKKKSSSSSSSSSSSSSSSS..",
    "..KKKKSSSSSSSGGGGGGGGS..",
    "..KKKSSGGGGGGGSSSSSLGS..",
    "..KKKSSSSSSSSGSSKKSLGSS.",
    "..KKKSSSSSSSSGSSKKSSGSS.",
    "..KKKSSSSSSSSGGGGGGGGSS.",
    "..KKKSSSSSSSSSSSSSSSSSSS",
    "...KKSSSSSSSSSSSSSSSSSS.",
    "...KSSSSSSSSSSSSSKKKKKS.",
    "....SSSSSSSSSSSSKTWWWWK.",
    "....DSSSSSSSSSSSKRRRRRK.",
    ".....DDSSSSSSSSSKKRRRK..",
    "......DDDSSSSSSSDKKKK...",
    ".......DDDDSSSDDDD......",
    ".........DDDDDDD........",
]
HEAD_X, HEAD_Y = 8, 0     # 頭貼在畫布的位置
NECK = (18, 24)           # 脖子中心
SHOULDER = (18, 26)
HIP = (18, 36)


def draw_body(g, dy):
    # 脖子
    rect(g, 16, 23 + dy, 19, 25 + dy, "S")
    # 球衣（側面：前面亮、背面暗）
    rect(g, 12, 25 + dy, 23, 34 + dy, "B")
    rect(g, 12, 25 + dy, 13, 34 + dy, "N")
    # 淺藍 V 字紋
    for i in range(0, 5):
        put(g, 14 + i, 28 + i + dy, "C")
        put(g, 23 - i, 28 + i + dy, "C") if 23 - i > 18 else None
    for i in range(0, 3):
        put(g, 14 + i, 32 + i + dy, "C")
    # 領口紅邊
    rect(g, 15, 25 + dy, 20, 25 + dy, "R")
    put(g, 21, 26 + dy, "R")
    # 隊徽（金色一點）
    put(g, 21, 29 + dy, "Y")
    put(g, 22, 29 + dy, "Y")
    put(g, 21, 30 + dy, "Y")
    # 短褲
    rect(g, 12, 35 + dy, 23, 38 + dy, "W")
    rect(g, 12, 35 + dy, 13, 38 + dy, "V")
    rect(g, 12, 38 + dy, 23, 38 + dy, "V")


def draw_leg(g, hip, th, tk, back, dy):
    """hip 角度 th（正＝往前）、膝蓋彎 tk；back=後腳畫暗色。"""
    hx, hy = hip[0], hip[1] + dy
    a = math.radians(th)
    kx, ky = hx + 6 * math.sin(a), hy + 6 * math.cos(a)
    b = math.radians(th - tk)       # 小腿角度：膝蓋往後折
    fx, fy = kx + 6 * math.sin(b), ky + 6 * math.cos(b)
    skin = "D" if back else "S"
    line(g, hx, hy, kx, ky, skin, 3)
    line(g, kx, ky, fx, fy, skin, 3)
    # 襪子（小腿下半段）
    sx, sy = kx + 3.5 * math.sin(b), ky + 3.5 * math.cos(b)
    line(g, sx, sy, fx, fy, "V" if back else "W", 3)
    line(g, sx, sy, sx + 0.8 * math.sin(b), sy + 0.8 * math.cos(b), "R", 3)
    line(g, sx + 1.4 * math.sin(b), sy + 1.4 * math.cos(b), sx + 2.0 * math.sin(b), sy + 2.0 * math.cos(b), "B", 3)
    # 鞋子：朝右的 5×3 方塊，鞋底灰
    shoe_x = int(round(fx)) - 1
    shoe_y = int(round(fy)) + 1
    rect(g, shoe_x, shoe_y, shoe_x + 4, shoe_y + 1, "V" if back else "W")
    rect(g, shoe_x, shoe_y + 2, shoe_x + 4, shoe_y + 2, "A")
    return fx, fy


def draw_arm(g, sh, ts, back, dy):
    sx, sy = sh[0], sh[1] + dy
    a = math.radians(ts)
    ex, ey = sx + 5 * math.sin(a), sy + 5 * math.cos(a)
    b = math.radians(ts + 85)       # 手肘固定彎，前臂往前
    wx, wy = ex + 5 * math.sin(b), ey + 5 * math.cos(b)
    sleeve = "N" if back else "B"
    skin = "D" if back else "S"
    line(g, sx, sy, sx + 2.2 * math.sin(a), sy + 2.2 * math.cos(a), sleeve, 3)
    line(g, sx + 2.2 * math.sin(a), sy + 2.2 * math.cos(a), ex, ey, skin, 3)
    line(g, ex, ey, wx, wy, skin, 3)
    disc(g, wx + 0.6 * math.sin(b), wy + 0.6 * math.cos(b), 1.4, skin)


# 跑步循環：8 格。th 髖角度（正＝往前），tk 膝蓋折角
TH = [38, 24, 4, -18, -36, -22, 4, 26]
TK = [8, 14, 26, 44, 66, 96, 78, 34]
DY = [1, 2, 1, 0, 1, 2, 1, 0]      # 身體上下


def frame(i):
    g = blank()
    dy = DY[i]
    j = (i + 4) % FRAMES
    # 影子
    rect(g, 11, 46, 25, 46, "Z")
    # 後手、後腳
    draw_arm(g, SHOULDER, -TH[j] * 0.9, True, dy)
    draw_leg(g, HIP, TH[j], TK[j], True, dy)
    draw_body(g, dy)
    # 頭
    stamp(g, HEAD_X, HEAD_Y + dy, HEAD)
    # 前腳、前手
    draw_leg(g, HIP, TH[i], TK[i], False, dy)
    draw_arm(g, SHOULDER, -TH[i] * 0.9, False, dy)
    # 灰塵（在後面腳落地的時候）
    if i in (0, 1, 4, 5):
        k = 0 if i in (0, 1) else 1
        rect(g, 5 - k * 2, 44, 6 - k * 2, 44, "U")
        put(g, 4 - k * 3, 43, "U")
        put(g, 7 - k * 2, 45, "U")
    return g


def svg_frame(g):
    parts = []
    for y, row in enumerate(g):
        x = 0
        while x < W:
            c = row[x]
            if c is None:
                x += 1
                continue
            x0 = x
            while x < W and row[x] == c:
                x += 1
            parts.append(f'<rect x="{x0 * SCALE}" y="{y * SCALE}" width="{(x - x0) * SCALE}" height="{SCALE}" fill="{PAL[c]}"/>')
    return "".join(parts)


def main():
    frames = [svg_frame(frame(i)) for i in range(FRAMES)]
    step = DUR / FRAMES
    css = [
        ".f{opacity:0;animation:show %.3fs steps(1,end) infinite}" % DUR,
        "@keyframes show{0%%{opacity:1}%.3f%%{opacity:0}100%%{opacity:0}}" % (100 / FRAMES),
    ]
    for i in range(FRAMES):
        css.append(".f%d{animation-delay:-%.3fs}" % (i, (FRAMES - i) % FRAMES * step))
    css.append("@media (prefers-reduced-motion:reduce){.f{animation-duration:%.1fs}}" % (DUR * 6))
    body = "".join(f'<g class="f f{i}">{fr}</g>' for i, fr in enumerate(frames))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W * SCALE} {H * SCALE}" width="{W * SCALE}" height="{H * SCALE}" '
           f'shape-rendering="crispEdges" role="img" aria-label="跑步中的爸爸，資料載入中">'
           f"<style>{''.join(css)}</style>{body}</svg>")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "loader.svg")
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print("寫入", out, len(svg), "bytes")
    # 順便輸出一張 8 格並排的 PNG 檢查用（沒有 Pillow 就跳過）
    try:
        from PIL import Image
        sheet = Image.new("RGBA", (W * FRAMES * 4, H * 4), (20, 18, 28, 255))
        for i in range(FRAMES):
            g = frame(i)
            for y, row in enumerate(g):
                for x, c in enumerate(row):
                    if c:
                        col = tuple(int(PAL[c][k:k + 2], 16) for k in (1, 3, 5)) + (255,)
                        for dy in range(4):
                            for dx in range(4):
                                sheet.putpixel((i * W * 4 + x * 4 + dx, y * 4 + dy), col)
        sheet.save(os.path.join(os.path.dirname(out), "loader-sheet.png"))
        print("寫入 loader-sheet.png")
    except ImportError:
        pass


if __name__ == "__main__":
    main()
