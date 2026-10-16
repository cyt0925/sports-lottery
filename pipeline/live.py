# -*- coding: utf-8 -*-
"""即時比分：玩運彩（歐洲籃球、日本籃球）和 SV.LEAGUE 不讓網頁直接抓，所以由 GitHub 這邊每分鐘抓一次，
寫成一個很小的 live.json，推到 live 分支（不會觸發網站重建）。網頁每 90 秒來讀一次。

只有在「有比賽正在打、或 25 分鐘內要開打」的時候才會一直跑；沒比賽就馬上結束。
NBA、NHL、足球不用這個，網頁直接跟 ESPN 拿，30 秒更新一次。
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taiwan_odds import fetch_livescore_ids, TW  # noqa: E402
from playsport import _state_for  # noqa: E402

UTC = timezone.utc
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ALLIANCE = {"eurobasket": 8, "jpbasket": 97}


def log(msg):
    print(msg, flush=True)


def _dt(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def targets(now):
    """從今天的資料找出要盯的比賽：開打前 25 分鐘到開打後 4 小時、還沒結束的。"""
    try:
        d = json.load(open(os.path.join(ROOT, "data", "today.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for g in d.get("games") or []:
        src = g.get("live_src") or ""
        if src not in ("playsport", "svleague"):
            continue
        st = _dt(g.get("start"))
        if not st or g["status"]["state"] == "post" and now - st > timedelta(hours=1):
            continue
        if st - timedelta(minutes=25) <= now <= st + timedelta(hours=4):
            out.append(dict(id=g["id"], league=g["league"], src=src, start=st, day=g.get("day_tw", "").replace("-", "")))
    return out


def playsport_scores(tg, now):
    res = {}
    for key, aid in ALLIANCE.items():
        days = sorted({t["day"] for t in tg if t["league"] == key})
        for d in days:
            ids = fetch_livescore_ids(aid, d) or {}
            for gid, ls in ids.items():
                try:
                    start_tw = datetime.strptime(ls.get("dateon") or "", "%Y-%m-%d %H:%M:%S").replace(tzinfo=TW)
                except ValueError:
                    continue
                state, detail, _ = _state_for(start_tw.astimezone(UTC), now, ls)
                hs, as_ = ls.get("hscore"), ls.get("ascore")
                if state == "pre" and not hs and not as_:
                    continue
                res[f"ps{gid}"] = dict(s=state, h=str(hs) if hs not in (None, "") else None, a=str(as_) if as_ not in (None, "") else None, d=detail)
    return res


def sv_scores(now):
    import svleague
    lg = dict(key="jpvolley", label="日本排球", sport="volleyball")
    errs = []
    games, _ = svleague.fetch_games(lg, lambda *_: None, errs, now=now)
    res = {}
    for g in games:
        if g["status"]["state"] == "pre":
            continue
        res[g["id"]] = dict(s=g["status"]["state"], h=g["home"].get("score"), a=g["away"].get("score"), d=g["status"]["detail"])
    return res


def git(*args, inp=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="github-actions[bot]", GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
               GIT_COMMITTER_NAME="github-actions[bot]", GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com")
    r = subprocess.run(["git", *args], input=inp, capture_output=True, text=True, cwd=ROOT, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def push(payload):
    """只放一個檔案、只留一個 commit，強制推到 live 分支，分支不會越長越大。"""
    blob = git("hash-object", "-w", "--stdin", inp=payload)
    tree = git("mktree", inp=f"100644 blob {blob}\tlive.json\n")
    commit = git("commit-tree", tree, "-m", "即時比分")
    git("push", "-f", "-q", "origin", f"{commit}:refs/heads/live")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=22)
    ap.add_argument("--every", type=int, default=60)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    t_end = time.time() + args.minutes * 60
    last = None
    loops = 0
    scores = {}
    while True:
        now = datetime.now(UTC)
        tg = targets(now)
        if not tg:
            log("沒有正在打或快開打的比賽，結束。")
            break
        try:
            if any(t["src"] == "playsport" for t in tg):
                scores.update(playsport_scores([t for t in tg if t["src"] == "playsport"], now))
            if any(t["src"] == "svleague" for t in tg) and loops % 3 == 0:
                scores.update(sv_scores(now))
        except Exception as e:  # noqa: BLE001
            log(f"抓比分失敗：{e!r}")
        want = {t["id"] for t in tg}
        games = {k: v for k, v in scores.items() if k in want}
        body = json.dumps(games, ensure_ascii=False, sort_keys=True)
        if body != last and games:
            payload = json.dumps(dict(updated=now.astimezone(TW).isoformat(timespec="seconds"), games=games), ensure_ascii=False, separators=(",", ":"))
            if args.dry:
                log(payload[:600])
            else:
                try:
                    push(payload)
                    log(f"{now.astimezone(TW):%H:%M:%S} 更新 {len(games)} 場：" + "；".join(f"{k} {v['a']}:{v['h']} {v['d']}" for k, v in list(games.items())[:4]))
                except Exception as e:  # noqa: BLE001
                    log(f"推送失敗：{e!r}")
            last = body
        loops += 1
        if all(v.get("s") == "post" for v in games.values()) and len(games) == len(want):
            log("盯的比賽都打完了，結束。")
            break
        if time.time() + args.every > t_end:
            break
        time.sleep(args.every)


if __name__ == "__main__":
    main()
