/* 運彩大叔：讀 data/today.json，純前端。手機優先：一層看重點，點一下看詳細。 */
(function () {
  "use strict";

  const $ = (s, el = document) => el.querySelector(s);
  const params = new URLSearchParams(location.search);
  const DATA_URL = params.get("data") === "sample" ? "data/sample.json" : "data/today.json";
  const SPORT_ICON = { all: "i-grid", nba: "i-basketball", basketball: "i-basketball", eurobasket: "i-basketball", jpbasket: "i-basketball", cba: "i-basketball", jpvolley: "i-volleyball", volleyball: "i-volleyball", soccer: "i-soccer", hockey: "i-hockey", football: "i-football" };
  const chipOf = (x) => x.chip || x.sport;

  const state = {
    data: null,
    sport: localStorage.getItem("sport") || "all",
    view: "today",
    detail: null,
    showMore: false,
    pickTab: {},        // 卡片上的預測按鈕現在顯示哪一種玩法（誰會贏／讓分／大小分）
    showAllInj: false,
    showAllHot: false,
    standingsLeague: localStorage.getItem("standingsLeague") || null,
    numbersOpen: false,
    picks: {},
    day: null,
    recTab: "site",
    results: null,
    resultsAt: 0,
  };

  // ---------- 小工具 ----------
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const tname = (t) => t.name_zh || t.short || t.name || "";
  const initials = (t) => (t.abbr || (t.name || "?").slice(0, 3)).toUpperCase().slice(0, 3);
  const icon = (id) => `<svg><use href="#${id}"/></svg>`;
  const num = (v, d = 2) => (v == null ? "–" : typeof v === "number" ? v.toFixed(d) : esc(v));
  function cheng(p) {
    if (p == null) return "";
    const v = Math.round(p * 20) / 2;
    if (v >= 9.5) return "九成五以上";
    if (v <= 1) return "一成不到";
    const d = "零一二三四五六七八九十";
    const w = Math.floor(v), h = v - w >= 0.5;
    if (w === 5 && !h) return "一半";
    return d[w] + "成" + (h ? "五" : "");
  }
  function todayTW() { return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Taipei" }); }
  function dayLabel(day) {
    const t = todayTW();
    const toUTC = (s) => { const [y, m, dd] = s.split("-").map(Number); return Date.UTC(y, m - 1, dd); };
    const diff = Math.round((toUTC(day) - toUTC(t)) / 86400000);
    const wk = ["日", "一", "二", "三", "四", "五", "六"][new Date(toUTC(day)).getUTCDay()];
    const md = day.slice(5).replace("-", "/");
    const name = diff === 0 ? "今天" : diff === 1 ? "明天" : diff === -1 ? "昨天" : diff === 2 ? "後天" : "";
    return { name: name || md, sub: `${md}（${wk}）` };
  }
  function addDays(day, n) {
    const [y, m, d] = day.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
  }
  // 日期列表：昨天、今天、往後 3 天
  const dayList = () => [-1, 0, 1, 2, 3].map((n) => addDays(todayTW(), n));
  const isTodayView = () => state.day === todayTW();
  const weekOf = (d) => "週" + ["日", "一", "二", "三", "四", "五", "六"][new Date(d + "T00:00:00Z").getUTCDay()];
  // 昨天／今天／明天／後天，再後面用「週三」
  const dayName = (d) => { const n = dayLabel(d).name; return ["昨天", "今天", "明天", "後天"].includes(n) ? n : weekOf(d); };
  function ago(ts) {
    const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
    if (m < 1) return "剛剛更新";
    if (m < 60) return `${m} 分鐘前更新`;
    return `${Math.floor(m / 60)} 小時前更新`;
  }
  function logoImg(t, cls = "logo") {
    if (t.logo) return `<img class="${cls}" src="${esc(t.logo)}" alt="" loading="lazy" data-fb="${esc(initials(t))}">`;
    return `<span class="${cls} fallback">${esc(initials(t))}</span>`;
  }
  function avatarImg(p) {
    const fb = esc((p.player || "?").split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase());
    if (p.headshot) return `<img class="avatar" src="${esc(p.headshot)}" alt="" loading="lazy" data-fb="${fb}">`;
    return `<span class="avatar fallback">${fb}</span>`;
  }
  const sevClass = (s) => (s === "out" ? "out" : s === "maybe" ? "maybe" : s === "limited" ? "limited" : s === "ir" ? "ir" : s === "ok" ? "ok" : s === "news" ? "vio" : "muted");
  document.addEventListener("error", (e) => {
    const el = e.target;
    if (el.tagName !== "IMG") return;
    if (!el.dataset.fb) { el.remove(); return; }
    const span = document.createElement("span");
    span.className = el.className + " fallback";
    span.textContent = el.dataset.fb;
    el.replaceWith(span);
  }, true);

  // ---------- 資料 ----------
  function showLoader(on) { const el = $("#loader"); if (el) el.classList.toggle("on", on); }
  async function load(opts = {}) {
    const visible = !opts.silent;
    const t0 = Date.now();
    if (visible) showLoader(true);
    try {
      const r = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      state.data = await r.json();
    } catch (err) {
      $("#games").innerHTML = `<div class="empty">資料載入失敗（${esc(err.message)}）。等一下再按右上角重新整理。</div>`;
      showLoader(false);
      return;
    }
    reapplyLive();
    migrateIds();
    settlePicks();
    if (opts.silent) renderKeepScroll(render); else render();
    if (visible) setTimeout(() => showLoader(false), Math.max(0, 700 - (Date.now() - t0)));
    // 還沒對到答案、又已經不在今天名單裡的，去賽果庫找
    const ids = new Set((state.data.games || []).map((g) => g.id));
    const lost = (id, start) => !ids.has(id) && Date.parse(start) < Date.now();
    if (Object.entries(state.picks).some(([id, p]) => !p.result && lost(id, p.start)) || state.parlays.some((x) => !x.result && x.legs.some((l) => !l.r && lost(l.gid, l.start)))) {
      ensureResults().then(() => { if (settlePicks()) renderRecord(); });
    }
  }

  // ---------- 即時比分 ----------
  // NBA、NHL、足球：網頁直接跟 ESPN 拿（30 秒）。歐洲籃球、日本籃球、CBA、日本排球：GitHub 每分鐘抓一次放到 live 分支（網頁 90 秒讀一次）。
  const LIVE_API = "https://api.github.com/repos/cyt0925/sports-lottery/contents/live.json?ref=live";
  const LIVE_RAW = "https://raw.githubusercontent.com/cyt0925/sports-lottery/live/live.json";
  const live = { espnAt: 0, fileAt: 0, busy: false, useRaw: false, last: {} };
  const PERIODS = { basketball: 4, football: 4, hockey: 3, soccer: 2 };
  function liveWanted(g) {
    if (g.status.state === "post") return false;
    const st = Date.parse(g.start) || 0, now = Date.now();
    return g.status.state === "in" || (now >= st - 10 * 60000 && now <= st + 5 * 3600000);
  }
  const etDate = (iso) => new Date(iso).toLocaleDateString("en-CA", { timeZone: "America/New_York" }).replace(/-/g, "");
  function zhStatus(sport, st) {
    const t = st.type || {}, name = t.name || "", p = st.period || 0, clock = st.displayClock || "";
    if (t.state === "post" || t.completed) return p > (PERIODS[sport] || 4) && sport !== "soccer" ? "已結束（延長）" : "已結束";
    if (t.state === "pre") return "未開賽";
    if (/HALFTIME/.test(name)) return "中場休息";
    if (/END_PERIOD/.test(name)) return `第${p}節結束`;
    if (sport === "soccer") return clock ? `${clock}` : "進行中";
    return p > (PERIODS[sport] || 4) ? `延長賽 ${clock}` : `第${p}節 ${clock}`;
  }
  async function pollEspn(list) {
    const groups = {};
    list.forEach((g) => { const src = g.live_src || ""; if (src.indexOf("espn:") !== 0) return; const k = src.slice(5) + "|" + etDate(g.start); (groups[k] = groups[k] || []).push(g); });
    const ups = {};
    await Promise.all(Object.keys(groups).map(async (k) => {
      const [path, d] = k.split("|");
      try {
        const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/${path}/scoreboard?dates=${d}`, { cache: "no-store" });
        if (!r.ok) return;
        const js = await r.json();
        (js.events || []).forEach((ev) => {
          const c = (ev.competitions || [])[0] || {}, st = c.status || ev.status || {}, cs = c.competitors || [];
          const h = cs.find((x) => x.homeAway === "home") || cs[0] || {}, a = cs.find((x) => x.homeAway === "away") || cs[1] || {};
          const sport = (groups[k][0] || {}).sport;
          const u = { s: (st.type || {}).state, h: h.score, a: a.score, d: zhStatus(sport, st), hw: h.winner, aw: a.winner };
          ups[String(c.id || ev.id)] = u; ups[String(ev.id)] = u;
        });
      } catch (_) { /* 抓不到就等下一輪 */ }
    }));
    return ups;
  }
  async function pollFile() {
    try {
      const r = live.useRaw ? await fetch(`${LIVE_RAW}`, { cache: "no-cache" })
        : await fetch(LIVE_API, { cache: "no-cache", headers: { Accept: "application/vnd.github.raw" } });
      if (r.status === 403 || r.status === 429) { live.useRaw = true; return {}; }
      if (!r.ok) return {};
      const js = await r.json();
      if (js.odds && js.odds_at) applyOdds(js.odds, js.odds_at);
      return js.games || {};
    } catch (_) { return {}; }
  }
  function applyOdds(odds, at) {
    let changed = false;
    (state.data.games || []).forEach((g) => {
      const x = odds[g.id];
      if (!x || g.status.state !== "pre") return;
      const cur = (g.tw && g.tw.updated) || "";
      if (cur && cur >= at) return;
      g.tw = Object.assign({}, g.tw || { source: "玩運彩" }, { ml: x.ml || (g.tw || {}).ml, spread: x.spread || (g.tw || {}).spread, total: x.total || (g.tw || {}).total, updated: at });
      changed = true;
    });
    live.odds = { odds, at };
    if (changed) {
      renderKeepScroll(() => { renderPicks(); renderParlay(); renderGames(); });
      if (state.detail) renderSheetKeep();
    }
  }
  function renderSheetKeep() {
    const sh = $("#sheet"), top = sh.scrollTop;
    renderSheet();
    sh.scrollTop = top;
  }
  function applyLive(g, u) {
    const before = g.status.state + "|" + g.status.detail + "|" + g.home.score + "|" + g.away.score;
    const st = u.s === "post" ? "post" : u.s === "in" ? "in" : g.status.state;
    g.status.state = st;
    g.status.completed = st === "post";
    if (u.d) g.status.detail = u.d;
    if (u.h != null && u.h !== "") g.home.score = String(u.h);
    if (u.a != null && u.a !== "") g.away.score = String(u.a);
    if (st === "post") {
      const hs = Number(g.home.score), as = Number(g.away.score);
      g.home.winner = u.hw != null ? !!u.hw : hs > as;
      g.away.winner = u.aw != null ? !!u.aw : as > hs;
    }
    const after = g.status.state + "|" + g.status.detail + "|" + g.home.score + "|" + g.away.score;
    return before === after ? 0 : (before.split("|")[0] !== st ? 2 : 1);
  }
  function renderKeepScroll(fn) {
    // 重畫之前記住畫面最上面那張卡片在哪，重畫之後捲回同一個位置，不會跳
    let anchor = null, top = 0;
    for (const el of document.querySelectorAll("#picks [data-goto], #games [data-goto]")) {
      const r = el.getBoundingClientRect();
      if (r.bottom > 80) { anchor = el.dataset.goto; top = r.top; break; }
    }
    fn();
    if (anchor) {
      const el = document.querySelector(`#games [data-goto="${CSS.escape(anchor)}"]`) || document.querySelector(`[data-goto="${CSS.escape(anchor)}"]`);
      if (el) window.scrollBy(0, el.getBoundingClientRect().top - top);
    }
  }
  function patchGame(g) {
    document.querySelectorAll(`[data-mid="${CSS.escape(g.id)}"]`).forEach((el) => { el.outerHTML = midCol(g); });
    document.querySelectorAll(`[data-when="${CSS.escape(g.id)}"]`).forEach((el) => { el.outerHTML = whenText(g); });
  }
  function useUpdates(ups, at) {
    let moved = false, any = false;
    (state.data.games || []).forEach((g) => {
      const u = ups[g.id];
      if (!u) return;
      live.last[g.id] = { u, at };
      const ch = applyLive(g, u);
      if (!ch) return;
      any = true;
      if (ch === 2) moved = true; else patchGame(g);
    });
    if (!any) return;
    if (settlePicks() && state.recTab === "mine") renderRecord();
    if (moved) renderKeepScroll(() => { renderPicks(); renderParlay(); renderGames(); });
    if (state.detail) { const g = findGame(state.detail); if (g) patchGame(g); }
  }
  async function liveTick() {
    if (!state.data || live.busy || document.hidden) return;
    const list = (state.data.games || []).filter(liveWanted);
    if (!list.length) return;
    live.busy = true;
    try {
      const now = Date.now();
      if (list.some((g) => (g.live_src || "").indexOf("espn:") === 0) && now - live.espnAt >= 30000) {
        live.espnAt = now;
        useUpdates(await pollEspn(list), now);
      }
      if (list.some((g) => g.live_src === "playsport" || g.live_src === "svleague") && now - live.fileAt >= 90000) {
        live.fileAt = now;
        useUpdates(await pollFile(), now);
      }
    } finally { live.busy = false; }
  }
  async function oddsTick() {
    // 沒有比賽在打的時候，也每 10 分鐘去看一次台灣運彩有沒有新的線
    if (!state.data || live.busy || document.hidden || Date.now() - live.fileAt < 10 * 60000) return;
    live.busy = true;
    try {
      live.fileAt = Date.now();
      useUpdates(await pollFile(), Date.now());
    } finally { live.busy = false; }
  }
  function reapplyLive() {
    // 背景重新載入的資料比即時比分舊，把剛剛抓到的比分、台灣盤口蓋回去
    const gen = (state.data.generated_ts || 0) * 1000;
    (state.data.games || []).forEach((g) => { const x = live.last[g.id]; if (x && x.at > gen) applyLive(g, x.u); });
    if (live.odds) {
      (state.data.games || []).forEach((g) => {
        const x = live.odds.odds[g.id];
        if (x && g.status.state === "pre" && (!g.tw || !g.tw.updated || g.tw.updated < live.odds.at)) g.tw = Object.assign({}, g.tw || { source: "玩運彩" }, { ml: x.ml || (g.tw || {}).ml, spread: x.spread || (g.tw || {}).spread, total: x.total || (g.tw || {}).total, updated: live.odds.at });
      });
    }
  }

  // ---------- 爸爸的預測（存在這支手機的瀏覽器裡） ----------
  const PICK_KEY = "mypicks.v1";
  function loadPicks() { try { return JSON.parse(localStorage.getItem(PICK_KEY) || "{}") || {}; } catch (_) { return {}; } }
  function savePicks() { try { localStorage.setItem(PICK_KEY, JSON.stringify(state.picks)); } catch (_) { /* ignore */ } }
  state.picks = loadPicks();
  const gameStarted = (g) => g.status.state !== "pre" || (Date.parse(g.start) || 0) <= Date.now();
  const fmtLine = (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v);
  function lineOf(p) {
    if (p.side === "ats_home") return p.spread_home;
    if (p.side === "ats_away") return p.spread_home == null ? null : -p.spread_home;
    return null;
  }
  const sideLabel = (p) => p.side === "home" ? p.home : p.side === "away" ? p.away
    : p.side === "ats_home" ? `${p.home} ${fmtLine(lineOf(p))}` : p.side === "ats_away" ? `${p.away} ${fmtLine(lineOf(p))}`
      : (p.side === "over" ? "大分" : "小分") + (p.total != null ? " " + p.total : "");
  function marketOf(g) {
    // 台灣運彩有開就用台灣運彩的線，沒有就先用國際盤
    const o = g.odds || {}, tw = g.tw || {}, sp = tw.spread || {}, tt = tw.total || {};
    const twSpread = sp.line_home != null, twTotal = tt.line != null;
    return {
      spread: twSpread ? sp.line_home : (o.spread ?? null), spreadTw: twSpread,
      total: twTotal ? tt.line : (o.total ?? null), totalTw: twTotal,
      mlTw: !!(tw.ml && (tw.ml.home || tw.ml.away)),
    };
  }
  // 按鈕旁邊的賠率：台灣運彩有開就用台灣的；不讓分沒有台灣盤時用國際盤，讓分、大小只放台灣的
  function oddOf(g, side, mk) {
    const o = g.odds || {}, tw = g.tw || {}, ml = tw.ml || {}, sp = tw.spread || {}, tt = tw.total || {};
    const v = side === "home" || side === "away" ? (mk.mlTw ? ml[side] : o["dec_" + side])
      : side === "ats_home" ? (mk.spreadTw ? sp.home : null) : side === "ats_away" ? (mk.spreadTw ? sp.away : null)
        : side === "over" ? (mk.totalTw ? tt.over : null) : side === "under" ? (mk.totalTw ? tt.under : null) : null;
    const x = Number(v);
    return Number.isFinite(x) && x > 1 ? x.toFixed(2) : "";
  }
  function snapshotPick(g, side) {
    const o = g.odds || {}, tw = g.tw || {}, ml = tw.ml || {}, sp = tw.spread || {}, tt = tw.total || {}, s = g.suggestion || {};
    const mk = marketOf(g);
    const isSide = side === "home" || side === "away";
    const isAts = side === "ats_home" || side === "ats_away";
    const dec = isSide ? (ml[side] || o["dec_" + side] || null)
      : isAts ? ((mk.spreadTw ? (side === "ats_home" ? sp.home : sp.away) : null) || null)
        : ((mk.totalTw ? (side === "over" ? tt.over : tt.under) : null) || null);
    return {
      side, at: new Date().toISOString(), start: g.start, day_tw: g.day_tw, time_tw: g.time_tw, league: g.league, league_zh: g.league_zh, chip: chipOf(g),
      home: tname(g.home), away: tname(g.away), dec, prob: isSide ? (s.source === "own" ? ((s.probs || {})[side] ?? null) : o.prob_source !== "form" ? (o["prob_" + side] ?? null) : null) : null,
      spread_home: mk.spread, total: mk.total, line_src: (isAts ? mk.spreadTw : side === "over" || side === "under" ? mk.totalTw : mk.mlTw) ? "台灣運彩" : "國際盤",
      site_pick: s.pick || null, site_label: s.pick_label || null, site_play: s.play || null, site_conf: s.confidence || null,
      model_pick: (s.model && s.model.pick) || null,
    };
  }
  function judge(side, hs, as, total, spreadHome) {
    if (side === "home" || side === "away") return hs === as ? "push" : ((hs > as) === (side === "home") ? "win" : "loss");
    if (side === "ats_home" || side === "ats_away") {
      if (spreadHome == null) return null;
      const v = (hs - as) + spreadHome;          // 主隊加上讓分之後贏幾分
      if (v === 0) return "push";
      return (v > 0) === (side === "ats_home") ? "win" : "loss";
    }
    if (total == null) return null;
    const t = hs + as;
    return t === total ? "push" : ((t > total) === (side === "over") ? "win" : "loss");
  }
  function settleOne(p, hs, as) {
    if (!Number.isFinite(hs) || !Number.isFinite(as)) return null;
    const r = judge(p.side, hs, as, p.total, p.spread_home);
    if (!r) return null;
    return { hs, as, r, site: p.site_pick ? judge(p.site_pick, hs, as, p.total, p.spread_home) : null, model: p.model_pick ? judge(p.model_pick, hs, as, null) : null, settled_at: new Date().toISOString() };
  }
  function settlePicks() {
    let changed = false;
    const byId = {};
    (state.data && state.data.games || []).forEach((g) => { byId[g.id] = g; });
    for (const [gid, p] of Object.entries(state.picks)) {
      if (p.result) continue;
      const g = byId[gid];
      if (g && g.status.state === "post") {
        const res = settleOne(p, Number(g.home.score), Number(g.away.score));
        if (res) { p.result = res; changed = true; continue; }
      }
      const rr = state.results && state.results.results && state.results.results[gid];
      if (rr) { const res = settleOne(p, Number(rr[1]), Number(rr[2])); if (res) { p.result = res; changed = true; } }
    }
    const pc = settleParlays();
    if (changed) savePicks();
    return changed || pc;
  }
  async function ensureResults() {
    if (state.results && Date.now() - state.resultsAt < 30 * 60 * 1000) return;
    try {
      const r = await fetch(`data/results.json?t=${Date.now()}`, { cache: "no-store" });
      if (r.ok) { state.results = await r.json(); state.resultsAt = Date.now(); }
    } catch (_) { /* ignore */ }
  }
  function setPick(gid, side) {
    const g = findGame(gid);
    if (!g || gameStarted(g)) return;
    const cur = state.picks[gid];
    if (cur && cur.side === side) delete state.picks[gid];
    else state.picks[gid] = snapshotPick(g, side);
    savePicks();
    document.querySelectorAll(`[data-pickrow="${CSS.escape(gid)}"]`).forEach((el) => { el.outerHTML = pickButtons(g, el.dataset.compact === "1"); });
    const box = $("#mypick");
    if (box) box.innerHTML = pickButtons(g, false);
    renderParlay();
    if (state.recTab === "mine") renderRecord();
  }
  // 讓分講白話：熱門那隊要贏幾分以上才算對，冷門那隊輸幾分以內也算對
  function atsHint(spreadHome, H, A) {
    const L = Math.abs(spreadHome);
    if (!L) return "讓分 0：誰贏就算誰對，打平退錢。";
    const fav = spreadHome < 0 ? H : A, dog = spreadHome < 0 ? A : H;
    if (L % 1) return `押${fav}：要贏 ${Math.ceil(L)} 分以上才算對；押${dog}：輸 ${Math.floor(L)} 分以內、或贏球，都算對。`;
    return `押${fav}：要贏 ${L + 1} 分以上才算對（剛好贏 ${L} 分退錢）；押${dog}：輸 ${L - 1} 分以內、或贏球，都算對。`;
  }
  function pickButtons(g, compact) {
    const p = state.picks[g.id];
    const locked = gameStarted(g), post = g.status.state === "post";
    if (compact && !p && locked) return "";
    const mk = marketOf(g);
    const btn = (side, label) => {
      const on = p && p.side === side;
      const res = on && p.result ? p.result.r : "";
      const od = oddOf(g, side, mk);
      return `<button class="pbtn ${on ? "on" : ""} ${res}" data-pick="${side}" data-pick-game="${esc(g.id)}" ${locked ? "disabled" : ""}>${on ? icon("i-check") : ""}<span class="pt"><span class="pn">${esc(label)}</span>${od ? `<em class="odd">賠 ${od}</em>` : ""}</span>${res ? `<b>${res === "win" ? "對" : res === "loss" ? "錯" : "平"}</b>` : ""}</button>`;
    };
    const A = tname(g.away), H = tname(g.home);
    if (compact) {
      // 卡片上可以切「誰會贏／讓分／大小分」；押過的那一種先打開
      const playOf = (side) => (side === "ats_home" || side === "ats_away" ? "ats" : side === "over" || side === "under" ? "ou" : "ml");
      const mine = p ? playOf(p.side) : null;
      const plays = [["ml", "誰會贏"]];
      if (mk.spread != null && (!locked || mine === "ats")) plays.push(["ats", "讓分"]);
      if (mk.total != null && (!locked || mine === "ou")) plays.push(["ou", "大小分"]);
      let tab = state.pickTab[g.id] || mine || "ml";
      if (!plays.some((x) => x[0] === tab)) tab = "ml";
      const tabs = plays.length > 1 ? `<div class="ptabs">${plays.map(([k, l]) => `<button class="${k === tab ? "on" : ""}" data-ptab="${k}" data-ptab-game="${esc(g.id)}">${l}</button>`).join("")}</div>` : "";
      const grid = tab === "ats" ? btn("ats_away", `${A} ${fmtLine(-mk.spread)}`) + btn("ats_home", `${H} ${fmtLine(mk.spread)}`)
        : tab === "ou" ? btn("over", "大分 " + mk.total) + btn("under", "小分 " + mk.total) : btn("away", "押 " + A) + btn("home", "押 " + H);
      const intl = !locked && ((tab === "ats" && !mk.spreadTw) || (tab === "ou" && !mk.totalTw)) ? `<div class="pick-note warn">台灣運彩還沒開這一種，先用國際盤的線</div>` : "";
      const hint = !locked && tab === "ats" ? `<div class="pick-note">${esc(atsHint(mk.spread, H, A))}</div>` : "";
      const extra = p && mine !== tab ? `<div class="pick-note">你押 ${esc(sideLabel(p))}${p.result ? (p.result.r === "win" ? "，對了" : p.result.r === "loss" ? "，沒中" : "，平手") : ""}</div>` : "";
      return `<div class="pickrow compact" data-pickrow="${esc(g.id)}" data-compact="1">${tabs}<div class="pick-grid">${grid}</div>${intl}${hint}${extra}</div>`;
    }
    const tag = (tw) => `<small class="src ${tw ? "tw" : "intl"}">${tw ? "台灣運彩" : "國際盤"}</small>`;
    const rows = [];
    const mlIntl = !mk.mlTw && ((g.odds || {}).dec_home || (g.odds || {}).dec_away);
    rows.push(`<div class="pick-label">誰會贏（不讓分）${mk.mlTw || mlIntl ? " " + tag(mk.mlTw) : ""}</div><div class="pick-grid">${btn("away", "我押 " + A)}${btn("home", "我押 " + H)}</div>`);
    const showP = (sides) => !locked || (p && sides.includes(p.side));
    if (mk.spread != null && showP(["ats_home", "ats_away"])) {
      rows.push(`<div class="pick-label">讓分 ${tag(mk.spreadTw)}</div><div class="pick-grid">${btn("ats_away", `${A} ${fmtLine(-mk.spread)}`)}${btn("ats_home", `${H} ${fmtLine(mk.spread)}`)}</div>`);
    }
    if (mk.total != null && showP(["over", "under"])) {
      rows.push(`<div class="pick-label">大小分 ${tag(mk.totalTw)}</div><div class="pick-grid">${btn("over", "大分 " + mk.total)}${btn("under", "小分 " + mk.total)}</div>`);
    }
    let note;
    if (post && p) note = p.result ? (p.result.r === "win" ? "你押對了！" : p.result.r === "loss" ? "這場沒中。" : "平手，不算。") : "打完了，等比分進來對答案。";
    else if (locked) note = p ? `已開打，鎖定你押的 ${sideLabel(p)}。` : "已開打，不能再選了。";
    else if (p) note = `你押 ${sideLabel(p)}${p.line_src === "國際盤" && p.side !== "home" && p.side !== "away" ? "（用國際盤的線）" : ""}，開打前都可以改，再點一次取消。`;
    else note = "你覺得誰會贏？點一下記下來，打完自動對答案。";
    const intlNote = !locked && ((mk.spread != null && !mk.spreadTw) || (mk.total != null && !mk.totalTw))
      ? `<div class="pick-note warn">台灣運彩還沒開這場的讓分或大小，先用國際盤的線；台灣運彩開了會自動換成台灣的線（大概 20 分鐘內）。</div>` : "";
    return `<div class="pickrow" data-pickrow="${esc(g.id)}" data-compact="0">${rows.join("")}<div class="pick-note">${esc(note)}</div>${intlNote}</div>`;
  }

  // ---------- 串關（過關）：至少 2 場、同一場不能串、賠率相乘、全中才有錢 ----------
  // 歐冠、歐盃：玩運彩還沒開盤時先用官方賽程列（代碼 el...），開盤後換成玩運彩那場；之前押的、串的搬過去
  function migrateIds() {
    let moved = false;
    (state.data.games || []).forEach((g) => {
      const old = g.alt_id;
      if (!old || old === g.id) return;
      if (state.picks[old] && !state.picks[g.id]) { state.picks[g.id] = state.picks[old]; delete state.picks[old]; moved = true; }
      state.parlays.forEach((x) => x.legs.forEach((l) => { if (l.gid === old) { l.gid = g.id; moved = true; } }));
    });
    if (moved) { savePicks(); saveParlays(); }
  }

  const PARLAY_KEY = "myparlays.v1";
  function loadParlays() { try { const x = JSON.parse(localStorage.getItem(PARLAY_KEY) || "[]"); return Array.isArray(x) ? x : []; } catch (_) { return []; } }
  function saveParlays() { try { localStorage.setItem(PARLAY_KEY, JSON.stringify(state.parlays)); } catch (_) { /* ignore */ } }
  state.parlays = loadParlays();
  state.slip = new Set();
  state.stake = 100;
  const TAX_LINE = 5000, MAX_LEGS = 8, MIN_STAKE = 100, MAX_STAKE = 100000;
  const pct = (p) => Math.round(p * 100) + "%";
  const yuan = (n) => Math.round(n).toLocaleString("en-US");
  const legLabel = (x) => (x.side === "home" || x.side === "away" ? `${x.side === "home" ? x.home : x.away} 不讓分` : sideLabel(x));
  function payout(stake, dec) {
    const pay = Math.floor(stake * dec + 1e-6);
    const tax = pay > TAX_LINE ? Math.round(pay * 0.2) : 0;   // 單注中獎超過 5,000 元，全額扣 20%
    return { pay, tax, net: pay - tax };
  }
  // 用現在台灣運彩的線和賠率做一個「串關的一場」；台灣運彩還沒開這個玩法就不能串
  function legOf(g, side) {
    const p = snapshotPick(g, side);
    if (p.line_src !== "台灣運彩" || !p.dec) return null;
    const probs = (g.suggestion || {}).probs || {};
    const x = { gid: g.id, side, home: p.home, away: p.away, league_zh: p.league_zh, chip: p.chip, day_tw: p.day_tw, time_tw: p.time_tw, start: p.start, spread_home: p.spread_home, total: p.total, dec: p.dec, p: probs[side] ?? null };
    x.label = legLabel(x);
    return x;
  }
  function packLegs(legs) {
    let dec = 1, p = 1;
    legs.forEach((x) => { dec *= x.dec; p = p == null || x.p == null ? null : p * x.p; });
    return { dec, p, ev: p == null ? null : p * dec };
  }
  function legResult(x) {
    const g = findGame(x.gid);
    let hs = null, as = null;
    if (g && g.status.state === "post") { hs = Number(g.home.score); as = Number(g.away.score); }
    else { const rr = state.results && state.results.results && state.results.results[x.gid]; if (rr) { hs = Number(rr[1]); as = Number(rr[2]); } }
    if (!Number.isFinite(hs) || !Number.isFinite(as)) return null;
    const r = judge(x.side, hs, as, x.total, x.spread_home);
    return r ? { r, hs, as } : null;
  }
  function settleParlays() {
    let changed = false;
    for (const pl of state.parlays) {
      if (pl.result) continue;
      let done = true;
      for (const x of pl.legs) {
        if (x.r) continue;
        const res = legResult(x);
        if (res) { x.r = res.r; x.hs = res.hs; x.as = res.as; changed = true; }
        else if (Date.now() - Date.parse(x.start) > 36 * 3600e3) { x.r = "void"; changed = true; }   // 取消或延期：當賠率 1 算
        else done = false;
      }
      const rs = pl.legs.map((x) => x.r);
      if (!done && !rs.includes("loss")) continue;   // 錯一場就整張沒了，不用等其他場
      let pay = 1;
      pl.legs.forEach((x) => { if (x.r === "win") pay *= x.dec; });
      pl.result = rs.includes("loss") ? { r: "loss", pay: 0 } : rs.every((r) => r === "push" || r === "void") ? { r: "push", pay: 1 } : { r: "win", pay };
      pl.result.settled_at = new Date().toISOString();
      changed = true;
    }
    if (changed) saveParlays();
    return changed;
  }
  function saveParlay(legs, stake, src, siteId) {
    const pk = packLegs(legs);
    state.parlays.push({ id: (src === "site" ? "s" : "m") + Date.now(), site_id: siteId || null, src, at: new Date().toISOString(), stake, dec: pk.dec, p: pk.p, legs: legs.map((x) => ({ ...x })) });
    saveParlays();
  }
  function legRow(x) {
    const g = findGame(x.gid);
    const r = x.r || (legResult(x) || {}).r;
    let st = "";
    if (r) st = `<span class="lr ${r}">${r === "win" ? "中" : r === "loss" ? "沒中" : r === "void" ? "取消" : "平"}</span>`;
    else if (g && g.status.state === "in") st = `<span class="lr live">${esc(g.away.score)}:${esc(g.home.score)}</span>`;
    const when = x.day_tw ? `${dayLabel(x.day_tw).name} ${x.time_tw || ""}` : "";
    const inner = `<div class="lg-2"><b>${esc(x.label)}</b><em>賠 ${Number(x.dec).toFixed(2)}</em>${x.p != null ? `<small>估 ${pct(x.p)}</small>` : ""}${st}</div><div class="lg-1">${esc(x.league_zh || "")} · ${esc(when)} · ${esc(x.away)} 對 ${esc(x.home)}</div>`;
    return g ? `<button class="leg" data-goto="${esc(x.gid)}">${inner}</button>` : `<div class="leg">${inner}</div>`;
  }
  // 網站推薦還沒鎖定前，跟著最新的台灣賠率走
  function siteLegs(cur) {
    return cur.legs.map((x) => {
      const g = findGame(x.gid);
      if (!cur.locked && g && !gameStarted(g)) { const nl = legOf(g, x.side); if (nl) return { ...x, dec: nl.dec, spread_home: nl.spread_home, total: nl.total, label: nl.label }; }
      return x;
    });
  }
  function siteParlayCard() {
    const P = state.data.parlay;
    if (!P) return "";
    const cur = P.current;
    if (!cur) return state.sport === "all" && P.note ? `<div class="day-title">今天最穩的 2 串 1</div><div class="parlay-card quiet"><p class="pl-note">${esc(P.note)}</p></div>` : "";
    if (state.sport !== "all" && !cur.legs.some((x) => x.chip === state.sport)) return "";
    const legs = siteLegs(cur);
    const pk = packLegs(legs);
    const py = payout(100, pk.dec);
    const saved = state.parlays.some((x) => x.site_id === cur.id);
    const anyStarted = legs.some((x) => { const g = findGame(x.gid); return g ? gameStarted(g) : Date.parse(x.start) <= Date.now(); });
    const btn = saved ? `<button class="pl-save on" disabled>${icon("i-check")}已記到「我的串關」</button>`
      : anyStarted ? "" : `<button class="pl-save" data-save-site="1">記下這組串關（押 100 元）</button>`;
    return `<div class="day-title">今天最穩的 2 串 1<small>兩場都中才有錢</small></div>
      <div class="parlay-card">
        <div class="legs">${legs.map(legRow).join("")}</div>
        <div class="pl-sum"><div><small>總賠率</small><b>${pk.dec.toFixed(2)}</b></div><div><small>兩場都中</small><b>${pk.p != null ? "約 " + pct(pk.p) : "–"}</b></div><div><small>押 100 元中了拿</small><b>${yuan(py.pay)} 元</b></div></div>
        <p class="pl-note">挑網站最有把握、賠率又不會太低的兩場（季前賽不串）。${pk.ev != null ? `長期來看每押 100 元大概拿回 ${Math.round(pk.ev * 100)} 元，運彩有抽水，當娛樂、小注就好。` : ""}${cur.locked ? "第一場快開打了，這組已經鎖定。" : "開打前 45 分鐘鎖定，在那之前可能因為盤口或傷兵換組合。"}</p>
        ${btn}
      </div>`;
  }
  function openForSlip() {
    const hid = hiddenSportKeys();
    return Object.entries(state.picks).map(([gid, p]) => ({ gid, p, g: findGame(gid) }))
      .filter((x) => x.g && !gameStarted(x.g) && !hid.has(chipOf(x.g)))
      .sort((a, b) => a.g.start.localeCompare(b.g.start));
  }
  const slipLegs = () => openForSlip().filter((x) => state.slip.has(x.gid)).map((x) => legOf(x.g, x.p.side)).filter(Boolean);
  function slipSummary() {
    const legs = slipLegs();
    if (legs.length < 2) return `<p class="pl-note">勾兩場以上才能串。同一場只能選一種玩法，你每場只押一種，剛好符合。</p>`;
    const pk = packLegs(legs), stake = state.stake, py = payout(stake, pk.dec);
    const notes = [];
    if (py.tax) notes.push(`超過 5,000 元要扣 20% 所得稅，實拿大約 ${yuan(py.net)} 元（領現金再扣 0.4% 印花稅，運彩會員線上領不扣）。`);
    if (pk.ev != null) notes.push(`長期來看每押 100 元大概拿回 ${Math.round(pk.ev * 100)} 元。`);
    else notes.push("有一場網站估不出機率（沒有盤口或資料太少），全中機率算不出來。");
    if (legs.length >= 3) notes.push("串越多越難中：每多一場，運彩就多抽一次。真的要串，2 串 1 最划算。");
    if (legs.length > MAX_LEGS) notes.push(`最多能串幾場以台灣運彩官網為準（常見是 ${MAX_LEGS} 場）。`);
    return `<div class="pl-sum"><div><small>總賠率</small><b>${pk.dec.toFixed(2)}</b></div><div><small>${legs.length} 場全中</small><b>${pk.p != null ? "約 " + pct(pk.p) : "–"}</b></div><div><small>中了拿</small><b>${yuan(py.pay)} 元</b></div></div>
      <p class="pl-note">${notes.map(esc).join("<br>")}</p>`;
  }
  // 金額改了只更新數字，按鈕不重畫（不然手機上一邊離開輸入框一邊按，會按不到）
  function updateSlip() {
    const sum = $("#slip-sum"), btn = $("#slip-save");
    if (sum) sum.innerHTML = slipSummary();
    if (btn) { const ok = slipLegs().length >= 2; btn.disabled = !ok; btn.textContent = ok ? `存成一張串關（押 ${yuan(state.stake)} 元）` : "勾兩場以上才能存"; }
  }
  function slipCard() {
    const open = openForSlip();
    [...state.slip].forEach((gid) => { if (!open.some((x) => x.gid === gid)) state.slip.delete(gid); });
    const msg = state.slipMsg ? `<div class="pl-ok">${icon("i-check")}${esc(state.slipMsg)}</div>` : "";
    state.slipMsg = "";
    if (!open.length) return msg + (state.sport === "all" ? `<div class="pl-hint">想自己串？先到每場的「你的預測」押好兩場以上，這裡就能勾起來算總賠率、全中的機率、扣稅後拿多少。</div>` : "");
    const rows = open.map(({ gid, p, g }) => {
      const leg = legOf(g, p.side);
      const on = !!leg && state.slip.has(gid);
      return `<button class="slip-row ${on ? "on" : ""}" data-slip="${esc(gid)}" ${leg ? "" : "disabled"}><span class="box">${on ? icon("i-check") : ""}</span><div class="grow"><div class="lg-2"><b>${esc(leg ? leg.label : legLabel(p))}</b>${leg ? `<em>賠 ${leg.dec.toFixed(2)}</em>${leg.p != null ? `<small>估 ${pct(leg.p)}</small>` : ""}` : `<small>台灣運彩還沒開盤，先不能串</small>`}</div><div class="lg-1">${esc(g.league_zh)} · ${esc(dayLabel(g.day_tw).name)} ${esc(g.time_tw)} · ${esc(tname(g.away))} 對 ${esc(tname(g.home))}</div></div></button>`;
    }).join("");
    return `${msg}<div class="day-title">串關試算<small>用你押的場次，勾起來算</small></div>
      <div class="parlay-card"><div class="slip-list">${rows}</div>
        <div class="stake"><span>押</span><button data-stake="-100" aria-label="少 100 元">−</button><input id="slip-stake" type="number" inputmode="numeric" min="${MIN_STAKE}" max="${MAX_STAKE}" step="10" value="${state.stake}"><button data-stake="100" aria-label="多 100 元">＋</button><span>元</span></div>
        <div id="slip-sum">${slipSummary()}</div>
        <button class="pl-save" id="slip-save" data-save-slip="1" ${slipLegs().length >= 2 ? "" : "disabled"}>${slipLegs().length >= 2 ? `存成一張串關（押 ${yuan(state.stake)} 元）` : "勾兩場以上才能存"}</button></div>`;
  }
  function renderParlay() {
    const el = $("#parlay");
    if (!el || !state.data) return;
    el.innerHTML = isTodayView() ? siteParlayCard() + slipCard() : "";
  }
  function setStake(v) {
    const n = Math.round(Number(v) / 10) * 10;
    if (!Number.isFinite(n)) return;
    state.stake = Math.min(MAX_STAKE, Math.max(MIN_STAKE, n));
  }
  function parlaySection() {
    const L = state.parlays.slice().sort((a, b) => b.at.localeCompare(a.at));
    if (!L.length) return "";
    const done = L.filter((x) => x.result && x.result.r !== "push");
    const w = done.filter((x) => x.result.r === "win").length;
    const money = done.reduce((acc, x) => acc + (x.result.r === "win" ? Math.floor(x.stake * x.result.pay) - x.stake : -x.stake), 0);
    const wait = L.filter((x) => !x.result).length;
    const tiles = `<div class="stat-grid"><div class="stat"><div class="sl">串關</div><b>${w} 中 ${done.length - w} 沒中</b><small>${wait ? `還有 ${wait} 張等結果` : `共 ${L.length} 張`}</small></div><div class="stat"><div class="sl">照你押的金額算</div><b class="${money >= 0 ? "good" : "bad"}">${money >= 0 ? "+" : "−"}${yuan(Math.abs(money))} 元</b><small>還沒扣稅</small></div></div>`;
    const rows = L.slice(0, 20).map((x) => {
      const r = x.result;
      const cls = !r ? "push" : r.r === "win" ? "win" : r.r === "loss" ? "loss" : "push";
      const mark = !r ? "等" : r.r === "win" ? "中" : r.r === "loss" ? "錯" : "平";
      const legsTxt = x.legs.map((l) => `${l.r === "win" ? "✓ " : l.r === "loss" ? "✗ " : l.r ? "－ " : "・ "}${esc(l.label)}${l.r === "void" ? "（取消，當賠率 1）" : ""}`).join("<br>");
      const sc = r ? (r.r === "win" ? `+${yuan(Math.floor(x.stake * r.pay) - x.stake)}` : r.r === "loss" ? `−${yuan(x.stake)}` : "退回") : `押 ${yuan(x.stake)}`;
      const del = r ? "" : `<button class="pl-del" data-del-parlay="${esc(x.id)}">刪掉</button>`;
      return `<div class="rec"><span class="mark ${cls}">${mark}</span><div><div class="t1">${x.legs.length} 串 1 · 總賠率 ${Number(x.dec).toFixed(2)}${x.src === "site" ? " · 照網站推薦" : ""}</div><div class="t2">${legsTxt}</div></div><div class="sc">${esc(sc)}<small>${esc(x.at.slice(5, 10).replace("-", "/"))}</small>${del}</div></div>`;
    }).join("");
    return `<div class="grp">我的串關</div>${tiles}<div class="list">${rows}</div>`;
  }

  const hiddenSportKeys = () => new Set((state.data.sports || []).filter((s) => s.hidden).map((s) => s.key));
  function gamesForSport() {
    const g = state.data.games || [];
    if (state.sport === "all") { const hid = hiddenSportKeys(); return g.filter((x) => !hid.has(chipOf(x))); }
    return g.filter((x) => chipOf(x) === state.sport);
  }
  const findGame = (id) => (state.data.games || []).find((x) => x.id === id);

  // ---------- 文字：講人話 ----------
  function talkOf(g) {
    const s = g.suggestion || {};
    if (s.talk) return s.talk;
    const story = s.story || [];
    return { verdict: story[0] || s.summary || "資料整理中。", why: story.slice(1, 4), care: [], odds: "" };
  }
  function firstSentence(x) {
    if (!x) return "";
    const i = x.indexOf("。");
    return i > 0 ? x.slice(0, i + 1) : x;
  }
  function verdictPill(g) {
    const s = g.suggestion || {};
    if (g.status.state === "post") {
      const gr = g.graded;
      if (gr && gr.r) {
        const ok = gr.r === "win", bad = gr.r === "loss";
        const what = gr.play === "大小分" ? `玩 ${esc(gr.pick_label)}${gr.total_line != null ? " " + gr.total_line : ""}` : `押 ${esc(gr.pick_label)} · ${esc(gr.play)}${gr.play === "讓分" && gr.ats_line != null ? " " + fmtLine(gr.ats_line) : ""}`;
        return `<span class="pill post ${ok ? "hit" : bad ? "miss" : ""}">${ok ? icon("i-check") : ""}網站${what}</span><span class="conf ${ok ? "hit" : bad ? "miss" : ""}">${ok ? "對了" : bad ? "沒中" : "平手"}</span>`;
      }
      return `<span class="pill post">打完了</span>`;
    }
    if (s.play === "大小分" && s.pick) { const tt = s.totals || {}; const line = tt.line_tw ?? tt.line; return `<span class="pill">${icon("i-star")}玩 ${esc(s.pick_label)}${line != null ? " " + line : ""}</span><span class="conf">信心${esc(s.confidence)}</span>`; }
    if (s.pick) return `<span class="pill">${icon("i-star")}押 ${esc(s.pick_label)} · ${esc(s.play)}</span><span class="conf">信心${esc(s.confidence)}</span>`;
    if (!g.odds || g.odds.prob_home == null) return `<span class="pill wait">還沒開盤</span>`;
    return `<span class="pill wait">先不下</span>`;
  }
  // 第二選擇：主推之外另一個也值得考慮的玩法（沒有就不顯示）
  function altPill(g) {
    const a = (g.suggestion || {}).alt;
    if (!a || g.status.state !== "pre") return "";
    const what = a.play === "大小分" ? `玩 ${esc(a.pick_label)} ${a.line}` : a.play === "讓分" ? `押 ${esc(a.pick_label)} ${fmtLine(a.line)}` : `押 ${esc(a.pick_label)} 不讓分`;
    return `<span class="pill alt">第二選擇 · ${what}</span>`;
  }
  function twLine(g) {
    const tw = g.tw;
    if (!tw) return (g.notes && g.notes.tw) || "";
    const ml = tw.ml || {}, sp = tw.spread || {}, tt = tw.total || {};
    const parts = [];
    if (ml.home != null || ml.away != null) parts.push(`不讓分 ${num(ml.away)} / ${num(ml.home)}`);
    if (sp.line) parts.push(`讓分 ${esc(sp.line)}`);
    if (tt.line != null) parts.push(`大小 ${tt.line}`);
    return parts.length ? "台灣運彩 · " + parts.join(" · ") : "";
  }
  function whenText(g) {
    const a = `data-when="${esc(g.id)}"`;
    if (g.status.state === "in") return `<span class="g-when live" ${a}>${esc(g.status.detail)}</span>`;
    if (g.status.state === "post") return `<span class="g-when" ${a}>已結束</span>`;
    return `<span class="g-when" ${a}>${esc(dayLabel(g.day_tw).name)} ${esc(g.time_tw)}</span>`;
  }
  function teamCol(t, side, g) {
    const bits = [];
    if (t.record) bits.push(esc(t.record));
    if (t.rank_note) bits.push(esc(t.rank_note.replace("B.LEAGUE ", "").replace(" 名", "").replace("第 ", "第")));
    else if (t.last10) bits.push("近況 " + esc(t.last10));
    const tag = g.sets || g.tennis ? "" : `<span class="badge muted">${side === "home" ? "主" : "客"}</span>`;
    return `<div class="g-team">${logoImg(t)}<b>${esc(tname(t))}</b><small>${bits.join(" · ") || "&nbsp;"}</small>${tag}</div>`;
  }
  function midCol(g) {
    const hasScore = (g.status.state === "in" || g.status.state === "post") && (g.home.score != null || g.away.score != null);
    const a = `data-mid="${esc(g.id)}"`;
    if (hasScore) return `<div class="g-mid ${g.status.state === "in" ? "is-live" : ""}" ${a}><div class="score">${esc(g.away.score ?? "")} : ${esc(g.home.score ?? "")}</div><div class="sub">${g.sets ? "局數" : esc(g.status.detail)}</div></div>`;
    return `<div class="g-mid" ${a}><div class="vs">對</div><div class="sub">${esc(g.time_tw)}</div></div>`;
  }

  // ---------- 比賽卡片 ----------
  function gameCard(g) {
    const live = g.status.state === "in", post = g.status.state === "post";
    const s = g.suggestion || {};
    const t = talkOf(g);
    const strong = s.pick && s.confidence === "高" && !post;
    return `<div class="g-wrap"><button class="g ${live ? "is-live" : ""} ${post ? "is-post" : ""} ${strong ? "strong" : ""}" data-goto="${esc(g.id)}">
      <div class="g-top"><span>${icon(SPORT_ICON[chipOf(g)] || "i-grid")} <b>${esc(g.league_zh)}</b>${g.round ? " · " + esc(g.round) : ""}</span>${whenText(g)}</div>
      <div class="g-teams">${teamCol(g.away, "away", g)}${midCol(g)}${teamCol(g.home, "home", g)}</div>
      <div class="g-verdict">${verdictPill(g)}${altPill(g)}</div>
      ${!post ? `<div class="g-why">${esc(firstSentence(aiBody(g)[0]) || firstSentence((t.ai || [])[0]) || firstSentence(t.fan) || (t.why || [])[0] || t.verdict)}</div>` : ""}
      ${twLine(g) ? `<div class="g-odds">${twLine(g)}</div>` : g.far ? `<div class="g-odds">台灣運彩還沒開盤，傷兵名單也還沒出來，先看看就好</div>` : ""}
      <div class="g-tap">點一下看詳細 ${icon("i-chev")}</div>
    </button>${pickButtons(g, true)}</div>`;
  }

  // ---------- 畫面 ----------
  function render() {
    const d = state.data;
    document.body.dataset.sport = state.sport;
    $("#hdr-date").textContent = `${dayLabel(todayTW()).sub} · ${ago(d.generated_ts)}`;
    $("#foot-src").textContent = `資料來源：${d.source || "ESPN"}　｜　更新時間 ${String(d.generated_at || "").replace("T", " ").slice(0, 16)}`;
    if (!state.day || !dayList().includes(state.day)) state.day = todayTW();
    renderChips();
    renderDays();
    renderPicks();
    renderParlay();
    renderGames();
    renderInjuries();
    renderHot();
    renderStandings();
    renderRecord();
    renderSheet();
  }

  // ---------- 成績單 ----------
  function segTabs() {
    const n = Object.keys(state.picks).length;
    return `<div class="seg"><button data-rec="site" class="${state.recTab === "site" ? "on" : ""}">網站的建議</button><button data-rec="mine" class="${state.recTab === "mine" ? "on" : ""}">我的預測${n ? ` <span class="n">${n}</span>` : ""}</button></div>`;
  }
  function modelBlock(rec) {
    const m = rec && rec.model;
    if (!m) return "";
    const hid = hiddenSportKeys();
    const o = m.overall || {};
    const tile = (label, b) => `<div class="stat"><div class="sl">${esc(label)}</div><b>${b.n ? `模型 ${b.model_rate}%　盤口 ${b.mkt_rate}%` : "還沒有"}</b><small>${b.n ? `${b.n} 場 · Brier 模型 ${b.model_brier} / 盤口 ${b.mkt_brier}${b.disagree ? ` · 意見不同 ${b.disagree} 場：模型對 ${b.disagree_model_right}、盤口對 ${b.disagree_mkt_right}` : ""}` : (m.pending ? `${m.pending} 場等結果` : "等比賽打完")}</small></div>`;
    const leagues = Object.keys(m.by_league || {}).filter((k) => !hid.has(k));
    const fs = (m.factors || []).filter((f) => f.n);
    const word = (f) => f.verdict === "有幫助" ? "加進去比較準" : f.verdict === "反而變差" ? "加進去反而不準" : "看不出差別";
    const factorHtml = `<div class="grp">每個因素有沒有用（加了跟沒加，哪個比較準）</div>
      <div class="explain">每一場都分開算：有算這個因素、沒算這個因素，打完看哪個比較接近結果。場數到 30 場以上才看得準，沒用的因素之後會拿掉。</div>
      <div class="list">${(m.factors || []).map((f) => `<div class="item"><div class="grow"><div class="pn">${esc(f.label)}</div><div class="ps">${f.n ? `${word(f)}：有算 ${f.with_}、沒算 ${f.without}（越低越準），${f.n} 場裡 ${f.better} 場有算的比較準` : "還沒有打完的比賽用到它"}</div></div><span class="badge ${f.verdict === "有幫助" ? "ok" : f.verdict === "反而變差" ? "out" : "muted"}">${f.n ? esc(f.verdict) : "等資料"}</span></div>`).join("")}</div>`;
    const ai = rec.ai;
    const aiTile = ai && ai.n ? `<div class="grp">AI 的看法準不準（近 ${ai.days} 天）</div><div class="stat-grid"><div class="stat"><div class="sl">AI 看好的</div><b>${ai.hit}/${ai.n}</b><small>命中 ${Math.round(ai.hit / ai.n * 100)}%${ai.pending ? ` · 還有 ${ai.pending} 場等結果` : ""}</small></div><div class="stat"><div class="sl">同樣這些場</div><b>網站 ${ai.n_ours ? Math.round(ai.ours_hit / ai.n_ours * 100) + "%" : "–"}　盤口 ${ai.n_mkt ? Math.round(ai.mkt_hit / ai.n_mkt * 100) + "%" : "–"}</b><small>網站的計算 ${ai.ours_hit}/${ai.n_ours}、盤口 ${ai.mkt_hit}/${ai.n_mkt}</small></div></div>` : "";
    const L = rec.learn;
    const learnHtml = L ? `<div class="grp">網站自己學的分量</div><div class="explain">${L.lines ? `拿最近 90 天打完的 ${L.n} 場籃球，試每個因素乘幾倍預測最準（場數少的不太動）。預測準度 ${L.brier_before} → ${L.brier_after}（越低越準）。` : esc(L.note || "")}</div>${L.lines ? `<div class="list">${L.lines.map((x) => `<div class="item"><div class="grow"><div class="pn">${esc(x.label)}</div><div class="ps">${x.n} 場用到它</div></div><span class="badge ${x.w > 1.05 ? "ok" : x.w < 0.95 ? "out" : "muted"}">×${x.w}</span></div>`).join("")}</div>` : ""}` : "";
    return `${aiTile}${fs.length || (m.factors || []).length ? factorHtml : ""}${learnHtml}<div class="grp">我們的分析 vs 盤口（對照組，近 ${m.days} 天）</div>
      <div class="explain">網站的建議只看兩隊實力、近況、傷兵、休息、交手、手感、戰意，不看賠率；盤口只拿來當對照組，看我們長期比它準還是不準。Brier 分數越低越準，0.25 等於丟銅板。</div>
      <div class="stat-grid">${tile("全部", o)}${leagues.map((k) => tile((state.data.sports || []).find((s) => s.key === k)?.label || k, m.by_league[k])).join("")}</div>`;
  }
  function renderRecord() {
    const el = $("#record");
    if (state.recTab === "mine") { el.innerHTML = segTabs() + renderMine(); return; }
    const rec = state.data.record;
    if (!rec || !rec.settled) {
      el.innerHTML = segTabs() + `<div class="empty">還沒有對過答案的建議。從 ${esc((rec && rec.since) || "今天")} 開始記，比賽打完就會出現在這裡。${rec && rec.pending ? `目前有 ${rec.pending} 場等結果。` : ""}</div>` + modelBlock(rec);
      return;
    }
    const o = rec.overall;
    const hid = hiddenSportKeys();
    const conf = rec.by_conf || {};
    const hi = conf["高"];
    const tiles = [
      `<div class="stat"><div class="sl">近 ${rec.days} 天建議（已結算）</div><b>${o.n} 場</b><small>還有 ${rec.pending} 場等結果</small></div>`,
      `<div class="stat"><div class="sl">不讓分 押對幾場</div><b>${o.ml_w} 勝 ${o.ml_l} 敗</b><small>${o.ml_rate != null ? "命中 " + o.ml_rate + "%" : ""}</small></div>`,
      `<div class="stat"><div class="sl">讓分 過盤</div><b>${o.ats_w} 過 ${o.ats_l} 沒過</b><small>${o.ats_rate != null ? "過盤率 " + o.ats_rate + "%（52.4% 以上才算贏錢）" : "還沒有讓分資料"}</small></div>`,
      `<div class="stat"><div class="sl">大小分（當主建議的）</div><b>${o.tot_w || 0} 對 ${o.tot_l || 0} 錯</b><small>${o.tot_rate != null ? "命中 " + o.tot_rate + "%" : "還沒推過大小分"}${o.ou_rate != null ? " · 含附帶看法 " + o.ou_w + "-" + o.ou_l : ""}</small></div>`,
    ];
    const pr = rec.parlay;
    if (pr && pr.n) tiles.push(`<div class="stat"><div class="sl">推薦的 2 串 1</div><b>${pr.w} 中 ${pr.l} 沒中</b><small>每組押 100 元：${pr.money >= 0 ? "+" : "−"}${Math.abs(pr.money)} 元</small></div>`);
    if (hi) tiles.push(`<div class="stat"><div class="sl">信心「高」的建議</div><b>${hi.ml_w} 勝 ${hi.ml_l} 敗</b><small>${hi.ats_w + hi.ats_l ? "讓分過盤 " + hi.ats_w + "-" + hi.ats_l : ""}</small></div>`);
    const leagues = Object.keys(rec.by_league || {}).filter((k) => !hid.has(k));
    const lgRows = leagues.map((k) => { const b = rec.by_league[k]; const label = (state.data.sports || []).find((s) => s.key === k)?.label || k; return `<div class="stat"><div class="sl">${esc(label)}</div><b>${b.ml_w} 勝 ${b.ml_l} 敗</b><small>${b.ats_w + b.ats_l ? "讓分 " + b.ats_w + "-" + b.ats_l : ""}${b.ou_w + b.ou_l ? " · 大小 " + b.ou_w + "-" + b.ou_l : ""}</small></div>`; }).join("");
    const list = (rec.recent || []).filter((r) => state.sport === "all" ? !hid.has(r.chip) : r.chip === state.sport).map((r) => {
      const totalsMain = r.play === "大小分";
      const main = totalsMain ? r.ou : r.ml;
      const cls = main === "win" ? "win" : main === "loss" ? "loss" : "push";
      const mark = main === "win" ? "對" : main === "loss" ? "錯" : "平";
      const bits = [];
      if (!totalsMain && r.ats) bits.push(`讓分${r.line != null ? "（" + (r.line > 0 ? "+" : "") + r.line + "）" : ""}${r.ats === "win" ? "過" : r.ats === "loss" ? "沒過" : "平"}`);
      if (!totalsMain && r.ou) bits.push(`大小看${esc(r.total_lean)} ${r.ou === "win" ? "對" : "錯"}`);
      if (totalsMain && r.total_line != null) bits.push(`盤口 ${r.total_line}，打了 ${r.as_ + r.hs} 分`);
      return `<button class="rec" data-goto="${esc(r.id)}"><span class="mark ${cls}">${mark}</span><div><div class="t1">${totalsMain ? "玩 " + esc(r.pick_label) : "押 " + esc(r.pick_label) + " · " + esc(r.play)}${r.confidence ? " · 信心" + esc(r.confidence) : ""}</div><div class="t2">${esc(r.league_zh)} ${esc(r.day_tw.slice(5))} · ${esc(r.away)} 對 ${esc(r.home)}${bits.length ? " · " + bits.join("，") : ""}</div>${r.review ? `<div class="t3">錯在哪：${esc(r.review)}</div>` : ""}</div><div class="sc">${r.as_}:${r.hs}<small>${r.dec ? "賠 " + Number(r.dec).toFixed(2) : ""}</small></div></button>`;
    }).join("");
    const rv = rec.reviews;
    const rvHtml = rv && rv.n ? `<div class="grp">押錯的 ${rv.n} 場，錯在哪</div><div class="explain">每場押錯都回頭看：差一點的算運氣；差很多的是實力看錯；因為某個因素才押這邊的，就記那個因素，網站之後會少信它一點。</div>
      <div class="stat-grid">${rv.kinds.map((k) => `<div class="stat"><div class="sl">${esc(k.label)}</div><b>${k.n} 場</b></div>`).join("")}</div>${rv.factors.length ? `<div class="explain">因為這些因素押錯：${rv.factors.map((f) => `${esc(f.label)} ${f.n} 場`).join("、")}</div>` : ""}` : "";
    el.innerHTML = segTabs() + `<div class="explain">每次建議都先記下來，比賽打完對答案，不改分。</div>
      <div class="stat-grid">${tiles.join("")}</div>${lgRows ? `<div class="grp">各聯盟</div><div class="stat-grid">${lgRows}</div>` : ""}${rvHtml}
      ${modelBlock(rec)}
      <div class="grp">最近對過答案的</div><div class="list">${list || `<div class="empty">這個球種還沒有結算的建議。</div>`}</div>`;
  }
  function renderMine() {
    const hid = hiddenSportKeys();
    const all = Object.entries(state.picks).map(([id, p]) => ({ id, ...p })).filter((p) => state.sport === "all" ? !hid.has(p.chip) : p.chip === state.sport);
    const tools = `<div class="tools"><button class="more" data-export>備份（下載檔案）</button><label class="more">匯入備份<input type="file" id="pick-import" accept="application/json,.json" hidden></label>${all.length || state.parlays.length ? `<button class="more danger" data-clear-picks>清掉全部</button>` : ""}</div>
      <div class="explain">預測記在這支手機的瀏覽器裡，換手機或清資料會不見，記得偶爾備份。</div>`;
    if (!all.length) return parlaySection() + `<div class="empty">還沒有預測。到「今天」隨便點一場，按「押 某隊」就記下來了，打完會自動對答案。</div>` + tools;
    const settled = all.filter((p) => p.result && p.result.r !== "push").sort((a, b) => b.start.localeCompare(a.start));
    const pending = all.filter((p) => !p.result).sort((a, b) => a.start.localeCompare(b.start));
    const w = settled.filter((p) => p.result.r === "win").length, l = settled.length - w;
    const rate = settled.length ? Math.round(w / settled.length * 100) : null;
    // 連中
    const asc = settled.slice().sort((a, b) => a.start.localeCompare(b.start));
    let cur = 0, best = 0, run = 0;
    asc.forEach((p) => { if (p.result.r === "win") { run++; best = Math.max(best, run); } else run = 0; });
    cur = run;
    // 每場 100 元
    const withDec = settled.filter((p) => p.dec);
    const money = withDec.reduce((acc, p) => acc + (p.result.r === "win" ? (p.dec - 1) * 100 : -100), 0);
    // 跟網站比
    const both = settled.filter((p) => p.result.site && p.result.site !== "push");
    const agree = both.filter((p) => p.side === p.site_pick);
    const dis = both.filter((p) => p.side !== p.site_pick);
    const youRight = dis.filter((p) => p.result.r === "win").length, siteRight = dis.filter((p) => p.result.site === "win").length;
    const agreeHit = agree.filter((p) => p.result.r === "win").length;
    // 習慣
    const sides = settled.filter((p) => p.side === "home" || p.side === "away");
    const homeP = sides.filter((p) => p.side === "home"), awayP = sides.filter((p) => p.side === "away");
    const hitOf = (lst) => lst.length ? `${lst.filter((p) => p.result.r === "win").length}/${lst.length}` : "–";
    const favP = sides.filter((p) => p.prob != null && p.prob >= 0.5), dogP = sides.filter((p) => p.prob != null && p.prob < 0.5);
    const atsP = settled.filter((p) => p.side === "ats_home" || p.side === "ats_away"), ouP = settled.filter((p) => p.side === "over" || p.side === "under");
    const tiles = [
      `<div class="stat"><div class="sl">對過答案的</div><b>${w} 對 ${l} 錯</b><small>${rate != null ? `命中 ${rate}%` : ""}${pending.length ? ` · 還有 ${pending.length} 場等結果` : ""}</small></div>`,
      `<div class="stat"><div class="sl">連中</div><b>現在 ${cur} 場</b><small>最長 ${best} 場</small></div>`,
      `<div class="stat"><div class="sl">如果每場下 100 元</div><b class="${money >= 0 ? "good" : "bad"}">${money >= 0 ? "+" : ""}${Math.round(money)} 元</b><small>${withDec.length ? `照你押的時候的賠率算，${withDec.length} 場` : "要有賠率才算得出來"}</small></div>`,
      `<div class="stat"><div class="sl">跟網站意見不同時</div><b>你對 ${youRight}　網站對 ${siteRight}</b><small>${dis.length ? `${dis.length} 場意見不同` : "還沒有意見不同的場次"}${agree.length ? ` · 一致的 ${agree.length} 場中 ${agreeHit}` : ""}</small></div>`,
      `<div class="stat"><div class="sl">押主隊 / 押客隊</div><b>${hitOf(homeP)} / ${hitOf(awayP)}</b><small>你押主隊 ${homeP.length} 次、客隊 ${awayP.length} 次</small></div>`,
      `<div class="stat"><div class="sl">押熱門 / 押冷門</div><b>${hitOf(favP)} / ${hitOf(dogP)}</b><small>熱門是網站看好那隊</small></div>`,
      `<div class="stat"><div class="sl">不讓分 / 讓分 / 大小分</div><b>${hitOf(sides)} / ${hitOf(atsP)} / ${hitOf(ouP)}</b><small>你哪一種玩法比較準</small></div>`,
    ];
    const byLg = {};
    settled.forEach((p) => { (byLg[p.league_zh] = byLg[p.league_zh] || []).push(p); });
    const lgRows = Object.entries(byLg).map(([k, lst]) => `<div class="stat"><div class="sl">${esc(k)}</div><b>${hitOf(lst)}</b><small>命中 ${Math.round(lst.filter((p) => p.result.r === "win").length / lst.length * 100)}%</small></div>`).join("");
    const row = (p, kind) => {
      const r = p.result;
      const cls = !r ? "push" : r.r === "win" ? "win" : r.r === "loss" ? "loss" : "push";
      const mark = !r ? "等" : r.r === "win" ? "對" : r.r === "loss" ? "錯" : "平";
      const site = p.site_label ? `網站${p.site_play === "大小分" ? "玩" : "押"} ${esc(p.site_label)}${r && r.site ? (r.site === "win" ? " 對" : r.site === "loss" ? " 錯" : " 平") : ""}` : "網站沒建議";
      return `<button class="rec" data-goto="${esc(p.id)}"><span class="mark ${cls}">${mark}</span><div><div class="t1">你押 ${esc(sideLabel(p))}${p.dec ? ` <small>賠 ${Number(p.dec).toFixed(2)}</small>` : ""}${p.line_src === "國際盤" && p.side !== "home" && p.side !== "away" ? ` <small>國際盤的線</small>` : ""}</div><div class="t2">${esc(p.league_zh)} ${esc(p.day_tw.slice(5))} ${esc(p.time_tw)} · ${esc(p.away)} 對 ${esc(p.home)} · ${site}</div></div><div class="sc">${r ? `${r.as}:${r.hs}` : (kind === "pending" && Date.parse(p.start) > Date.now() ? "還沒打" : "等比分")}</div></button>`;
    };
    return `<div class="stat-grid">${tiles.join("")}</div>${lgRows ? `<div class="grp">各聯盟</div><div class="stat-grid">${lgRows}</div>` : ""}
      ${parlaySection()}
      ${pending.length ? `<div class="grp">等結果的（${pending.length}）</div><div class="list">${pending.slice(0, 20).map((p) => row(p, "pending")).join("")}</div>` : ""}
      ${settled.length ? `<div class="grp">對過答案的</div><div class="list">${settled.slice(0, 40).map((p) => row(p, "done")).join("")}</div>` : ""}
      ${tools}`;
  }

  function renderChips() {
    const all = (state.data.games || []).filter((g) => g.day_tw === state.day || (isTodayView() && g.status.state === "in"));
    const sports = state.data.sports || [];
    const hiddenKeys = new Set(sports.filter((s) => s.hidden).map((s) => s.key));
    const counts = {};
    all.forEach((g) => { counts[chipOf(g)] = (counts[chipOf(g)] || 0) + 1; });
    const visible = sports.filter((s) => !s.hidden || state.showMore || state.sport === s.key);
    const mainCount = all.filter((g) => !hiddenKeys.has(chipOf(g))).length;
    $("#chips").innerHTML = visible.map((s) => {
      const n = s.key === "all" ? mainCount : counts[s.key] || 0;
      return `<button class="chip ${state.sport === s.key ? "on" : ""}" data-sport="${s.key}">${icon(SPORT_ICON[s.key] || "i-grid")}${esc(s.label)}<span class="n">${n}</span></button>`;
    }).join("") + (hiddenKeys.size ? `<button class="chip more-chip" data-more-sports="1">${state.showMore ? "收起" : "其他球種"}</button>` : "");
  }

  function renderDays() {
    const el = $("#days");
    if (!el) return;
    const counts = {};
    gamesForSport().forEach((g) => { counts[g.day_tw] = (counts[g.day_tw] || 0) + 1; });
    el.innerHTML = dayList().map((d) => {
      return `<button class="day ${state.day === d ? "on" : ""}" data-day="${d}"><b>${esc(dayName(d))}</b><small>${esc(d.slice(5).replace("-", "/"))} ${esc(weekOf(d).slice(1))}</small><span class="n">${counts[d] || 0} 場</span></button>`;
    }).join("");
  }
  function topPicks() {
    const order = { 高: 0, 中: 1, 低: 2 };
    const dec = (g) => { const side = g.suggestion.pick; if (g.suggestion.play === "大小分") { const tt = g.tw && g.tw.total; return tt ? (side === "over" ? tt.over : tt.under) || null : null; } const ml = g.tw && g.tw.ml; return (ml && ml[side]) || (g.odds && g.odds["dec_" + side]) || null; };
    const soon = Date.now() + 30 * 3600e3;
    const inDay = (g) => isTodayView() ? Date.parse(g.start) <= soon : g.day_tw === state.day;
    return gamesForSport()
      .filter((g) => inDay(g) && g.suggestion && g.suggestion.pick && g.status.state !== "post" && !(dec(g) != null && dec(g) < 1.2))
      .sort((a, b) => {
        const c = order[a.suggestion.confidence] - order[b.suggestion.confidence];
        if (c) return c;
        const pOf = (g) => g.suggestion.prob ?? Math.max(g.odds?.prob_home || 0, g.odds?.prob_away || 0);
        return pOf(b) - pOf(a);
      });
  }
  function renderPicks() {
    const el = $("#picks");
    // 昨天：網站推薦的對了幾場
    if (state.day < todayTW()) {
      const gr = gamesForSport().filter((g) => g.day_tw === state.day && g.graded && g.graded.r);
      const w = gr.filter((g) => g.graded.r === "win").length, l = gr.filter((g) => g.graded.r === "loss").length;
      el.innerHTML = gr.length ? `<div class="day-sum"><b>${esc(dayName(state.day))}網站推薦 ${gr.length} 場：對 ${w}、錯 ${l}</b><small>每一場下面有寫網站當時押什麼、對不對；你自己押的也會顯示。</small></div>` : "";
      return;
    }
    const picks = topPicks().slice(0, 3);
    if (!picks.length) { el.innerHTML = ""; return; }
    const title = `${dayName(state.day)}最有把握的`;
    const far = !isTodayView() && picks.some((g) => g.far);
    el.innerHTML = `<div class="day-title">${esc(title)} ${picks.length} 場<small>${far ? "還沒開盤，先參考" : "先看這裡"}</small></div><div class="cards">${picks.map(gameCard).join("")}</div>`;
  }
  function renderGames() {
    const all = gamesForSport();
    const el = $("#games");
    const live = isTodayView() ? all.filter((g) => g.status.state === "in") : [];
    const rest = all.filter((g) => g.status.state !== "in" && g.day_tw === state.day);
    const farNote = state.day > addDays(todayTW(), 1) && rest.some((g) => g.status.state === "pre")
      ? `<div class="pl-hint">這天的比賽還早：台灣運彩的盤口、傷兵名單通常前一兩天才出來，現在只能看近況和對戰，正式建議等近一點再看。</div>` : "";
    if (!live.length && !rest.length) { el.innerHTML = `<div class="empty">${esc(dayName(state.day))}（${esc(state.day.slice(5).replace("-", "/"))}）這個球種沒有比賽。</div>`; return; }
    const sortGames = (list) => list.sort((a, b) => (a.status.state === "post") - (b.status.state === "post") || a.start.localeCompare(b.start));
    let html = "";
    if (live.length) html += `<div class="day-title live">${icon("i-live")} 進行中<small>${live.length} 場</small></div><div class="cards">${live.map(gameCard).join("")}</div>`;
    const byDay = {};
    rest.forEach((g) => { (byDay[g.day_tw] = byDay[g.day_tw] || []).push(g); });
    html += Object.keys(byDay).sort().map((day) => {
      const dl = dayLabel(day);
      const list = sortGames(byDay[day]);
      return `<div class="day-title">${esc(dayName(day))}的比賽<small>${esc(dl.sub)} · ${list.length} 場</small></div><div class="cards">${list.map(gameCard).join("")}</div>`;
    }).join("");
    el.innerHTML = farNote + html;
  }

  function renderInjuries() {
    const hid = hiddenSportKeys();
    const feed = (state.data.injury_feed || []).filter((x) => state.sport === "all" ? !hid.has(chipOf(x)) : chipOf(x) === state.sport);
    const el = $("#injuries");
    if (!feed.length) { el.innerHTML = `<div class="empty">今明兩天的比賽沒有傷兵消息。</div>`; return; }
    const list = state.showAllInj ? feed : feed.slice(0, 10);
    el.innerHTML = list.map((x) => `<button class="item" data-goto="${esc(x.game_id)}">${x.severity === "news" ? `<span class="avatar fallback">${icon("i-news")}</span>` : avatarImg(x)}<div class="grow"><div class="pn">${esc(x.player)} ${x.key ? `<span class="badge vio">主力</span>` : ""}</div>
      <div class="ps">${x.team_logo ? `<img src="${esc(x.team_logo)}" alt="">` : ""}${esc(x.team)}${x.position ? " · " + esc(x.position) : ""}${x.ppg != null ? ` · 場均 ${Number(x.ppg).toFixed(1)} 分` : ""}${x.detail ? " · " + esc(x.detail) : ""} · ${esc(dayLabel(x.day_tw).name)} ${esc(x.time_tw)}</div></div>
      <span class="badge ${sevClass(x.severity)}">${esc(x.status_zh)}</span></button>`).join("") +
      (feed.length > 10 ? `<button class="more" data-more="inj">${state.showAllInj ? "收起" : `還有 ${feed.length - 10} 筆，點開看全部`}</button>` : "");
  }
  function renderHot() {
    const hid = hiddenSportKeys();
    const hot = (state.data.hot_players || []).filter((x) => state.sport === "all" ? !hid.has(chipOf(x)) : chipOf(x) === state.sport);
    const el = $("#hot");
    if (!hot.length) { el.innerHTML = `<div class="empty">現在沒有特別燙或特別冷的球員。</div>`; return; }
    const list = state.showAllHot ? hot : hot.slice(0, 8);
    el.innerHTML = list.map((p) => {
      const cls = p.label === "火燙" ? "hot" : "cold";
      return `<button class="item" data-goto="${esc(p.game_id)}">${avatarImg(p)}<div class="grow"><div class="pn">${esc(p.player)}</div>
        <div class="ps">${p.team_logo ? `<img src="${esc(p.team_logo)}" alt="">` : ""}${esc(p.team)} · 近 5 場平均 ${p.last5} ${esc(p.stat)}（平常 ${p.season}）</div></div>
        <span class="badge ${cls}">${icon(cls === "hot" ? "i-fire" : "i-snow")}${esc(p.label)}</span></button>`;
    }).join("") + (hot.length > 8 ? `<button class="more" data-more="hot">${state.showAllHot ? "收起" : `還有 ${hot.length - 8} 人，點開看全部`}</button>` : "");
  }

  const streakZh = (s) => { const m = /^([WL])(\d+)$/.exec(s || ""); return m ? (m[1] === "W" ? "連贏 " : "連輸 ") + m[2] : s || ""; };
  function renderStandings() {
    const st = state.data.standings || {};
    const hid = hiddenSportKeys();
    const keys = Object.keys(st).filter((k) => state.sport === "all" ? !hid.has(chipOf(st[k])) : chipOf(st[k]) === state.sport);
    const el = $("#standings");
    if (!keys.length) { el.innerHTML = `<div class="empty">沒有排名資料。</div>`; return; }
    if (!state.standingsLeague || !keys.includes(state.standingsLeague)) state.standingsLeague = keys[0];
    const cur = st[state.standingsLeague];
    const sel = `<select class="sel" id="st-sel">${keys.map((k) => `<option value="${esc(k)}" ${k === state.standingsLeague ? "selected" : ""}>${esc(st[k].label || k)}</option>`).join("")}</select>`;
    const soccer = cur.sport === "soccer", hockey = cur.sport === "hockey";
    el.innerHTML = sel + (cur.groups || []).map((grp) => `${grp.name ? `<div class="grp">${esc(grp.name)}</div>` : ""}<table class="table"><thead><tr><th class="pos">#</th><th>球隊</th>${soccer ? `<th class="n">勝-和-敗</th><th class="n">積分</th>` : hockey ? `<th class="n">勝-敗-延敗</th><th class="n">積分</th>` : `<th class="n">勝-敗</th><th class="n">近況 / 分差</th>`}</tr></thead><tbody>
      ${grp.rows.slice(0, 24).map((r) => `<tr><td class="pos">${r.pos}</td><td><span class="tm">${r.logo ? `<img src="${esc(r.logo)}" alt="">` : ""}${esc(r.name_zh || r.team || "")}</span></td>
        ${soccer ? `<td class="n">${r.w ?? 0}-${r.d ?? 0}-${r.l ?? 0}</td><td class="n"><b>${r.points ?? ""}</b></td>`
          : hockey ? `<td class="n">${r.w ?? 0}-${r.l ?? 0}-${r.otl ?? 0}</td><td class="n"><b>${r.points ?? ""}</b></td>`
          : `<td class="n"><b>${r.w ?? 0}-${r.l ?? 0}</b></td><td class="n">${esc(streakZh(r.streak) || (r.last5 ? "近5場 " + r.last5 : "") || (r.sets ? "局 " + r.sets : "") || (r.diff != null ? (r.diff > 0 ? "+" : "") + r.diff : ""))}</td>`}</tr>`).join("")}
    </tbody></table>`).join("");
  }

  // ---------- 詳細頁 ----------
  // AI 寫的分析：分段
  function aiBody(g) {
    const ai = g.ai;
    if (!ai || !ai.text) return [];
    return ai.text.split(/\n+/).map((x) => x.trim()).filter(Boolean);
  }
  // AI 分析：老球迷怎麼看、為什麼、這場怎麼算的、要小心，合成一塊講（有 Gemini 寫的就用它的，沒有就用網站自己整理的）
  function ourParas(t) {
    if (t.ai && t.ai.length) return t.ai;
    const out = [];
    if (t.fan) out.push(t.fan);
    if (t.why && t.why.length) out.push(t.why.join(""));
    if (t.care && t.care.length) out.push("要小心：" + t.care.join(""));
    return out;
  }
  function paraHtml(x) {
    const m = /^(要小心：|我們的算法：)/.exec(x);
    if (!m) return `<p>${esc(x)}</p>`;
    const cls = m[1] === "要小心：" ? "ai-care" : "ai-calc";
    return `<p class="${cls}"><b>${esc(m[1] === "要小心：" ? "要小心" : "算法")}</b>${esc(x.slice(m[1].length))}</p>`;
  }
  function calcRows(g) {
    const s = g.suggestion || {}, est = s.est || {};
    const fs = (s.factors || []).filter((f) => f.team);
    if (!fs.length || est.p_home == null) return "";
    const rows = fs.map((f) => `<div class="calc-row"><span>${esc(f.label)}</span><b>${esc(f.team)} +${f.pts}</b></div>`).join("");
    const tot = est.total != null ? `<div class="calc-row"><span>總分大概</span><b>${Math.round(est.total)} 分</b></div>` : "";
    return `<details class="calc-more"><summary>看每個因素加幾分</summary><div class="calc">${rows}${tot}</div></details>`;
  }
  function analysisBlock(g, t) {
    const s = g.suggestion || {}, est = s.est || {};
    const post = g.status.state === "post";
    const ai = g.ai && g.ai.text ? g.ai : null;      // 開打後、打完也留著開打前寫的分析
    const ours = ourParas(t);
    let paras, lean, diff = "", foot;
    const oursFav = est.p_home != null ? (est.p_home >= 0.5 ? "home" : "away") : null;
    if (ai) {
      paras = aiBody(g).concat(ours.filter((x) => x.startsWith("我們的算法：")));
      lean = ai.lean ? `${tname(g[ai.lean])}${ai.p ? "（" + cheng(ai.p) + "）" : ""}` : "兩隊差不多";
      if (ai.lean && oursFav && ai.lean !== oursFav) diff = `<div class="ai-diff">${icon("i-warn")}AI 的看法跟網站的計算不一樣，兩邊都看看再決定。</div>`;
      const when = ai.at ? String(ai.at).slice(5, 16).replace("T", " ") : "";
      foot = `AI 只根據網站整理的資料寫，可能會錯${when ? " · " + esc(when) + (g.status.state !== "pre" ? " 開打前" : "") + " 寫的" : ""}`;
    } else {
      paras = post ? ours.filter((x) => !x.startsWith("要小心：")) : ours;
      if (oursFav && !post) {
        const p = Math.max(est.p_home, 1 - est.p_home);
        lean = p < 0.53 ? "兩隊差不多" : `${tname(g[oursFav])}（${cheng(p)}）`;
      }
      foot = "AI 還沒寫這場，先看網站自己整理的（看實力、陣容、近況、傷兵、新聞，不看賭盤和賠率）" + (est.weak ? " · 開季場數少，還不準" : "");
    }
    // 72 小時外的比賽：還沒抓傷兵、新聞，也還沒請 AI 寫，講清楚什麼時候會有完整分析
    let wait = "";
    if (g.far && !post) {
      const at = new Date(new Date(g.start).getTime() - 72 * 3600e3);
      const when = at.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
      const soon = at.getTime() <= Date.now() ? "下一次更新（每小時一次）就會出來" : `大約 ${esc(when)} 以後出來`;
      wait = `<div class="ai-wait">${icon("i-clock")}<span>這場還早。傷兵、新聞和 AI 寫的完整分析，${soon}，現在先看基本資料。</span></div>`;
    }
    if (!paras.length && !wait) return "";
    return `<div class="ai"><div class="ai-h"><span>${ai ? "AI 分析" : "分析"}</span>${lean ? `<span class="ai-lean">看好 ${esc(lean)}</span>` : ""}</div>${wait}${paras.map(paraHtml).join("")}${diff}${post ? "" : calcRows(g)}${sourcesHtml(g)}<div class="ai-foot">${foot}</div></div>`;
  }
  // 資料來源：分析用到的新聞（原文標題），收起來，要查證才點開
  function sourcesHtml(g) {
    const src = g.sources || [];
    if (!src.length || g.status.state === "post") return "";
    return `<details class="calc-more src-more"><summary>資料來源（${src.length} 則新聞）</summary><div class="src-list">${src.map((x) => `<a href="${esc(x.url || "#")}" target="_blank" rel="noopener"><b>${esc(x.media)}</b>${x.src ? " · " + esc(x.src) : ""}<span>${esc(x.title)}</span></a>`).join("")}</div></details>`;
  }
  function pts(items, cls, ic) {
    if (!items || !items.length) return "";
    return `<ul class="pts">${items.map((x) => `<li class="${cls}">${icon(ic)}<span>${esc(x)}</span></li>`).join("")}</ul>`;
  }
  function twTiles(g) {
    const tw = g.tw;
    if (!tw) return `<div class="note">${esc((g.notes && g.notes.tw) || "台灣運彩還沒開這場。")}</div>`;
    const ml = tw.ml || {}, sp = tw.spread || {}, tt = tw.total || {};
    const s = g.suggestion || {};
    const tiles = [];
    tiles.push(`<div class="tile ${s.pick && s.play === "不讓分" ? "fav" : ""}"><div class="tl">不讓分</div><b>${num(ml.away)} / ${num(ml.home)}</b><small>客 / 主</small></div>`);
    tiles.push(`<div class="tile ${s.pick && s.play === "讓分" ? "fav" : ""}"><div class="tl">讓分</div><b>${sp.line ? esc(sp.line) : "–"}</b><small>${sp.line ? num(sp.away) + " / " + num(sp.home) : "還沒開"}</small></div>`);
    tiles.push(`<div class="tile ${s.play === "大小分" ? "fav" : ""}"><div class="tl">大小${s.play === "大小分" ? "（玩" + esc(s.pick_label) + "）" : ""}</div><b>${tt.line != null ? tt.line : "–"}</b><small>${tt.line != null ? "大 " + num(tt.over) + " 小 " + num(tt.under) : "還沒開"}</small></div>`);
    const o = g.odds || {};
    const est = s.est || {};
    let line = "";
    if (s.source === "own" && est.p_home != null) {
      const v = s.value;
      line = `<div class="line">我們估：${esc(tname(g.away))} ${cheng(1 - est.p_home)}、${esc(tname(g.home))} ${cheng(est.p_home)}${v ? ` · 網站建議的那個賠率 <b class="val ${v.label === "划算" ? "good" : v.label === "不划算" ? "bad" : ""}">${esc(v.label)}</b>（押 100 長期拿回約 ${v.back} 元）` : ""}</div>`;
    } else if (o.prob_home != null) {
      const src = { spread: "國際盤讓分推的", tw_ml: "用台灣賠率算的", form: "沒盤口，用近況猜的", moneyline: "國際盤算的" }[o.prob_source] || "";
      line = `<div class="line">贏的機會：${esc(tname(g.away))} ${cheng(o.prob_away)}、${esc(tname(g.home))} ${cheng(o.prob_home)}${src ? "（" + src + "）" : ""}${s.tw_value && s.tw_value !== "正常" ? " · 台灣賠率" + (s.tw_value === "划算" ? "比平常好" : "比平常差") : ""}</div>`;
    }
    return `<div class="tw-tiles">${tiles.join("")}</div>${line}<div class="line">${esc(tw.source || "玩運彩")}${tw.updated ? " " + esc(String(tw.updated).slice(11, 16)) + " 更新" : ""}，下注前再看一次運彩的最新賠率</div>`;
  }
  function teamHead(t) { return `<div class="team-head">${t.logo ? `<img src="${esc(t.logo)}" alt="">` : `<span class="fallback">${esc(initials(t))}</span>`}${esc(tname(t))}</div>`; }
  function injuryBlock(t, g) {
    const list = (t.injuries || []).slice(0, 12);
    let body = "";
    if (list.length) {
      body = list.map((x) => `<div class="prow">${avatarImg(x)}<div class="grow"><div class="pn">${esc(x.player)}${x.ppg != null ? ` <small style="color:var(--muted);font-weight:500">場均 ${Number(x.ppg).toFixed(1)} 分</small>` : ""}</div><div class="ps">${esc(x.position_zh || x.position || "")}${(x.why || x.detail_zh || (x.official || !x.url ? x.detail : "")) ? " · " + esc(x.why || x.detail_zh || x.detail) : ""}${x.return_date && String(x.return_date).slice(0, 10) > todayTW() && (x.severity === "out" || x.severity === "ir") ? " · 預計 " + esc(String(x.return_date).slice(5, 10)) + " 回來" : ""}${x.url ? ` · <a class="src-link" href="${esc(x.url)}" target="_blank" rel="noopener">來源</a>` : ""}</div></div><span class="badge ${sevClass(x.severity)}">${esc(x.status_zh)}</span></div>`).join("");
      if ((t.injuries || []).length > 12) body += `<div class="note">還有 ${(t.injuries || []).length - 12} 人沒列</div>`;
    } else {
      body = `<div class="note">${esc(t.injury_note || (g.notes && g.notes.injuries) || "沒有傷兵消息，應該是全員到齊。")}</div>`;
    }
    return `<div class="team-block">${teamHead(t)}${body}</div>`;
  }
  function formBlock(t, g) {
    const f = (t.form || []).slice(-5);
    if (!f.length) return `<div class="team-block">${teamHead(t)}<div class="note">${esc((g.notes && g.notes.form) || "本季還沒有打完的比賽。")}</div></div>`;
    const boxes = f.map((r) => `<div class="res"><span class="r ${r.result}">${r.result === "W" ? "勝" : r.result === "L" ? "敗" : "和"}</span><b>${r.pf}-${r.pa}</b><span>${esc(r.date)}</span><span>${esc((r.opp_zh || r.opp || "").slice(0, 4))}</span></div>`).join("");
    const bits = [];
    if (t.last10) bits.push(`近 ${(t.form || []).length} 場 ${esc(t.last10)}`);
    if (t.streak) bits.push(esc(t.streak.replace("連勝", "連贏 ").replace("連敗", "連輸 ")) + " 場");
    if (t.rank_note) bits.push(esc(t.rank_note));
    if (t.avg_for5 != null) bits.push(`最近平均得 ${t.avg_for5} 失 ${t.avg_against5}`);
    return `<div class="team-block">${teamHead(t)}<div class="results">${boxes}</div><div class="form-sum">${bits.join(" · ")}${t.form_note ? `<br><small style="color:var(--muted)">${esc(t.form_note)}（右邊是最近一場）</small>` : ""}</div></div>`;
  }
  function starsBlock(g) {
    const blocks = [];
    for (const side of ["away", "home"]) {
      const t = g[side];
      const stars = t.stars || [];
      const imp = t.injury_impact;
      if (!stars.length && !imp) continue;
      const injBy = {};
      (t.injuries || []).forEach((x) => { injBy[x.player] = x; });
      const rows = stars.map((p) => {
        const x = injBy[p.player];
        const st = x ? `<span class="badge ${sevClass(x.severity)}">${esc(x.status_zh)}</span>` : `<span class="badge ok">正常</span>`;
        const line = [p.ppg != null ? `場均 ${Number(p.ppg).toFixed(1)} 分` : "", p.mpg != null ? `${Math.round(p.mpg)} 分鐘` : "", p.pir != null ? `PIR ${Number(p.pir).toFixed(1)}` : "", p.stat && p.value != null ? `${esc(p.stat)} ${esc(p.value)}` : ""].filter(Boolean).join(" · ");
        return `<div class="prow">${avatarImg(p)}<div class="grow"><div class="pn">${esc(p.player)}</div><div class="ps">${line}</div></div>${st}</div>`;
      }).join("");
      const impHtml = imp && imp.pts >= 1 ? `<div class="note" style="margin-top:8px">少了 ${esc(imp.players.map((p) => p.player.split(" ").pop() + (p.ppg != null ? "（場均 " + Number(p.ppg).toFixed(0) + " 分）" : "")).join("、"))}，大概影響 <b>${imp.pts}</b> 分讓分。${esc(imp.note || "")}</div>` : "";
      blocks.push(`<div class="team-block">${teamHead(t)}${rows || `<div class="note">主力名單還沒有資料。</div>`}${impHtml}</div>`);
    }
    return blocks.length ? `<div class="h">${icon("i-star")}主力球員</div>${blocks.join("")}` : "";
  }
  // 球員看點：每隊 2～3 個主力，一句話講他這季打得怎樣、手感、上場時間、是不是新來的（取代原本的主力名單和手感）
  function spotBlock(g) {
    const teams = ["away", "home"].filter((side) => (g[side].spot || []).length);
    if (!teams.length) return "";
    const tagCls = { 火燙: "hot", 冰冷: "cold", 新來的: "vio", 回歸: "vio", 上季: "muted", 主力: "muted" };
    const blocks = teams.map((side) => {
      const t = g[side];
      const rows = t.spot.map((p) => `<div class="prow spot">${avatarImg(p)}<div class="grow"><div class="pn">${esc(p.player)} <span class="badge ${tagCls[p.tag] || "muted"}">${esc(p.tag)}</span>${p.status_zh ? ` <span class="badge ${sevClass(p.severity)}">${esc(p.status_zh)}</span>` : ""}</div><div class="ps spot-text">${esc(p.text)}</div></div></div>`).join("");
      return `<div class="team-block">${teamHead(t)}${rows}</div>`;
    }).join("");
    return `<div class="h">${icon("i-fire")}球員看點</div>${blocks}`;
  }
  function hotBlock(g) {
    const rows = [];
    for (const side of ["away", "home"]) {
      const t = g[side];
      (t.hot || []).forEach((p) => {
        const cls = p.label === "火燙" ? "hot" : p.label === "冰冷" ? "cold" : "muted";
        rows.push(`<div class="prow">${avatarImg(p)}<div class="grow"><div class="pn">${esc(p.player)} <span class="badge ${cls}">${esc(p.label)}</span></div><div class="ps">${esc(tname(t))} · 近 5 場平均 ${p.last5} ${esc(p.stat)}，平常 ${p.season}</div></div></div>`);
      });
    }
    return rows.length ? `<div class="h">${icon("i-fire")}球員手感</div><div class="team-block">${rows.join("")}</div>` : "";
  }
  function numbersBlock(g) {
    const a = g.analysis || {};
    const H = tname(g.home), A = tname(g.away);
    const kv = [];
    const o = g.odds || {};
    const own = (g.suggestion || {}).source === "own";
    if (!own && o.prob_home != null && o.prob_source !== "form") kv.push(`<div class="kv"><div class="kl">盤口換算的勝率</div><div class="kbar"><span class="ka" style="width:${Math.round(o.prob_away * 100)}%">${esc(A)} ${Math.round(o.prob_away * 100)}%</span><span class="kh" style="width:${Math.round(o.prob_home * 100)}%">${esc(H)} ${Math.round(o.prob_home * 100)}%</span></div>${o.spread != null ? `<div class="kval">國際盤讓分 ${esc(o.details || o.spread)}${o.total != null ? " · 大小 " + o.total : ""}</div>` : ""}</div>`);
    if (a.rating) {
      const r = a.rating;
      kv.push(`<div class="kv"><div class="kl">我們的實力評分（每場淨勝分，已考慮場數）</div><div class="kval">${esc(A)} ${r.away > 0 ? "+" : ""}${r.away}（${r.gp_away} 場）　${esc(H)} ${r.home > 0 ? "+" : ""}${r.home}（${r.gp_home} 場）<br>我們算主隊讓 ${(-r.our_spread).toFixed(1)} 分${r.market_spread != null ? (own ? "，台灣運彩的線 " : "，盤口 ") + (-r.market_spread).toFixed(1) : ""}${r.total != null ? "<br>我們算總分 " + r.total + (r.market_total != null ? (own ? "，台灣運彩的線 " : "，盤口 ") + r.market_total : "") : ""}${r.weak ? "<br><span style=\"color:var(--warn)\">場數太少，評分還不準</span>" : ""}</div></div>`);
    }
    if (a.predictor) kv.push(`<div class="kv"><div class="kl">ESPN 電腦預測（外界看法）</div><div class="kbar"><span class="ka" style="width:${Math.round(a.predictor.away * 100)}%">${esc(A)} ${Math.round(a.predictor.away * 100)}%</span><span class="kh" style="width:${Math.round(a.predictor.home * 100)}%">${esc(H)} ${Math.round(a.predictor.home * 100)}%</span></div></div>`);
    if (!own && a.crowd && a.crowd.ml_home != null) kv.push(`<div class="kv"><div class="kl">玩運彩的人押誰（不讓分）</div><div class="kbar"><span class="ka" style="width:${a.crowd.ml_away || 0}%">${esc(A)} ${a.crowd.ml_away}%</span><span class="kh" style="width:${a.crowd.ml_home || 0}%">${esc(H)} ${a.crowd.ml_home}%</span></div>${a.crowd.n ? `<div class="kval">約 ${a.crowd.n} 人預測</div>` : ""}</div>`);
    if (!own && a.line_move && a.line_move.spread_open != null && a.line_move.spread_now != null) kv.push(`<div class="kv"><div class="kl">盤口變動（主隊讓分，開盤 → 現在）</div><div class="kval">${a.line_move.spread_open > 0 ? "+" : ""}${a.line_move.spread_open} → ${a.line_move.spread_now > 0 ? "+" : ""}${a.line_move.spread_now}${a.line_move.total_open != null ? `　大小 ${a.line_move.total_open} → ${a.line_move.total_now}` : ""}</div></div>`);
    if (a.rest && (a.rest.home || a.rest.away)) {
      const r = (x) => !x ? "無資料" : x.b2b ? "背靠背" : x.days == null ? "本季首戰" : `休 ${x.days} 天`;
      kv.push(`<div class="kv"><div class="kl">休息</div><div class="kval">${esc(A)} ${r(a.rest.away)}　${esc(H)} ${r(a.rest.home)}</div></div>`);
    }
    if (!own && a.ats && (a.ats.home || a.ats.away)) kv.push(`<div class="kv"><div class="kl">讓分盤過盤紀錄${a.ats.source ? "（" + esc(a.ats.source) + "）" : ""}</div><div class="kval">${esc(A)} ${esc(a.ats.away || "–")}　${esc(H)} ${esc(a.ats.home || "–")}</div></div>`);
    if (a.h2h && a.h2h.games && a.h2h.games.length) kv.push(`<div class="kv"><div class="kl">最近交手</div><div class="kval">${a.h2h.games.slice(0, 4).map((x) => `${esc(x.date)} ${esc(x.away)} ${x.as}-${x.hs} ${esc(x.home)}`).join("<br>")}</div></div>`);
    if (!own && a.books && a.books.length > 1) kv.push(`<div class="kv"><div class="kl">各莊家（主隊讓分 / 大小 / 主隊不讓分）</div><div class="kval">${a.books.slice(0, 5).map((b) => `${esc(b.provider)}：${b.spread != null ? (b.spread > 0 ? "+" : "") + b.spread : "–"} / ${b.total != null ? b.total : "–"} / ${b.dec_home != null ? b.dec_home.toFixed(2) : "–"}`).join("<br>")}</div></div>`);
    if (!kv.length) return "";
    return `<button class="fold ${state.numbersOpen ? "open" : ""}" data-fold="1">更多數字（想看細節的再點）${icon("i-chev")}</button><div class="numbers ${state.numbersOpen ? "open" : ""}">${kv.join("")}</div>`;
  }

  function renderSheet() {
    const sh = $("#sheet");
    const g = state.detail ? findGame(state.detail) : null;
    if (!g) { sh.classList.remove("on"); sh.innerHTML = ""; document.body.classList.remove("lock"); return; }
    const t = talkOf(g);
    const s = g.suggestion || {};
    const wait = !s.pick || g.status.state === "post";
    sh.innerHTML = `<div class="sheet-top"><button class="back" data-back="1">${icon("i-back")}返回</button><div class="sheet-title">${esc(g.league_zh)}${g.round ? " · " + esc(g.round) : ""}</div></div>
      <div class="sheet-body">
        <div class="g-top"><span></span>${whenText(g)}</div>
        <div class="g-teams">${teamCol(g.away, "away", g)}${midCol(g)}${teamCol(g.home, "home", g)}</div>
        <div class="verdict ${wait ? "wait" : ""}">${esc(t.verdict)}${g.status.state === "pre" ? `<small>${esc(dayLabel(g.day_tw).name)} ${esc(g.time_tw)} 開打${g.venue ? " · " + esc(g.venue) : ""}</small>` : ""}</div>
        ${t.alt && g.status.state === "pre" ? `<div class="alt-pick"><b>第二選擇</b>${esc(t.alt.replace(/^第二選擇：/, ""))}</div>` : ""}
        ${analysisBlock(g, t)}
        <div class="h">${icon("i-star")}你的預測</div><div id="mypick">${pickButtons(g, false)}</div>
        ${t.matchup && t.matchup.length ? `<div class="h">${icon("i-trophy")}對位跟交手</div>${pts(t.matchup, "info", "i-chev")}` : ""}
        <div class="h">${icon("i-star")}台灣運彩賠率</div>${twTiles(g)}
        <div class="h">${icon("i-med")}傷兵</div>${injuryBlock(g.away, g)}${injuryBlock(g.home, g)}
        ${spotBlock(g) || starsBlock(g)}
        <div class="h">${icon("i-clock")}最近 5 場</div>${formBlock(g.away, g)}${formBlock(g.home, g)}
        ${spotBlock(g) ? "" : hotBlock(g)}
        ${numbersBlock(g)}
        <button class="back" data-back="1" style="margin-top:24px;width:100%;justify-content:center">${icon("i-back")}返回列表</button>
      </div>`;
    sh.classList.add("on");
    sh.scrollTop = 0;
    document.body.classList.add("lock");
  }
  function openSheet(id) {
    state.detail = id;
    state.numbersOpen = false;
    history.pushState({ sheet: id }, "");
    renderSheet();
  }
  function closeSheet(fromPop) {
    if (!state.detail) return;
    state.detail = null;
    renderSheet();
    if (!fromPop && history.state && history.state.sheet) history.back();
  }
  window.addEventListener("popstate", () => { if (state.detail) closeSheet(true); });

  function setView(v) {
    state.view = v;
    document.body.dataset.view = v;
    document.querySelectorAll(".bottom-nav button").forEach((b) => b.classList.toggle("on", b.dataset.view === v));
    window.scrollTo({ top: 0 });
  }

  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-back]")) { closeSheet(false); return; }
    const fold = e.target.closest("[data-fold]");
    if (fold) { state.numbersOpen = !state.numbersOpen; fold.classList.toggle("open", state.numbersOpen); fold.nextElementSibling.classList.toggle("open", state.numbersOpen); return; }
    const dy = e.target.closest("[data-day]");
    if (dy) { state.day = dy.dataset.day; renderChips(); renderDays(); renderPicks(); renderParlay(); renderGames(); window.scrollTo({ top: 0 }); return; }
    if (e.target.closest("[data-more-sports]")) { state.showMore = !state.showMore; renderChips(); return; }
    const chip = e.target.closest(".chip");
    if (chip) { state.sport = chip.dataset.sport; localStorage.setItem("sport", state.sport); render(); return; }
    const sl = e.target.closest("[data-slip]");
    if (sl) { const id = sl.dataset.slip; if (state.slip.has(id)) state.slip.delete(id); else state.slip.add(id); renderParlay(); return; }
    const sk = e.target.closest("[data-stake]");
    if (sk) { setStake(state.stake + Number(sk.dataset.stake)); const inp = $("#slip-stake"); if (inp) inp.value = state.stake; updateSlip(); return; }
    if (e.target.closest("[data-save-slip]")) { const legs = slipLegs(); if (legs.length >= 2) { saveParlay(legs, state.stake, "mine"); state.slip.clear(); state.slipMsg = "存好了，到「成績單 → 我的預測」看結果。"; renderParlay(); } return; }
    if (e.target.closest("[data-save-site]")) { const cur = state.data.parlay && state.data.parlay.current; if (cur && !state.parlays.some((x) => x.site_id === cur.id)) { saveParlay(siteLegs(cur), 100, "site", cur.id); renderParlay(); } return; }
    const dp = e.target.closest("[data-del-parlay]");
    if (dp) { if (confirm("刪掉這張串關？")) { state.parlays = state.parlays.filter((x) => x.id !== dp.dataset.delParlay); saveParlays(); renderRecord(); renderParlay(); } return; }
    const pb = e.target.closest("[data-pick]");
    if (pb) { setPick(pb.dataset.pickGame, pb.dataset.pick); return; }
    const ptab = e.target.closest("[data-ptab]");
    if (ptab) {
      const gid = ptab.dataset.ptabGame, g = findGame(gid);
      state.pickTab[gid] = ptab.dataset.ptab;
      if (g) document.querySelectorAll(`[data-pickrow="${CSS.escape(gid)}"][data-compact="1"]`).forEach((el) => { el.outerHTML = pickButtons(g, true); });
      return;
    }
    const rt = e.target.closest("[data-rec]");
    if (rt) { state.recTab = rt.dataset.rec; renderRecord(); return; }
    if (e.target.closest("[data-export]")) { exportPicks(); return; }
    if (e.target.closest("[data-clear-picks]")) { if (confirm("確定要清掉全部預測紀錄？建議先備份。")) { state.picks = {}; state.parlays = []; savePicks(); saveParlays(); renderRecord(); renderGames(); renderPicks(); renderParlay(); } return; }
    const go = e.target.closest("[data-goto]");
    if (go) { openSheet(go.dataset.goto); return; }
    const more = e.target.closest("[data-more]");
    if (more) { if (more.dataset.more === "inj") state.showAllInj = !state.showAllInj; else state.showAllHot = !state.showAllHot; renderInjuries(); renderHot(); return; }
    const nav = e.target.closest(".bottom-nav button");
    if (nav) { setView(nav.dataset.view); return; }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && state.detail) closeSheet(false); });
  document.addEventListener("input", (e) => {
    if (e.target.id !== "slip-stake") return;
    const v = Number(e.target.value);
    if (Number.isFinite(v) && v >= MIN_STAKE) { setStake(v); updateSlip(); }
  });
  document.addEventListener("change", (e) => {
    if (e.target.id === "st-sel") { state.standingsLeague = e.target.value; localStorage.setItem("standingsLeague", e.target.value); renderStandings(); }
    if (e.target.id === "pick-import" && e.target.files && e.target.files[0]) importPicks(e.target.files[0]);
    if (e.target.id === "slip-stake") { setStake(e.target.value); e.target.value = state.stake; updateSlip(); }
  });
  function exportPicks() {
    const blob = new Blob([JSON.stringify({ version: 1, exported: new Date().toISOString(), picks: state.picks, parlays: state.parlays }, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `我的預測-${todayTW()}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function importPicks(file) {
    const rd = new FileReader();
    rd.onload = () => {
      try {
        const d = JSON.parse(rd.result);
        const picks = d && d.picks && typeof d.picks === "object" ? d.picks : (d && typeof d === "object" ? d : {});
        let n = 0;
        for (const [id, p] of Object.entries(picks)) { if (p && p.side && p.start && !state.picks[id]) { state.picks[id] = p; n++; } }
        const have = new Set(state.parlays.map((x) => x.id));
        (Array.isArray(d && d.parlays) ? d.parlays : []).forEach((x) => { if (x && x.id && Array.isArray(x.legs) && !have.has(x.id)) { state.parlays.push(x); n++; } });
        saveParlays();
        savePicks(); settlePicks(); renderRecord(); renderGames(); renderPicks();
        alert(`匯入了 ${n} 筆。`);
      } catch (err) { alert("這個檔案讀不出來：" + err.message); }
    };
    rd.readAsText(file);
  }
  $("#btn-refresh").addEventListener("click", () => load());
  $("#btn-theme").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = cur;
    try { localStorage.setItem("theme", cur); } catch (_) { /* ignore */ }
    $("#btn-theme").innerHTML = icon(cur === "light" ? "i-moon" : "i-sun");
  });
  try {
    const saved = localStorage.getItem("theme");
    if (saved) { document.documentElement.dataset.theme = saved; $("#btn-theme").innerHTML = icon(saved === "light" ? "i-moon" : "i-sun"); }
  } catch (_) { /* ignore */ }

  load().then(() => { liveTick(); live.fileAt = 0; oddsTick(); });
  setInterval(oddsTick, 60000);
  setInterval(() => load({ silent: true }), 5 * 60 * 1000);
  setInterval(liveTick, 10000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) liveTick(); });
})();
