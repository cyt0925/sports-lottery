/* 今日運彩總覽：讀 data/today.json，純前端。手機優先：一層看重點，點一下看詳細。 */
(function () {
  "use strict";

  const $ = (s, el = document) => el.querySelector(s);
  const params = new URLSearchParams(location.search);
  const DATA_URL = params.get("data") === "sample" ? "data/sample.json" : "data/today.json";
  const SPORT_ICON = { all: "i-grid", nba: "i-basketball", basketball: "i-basketball", eurobasket: "i-basketball", jpbasket: "i-basketball", jpvolley: "i-volleyball", volleyball: "i-volleyball", soccer: "i-soccer", hockey: "i-hockey", football: "i-football" };
  const chipOf = (x) => x.chip || x.sport;

  const state = {
    data: null,
    sport: localStorage.getItem("sport") || "all",
    view: "today",
    detail: null,
    showMore: false,
    showAllInj: false,
    showAllHot: false,
    standingsLeague: localStorage.getItem("standingsLeague") || null,
    numbersOpen: false,
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
  const sevClass = (s) => (s === "out" ? "out" : s === "maybe" ? "maybe" : s === "ir" ? "ir" : s === "ok" ? "ok" : s === "news" ? "vio" : "muted");
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
    render();
    if (visible) setTimeout(() => showLoader(false), Math.max(0, 700 - (Date.now() - t0)));
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
  function verdictPill(g) {
    const s = g.suggestion || {};
    if (g.status.state === "post") return `<span class="pill post">打完了</span>`;
    if (s.pick) return `<span class="pill">${icon("i-star")}押 ${esc(s.pick_label)} · ${esc(s.play)}</span><span class="conf">信心${esc(s.confidence)}</span>`;
    if (!g.odds || g.odds.prob_home == null) return `<span class="pill wait">還沒開盤</span>`;
    return `<span class="pill wait">先不下</span>`;
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
    if (g.status.state === "in") return `<span class="g-when live">${esc(g.status.detail)}</span>`;
    if (g.status.state === "post") return `<span class="g-when">已結束</span>`;
    return `<span class="g-when">${esc(dayLabel(g.day_tw).name)} ${esc(g.time_tw)}</span>`;
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
    if (hasScore) return `<div class="g-mid"><div class="score">${esc(g.away.score ?? "")} : ${esc(g.home.score ?? "")}</div><div class="sub">${g.sets ? "局數" : esc(g.status.detail)}</div></div>`;
    return `<div class="g-mid"><div class="vs">對</div><div class="sub">${esc(g.time_tw)}</div></div>`;
  }

  // ---------- 比賽卡片 ----------
  function gameCard(g) {
    const live = g.status.state === "in", post = g.status.state === "post";
    const s = g.suggestion || {};
    const t = talkOf(g);
    const strong = s.pick && s.confidence === "高" && !post;
    return `<button class="g ${live ? "is-live" : ""} ${post ? "is-post" : ""} ${strong ? "strong" : ""}" data-goto="${esc(g.id)}">
      <div class="g-top"><span>${icon(SPORT_ICON[chipOf(g)] || "i-grid")} <b>${esc(g.league_zh)}</b>${g.round ? " · " + esc(g.round) : ""}</span>${whenText(g)}</div>
      <div class="g-teams">${teamCol(g.away, "away", g)}${midCol(g)}${teamCol(g.home, "home", g)}</div>
      <div class="g-verdict">${verdictPill(g)}</div>
      ${!post ? `<div class="g-why">${esc((t.why || [])[0] || t.verdict)}</div>` : ""}
      ${twLine(g) ? `<div class="g-odds">${twLine(g)}</div>` : ""}
      <div class="g-tap">點一下看詳細 ${icon("i-chev")}</div>
    </button>`;
  }

  // ---------- 畫面 ----------
  function render() {
    const d = state.data;
    document.body.dataset.sport = state.sport;
    $("#hdr-date").textContent = `${dayLabel(todayTW()).sub} · ${ago(d.generated_ts)}`;
    $("#foot-src").textContent = `資料來源：${d.source || "ESPN"}　｜　更新時間 ${String(d.generated_at || "").replace("T", " ").slice(0, 16)}`;
    renderChips();
    renderPicks();
    renderGames();
    renderInjuries();
    renderHot();
    renderStandings();
    renderSheet();
  }

  function renderChips() {
    const all = state.data.games || [];
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

  function topPicks() {
    const order = { 高: 0, 中: 1, 低: 2 };
    const dec = (g) => { const side = g.suggestion.pick; const ml = g.tw && g.tw.ml; return (ml && ml[side]) || (g.odds && g.odds["dec_" + side]) || null; };
    return gamesForSport()
      .filter((g) => g.suggestion && g.suggestion.pick && g.status.state !== "post" && !(dec(g) != null && dec(g) < 1.2))
      .sort((a, b) => {
        const c = order[a.suggestion.confidence] - order[b.suggestion.confidence];
        if (c) return c;
        const pa = Math.max(a.odds?.prob_home || 0, a.odds?.prob_away || 0);
        const pb = Math.max(b.odds?.prob_home || 0, b.odds?.prob_away || 0);
        return pb - pa;
      });
  }
  function renderPicks() {
    const picks = topPicks().slice(0, 3);
    const el = $("#picks");
    if (!picks.length) { el.innerHTML = ""; return; }
    el.innerHTML = `<div class="day-title">今天最有把握的 ${picks.length} 場<small>先看這裡</small></div><div class="cards">${picks.map(gameCard).join("")}</div>`;
  }
  function renderGames() {
    const games = gamesForSport();
    const el = $("#games");
    if (!games.length) { el.innerHTML = `<div class="empty">這個球種現在沒有比賽（往後 40 小時內）。</div>`; return; }
    const live = games.filter((g) => g.status.state === "in");
    const rest = games.filter((g) => g.status.state !== "in");
    const sortGames = (list) => list.sort((a, b) => (a.status.state === "post") - (b.status.state === "post") || a.start.localeCompare(b.start));
    let html = "";
    if (live.length) html += `<div class="day-title live">${icon("i-live")} 進行中<small>${live.length} 場</small></div><div class="cards">${live.map(gameCard).join("")}</div>`;
    const byDay = {};
    rest.forEach((g) => { (byDay[g.day_tw] = byDay[g.day_tw] || []).push(g); });
    html += Object.keys(byDay).sort().map((day) => {
      const dl = dayLabel(day);
      const list = sortGames(byDay[day]);
      return `<div class="day-title">${esc(dl.name)}的比賽<small>${esc(dl.sub)} · ${list.length} 場</small></div><div class="cards">${list.map(gameCard).join("")}</div>`;
    }).join("");
    el.innerHTML = html;
  }

  function renderInjuries() {
    const hid = hiddenSportKeys();
    const feed = (state.data.injury_feed || []).filter((x) => state.sport === "all" ? !hid.has(chipOf(x)) : chipOf(x) === state.sport);
    const el = $("#injuries");
    if (!feed.length) { el.innerHTML = `<div class="empty">今明兩天的比賽沒有傷兵消息。</div>`; return; }
    const list = state.showAllInj ? feed : feed.slice(0, 10);
    el.innerHTML = list.map((x) => `<button class="item" data-goto="${esc(x.game_id)}">${x.severity === "news" ? `<span class="avatar fallback">${icon("i-news")}</span>` : avatarImg(x)}<div class="grow"><div class="pn">${esc(x.player)} ${x.key ? `<span class="badge vio">主力</span>` : ""}</div>
      <div class="ps">${x.team_logo ? `<img src="${esc(x.team_logo)}" alt="">` : ""}${esc(x.team)}${x.position ? " · " + esc(x.position) : ""}${x.detail ? " · " + esc(x.detail) : ""} · ${esc(dayLabel(x.day_tw).name)} ${esc(x.time_tw)}</div></div>
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
    tiles.push(`<div class="tile"><div class="tl">大小</div><b>${tt.line != null ? tt.line : "–"}</b><small>${tt.line != null ? "大 " + num(tt.over) + " 小 " + num(tt.under) : "還沒開"}</small></div>`);
    const o = g.odds || {};
    const src = { spread: "國際盤讓分推的", tw_ml: "用台灣賠率算的", form: "沒盤口，用近況猜的", moneyline: "國際盤算的" }[o.prob_source] || "";
    const line = o.prob_home != null ? `<div class="line">贏的機會：${esc(tname(g.away))} ${cheng(o.prob_away)}、${esc(tname(g.home))} ${cheng(o.prob_home)}${src ? "（" + src + "）" : ""}${s.tw_value && s.tw_value !== "正常" ? " · 台灣賠率" + (s.tw_value === "划算" ? "比平常好" : "比平常差") : ""}</div>` : "";
    return `<div class="tw-tiles">${tiles.join("")}</div>${line}<div class="line">${esc(tw.source || "玩運彩")}${tw.updated ? " " + esc(String(tw.updated).slice(11, 16)) + " 更新" : ""}，下注前再看一次運彩的最新賠率</div>`;
  }
  function teamHead(t) { return `<div class="team-head">${t.logo ? `<img src="${esc(t.logo)}" alt="">` : `<span class="fallback">${esc(initials(t))}</span>`}${esc(tname(t))}</div>`; }
  function injuryBlock(t, g) {
    const list = (t.injuries || []).slice(0, 12);
    let body = "";
    if (list.length) {
      body = list.map((x) => `<div class="prow">${avatarImg(x)}<div class="grow"><div class="pn">${esc(x.player)}</div><div class="ps">${esc(x.position_zh || x.position || "")}${x.detail ? " · " + esc(x.detail) : ""}${x.return_date ? " · 預計 " + esc(String(x.return_date).slice(5, 10)) + " 回來" : ""}</div></div><span class="badge ${sevClass(x.severity)}">${esc(x.status_zh)}</span></div>`).join("");
      if ((t.injuries || []).length > 12) body += `<div class="note">還有 ${(t.injuries || []).length - 12} 人沒列</div>`;
    } else {
      body = `<div class="note">${esc(t.injury_note || (g.notes && g.notes.injuries) || "沒有傷兵消息，應該是全員到齊。")}</div>`;
    }
    const news = (t.injury_news || []).map((n) => `<a href="${esc(n.url || "#")}" target="_blank" rel="noopener"><div><div class="nt">${esc(n.title)}</div><div class="nd">${esc(n.source || "新聞")} · ${esc(String(n.published || "").slice(0, 10))}</div></div></a>`).join("");
    return `<div class="team-block">${teamHead(t)}${body}${news ? `<div class="news">${news}</div>` : ""}</div>`;
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
  function newsBlock(g) {
    if (!g.news || !g.news.length) return "";
    return `<div class="h">${icon("i-news")}相關新聞</div><div class="news">${g.news.map((n) => `<a href="${esc(n.url || "#")}" target="_blank" rel="noopener">${n.image ? `<img src="${esc(n.image)}" alt="" loading="lazy">` : ""}<div><div class="nt">${esc(n.title)}</div><div class="nd">${esc(n.team === "home" ? tname(g.home) : tname(g.away))}${n.source ? " · " + esc(n.source) : ""} · ${esc(String(n.published || "").slice(0, 10))}</div></div></a>`).join("")}</div>`;
  }
  function numbersBlock(g) {
    const a = g.analysis || {};
    const H = tname(g.home), A = tname(g.away);
    const kv = [];
    const o = g.odds || {};
    if (o.prob_home != null && o.prob_source !== "form") kv.push(`<div class="kv"><div class="kl">盤口換算的勝率</div><div class="kbar"><span class="ka" style="width:${Math.round(o.prob_away * 100)}%">${esc(A)} ${Math.round(o.prob_away * 100)}%</span><span class="kh" style="width:${Math.round(o.prob_home * 100)}%">${esc(H)} ${Math.round(o.prob_home * 100)}%</span></div>${o.spread != null ? `<div class="kval">國際盤讓分 ${esc(o.details || o.spread)}${o.total != null ? " · 大小 " + o.total : ""}</div>` : ""}</div>`);
    if (a.predictor) kv.push(`<div class="kv"><div class="kl">ESPN 模型勝率</div><div class="kbar"><span class="ka" style="width:${Math.round(a.predictor.away * 100)}%">${esc(A)} ${Math.round(a.predictor.away * 100)}%</span><span class="kh" style="width:${Math.round(a.predictor.home * 100)}%">${esc(H)} ${Math.round(a.predictor.home * 100)}%</span></div></div>`);
    if (a.crowd && a.crowd.ml_home != null) kv.push(`<div class="kv"><div class="kl">玩運彩的人押誰（不讓分）</div><div class="kbar"><span class="ka" style="width:${a.crowd.ml_away || 0}%">${esc(A)} ${a.crowd.ml_away}%</span><span class="kh" style="width:${a.crowd.ml_home || 0}%">${esc(H)} ${a.crowd.ml_home}%</span></div>${a.crowd.n ? `<div class="kval">約 ${a.crowd.n} 人預測</div>` : ""}</div>`);
    if (a.line_move && a.line_move.spread_open != null && a.line_move.spread_now != null) kv.push(`<div class="kv"><div class="kl">盤口變動（主隊讓分，開盤 → 現在）</div><div class="kval">${a.line_move.spread_open > 0 ? "+" : ""}${a.line_move.spread_open} → ${a.line_move.spread_now > 0 ? "+" : ""}${a.line_move.spread_now}${a.line_move.total_open != null ? `　大小 ${a.line_move.total_open} → ${a.line_move.total_now}` : ""}</div></div>`);
    if (a.rest && (a.rest.home || a.rest.away)) {
      const r = (x) => !x ? "無資料" : x.b2b ? "背靠背" : x.days == null ? "本季首戰" : `休 ${x.days} 天`;
      kv.push(`<div class="kv"><div class="kl">休息</div><div class="kval">${esc(A)} ${r(a.rest.away)}　${esc(H)} ${r(a.rest.home)}</div></div>`);
    }
    if (a.ats && (a.ats.home || a.ats.away)) kv.push(`<div class="kv"><div class="kl">讓分盤過盤紀錄${a.ats.source ? "（" + esc(a.ats.source) + "）" : ""}</div><div class="kval">${esc(A)} ${esc(a.ats.away || "–")}　${esc(H)} ${esc(a.ats.home || "–")}</div></div>`);
    if (a.h2h && a.h2h.games && a.h2h.games.length) kv.push(`<div class="kv"><div class="kl">最近交手</div><div class="kval">${a.h2h.games.slice(0, 4).map((x) => `${esc(x.date)} ${esc(x.away)} ${x.as}-${x.hs} ${esc(x.home)}`).join("<br>")}</div></div>`);
    if (a.books && a.books.length > 1) kv.push(`<div class="kv"><div class="kl">各莊家（主隊讓分 / 大小 / 主隊不讓分）</div><div class="kval">${a.books.slice(0, 5).map((b) => `${esc(b.provider)}：${b.spread != null ? (b.spread > 0 ? "+" : "") + b.spread : "–"} / ${b.total != null ? b.total : "–"} / ${b.dec_home != null ? b.dec_home.toFixed(2) : "–"}`).join("<br>")}</div></div>`);
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
        ${t.why && t.why.length ? `<div class="h">${icon("i-check")}為什麼</div>${pts(t.why, "plus", "i-check")}` : ""}
        ${t.care && t.care.length ? `<div class="h">${icon("i-warn")}要小心</div>${pts(t.care, "minus", "i-warn")}` : ""}
        <div class="h">${icon("i-star")}台灣運彩賠率</div>${twTiles(g)}
        <div class="h">${icon("i-med")}傷兵</div>${injuryBlock(g.away, g)}${injuryBlock(g.home, g)}
        <div class="h">${icon("i-clock")}最近 5 場</div>${formBlock(g.away, g)}${formBlock(g.home, g)}
        ${hotBlock(g)}
        ${newsBlock(g)}
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
    if (e.target.closest("[data-more-sports]")) { state.showMore = !state.showMore; renderChips(); return; }
    const chip = e.target.closest(".chip");
    if (chip) { state.sport = chip.dataset.sport; localStorage.setItem("sport", state.sport); render(); return; }
    const go = e.target.closest("[data-goto]");
    if (go) { openSheet(go.dataset.goto); return; }
    const more = e.target.closest("[data-more]");
    if (more) { if (more.dataset.more === "inj") state.showAllInj = !state.showAllInj; else state.showAllHot = !state.showAllHot; renderInjuries(); renderHot(); return; }
    const nav = e.target.closest(".bottom-nav button");
    if (nav) { setView(nav.dataset.view); return; }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && state.detail) closeSheet(false); });
  document.addEventListener("change", (e) => {
    if (e.target.id === "st-sel") { state.standingsLeague = e.target.value; localStorage.setItem("standingsLeague", e.target.value); renderStandings(); }
  });
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

  load();
  setInterval(() => load({ silent: true }), 5 * 60 * 1000);
})();
