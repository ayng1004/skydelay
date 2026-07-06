const MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
const API = window.SKYDELAY_API || localStorage.getItem("skydelay_api") || "http://localhost:8000";
const CLUSTER_COLORS = [[243,156,18], [46,204,113], [231,76,60], [52,152,219]];

const rad = d => d * Math.PI / 180, deg = r => r * 180 / Math.PI, clamp = t => Math.max(0, Math.min(1, t));
function gcInterp(a, b, f) {
 const p1 = rad(a[1]), l1 = rad(a[0]), p2 = rad(b[1]), l2 = rad(b[0]);
 const d = 2 * Math.asin(Math.sqrt(Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin((l2 - l1) / 2) ** 2));
 if (!d) return a;
 const A = Math.sin((1 - f) * d) / Math.sin(d), B = Math.sin(f * d) / Math.sin(d);
 const x = A * Math.cos(p1) * Math.cos(l1) + B * Math.cos(p2) * Math.cos(l2);
 const y = A * Math.cos(p1) * Math.sin(l1) + B * Math.cos(p2) * Math.sin(l2);
 const z = A * Math.sin(p1) + B * Math.sin(p2);
 return [deg(Math.atan2(y, x)), deg(Math.atan2(z, Math.sqrt(x * x + y * y)))];
}
function bearing(a, b) {
 const p1 = rad(a[1]), p2 = rad(b[1]), dl = rad(b[0] - a[0]);
 return deg(Math.atan2(Math.sin(dl) * Math.cos(p2), Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl)));
}
function grad(t) {
 t = clamp(t); const c = [[46, 204, 113], [241, 196, 15], [231, 76, 60]];
 const mix = (a, b, f) => a.map((v, i) => Math.round(v + (b[i] - v) * f));
 return t < 0.5 ? mix(c[0], c[1], t * 2) : mix(c[1], c[2], (t - 0.5) * 2);
}
const riskColor = r => grad((r - 0.38) / 0.17);
const realColor = delay => grad((delay - 10) / 60);

const AIRLINES = { "9E": "Endeavor Air", AA: "American", AS: "Alaska", B6: "JetBlue", DL: "Delta", F9: "Frontier", G4: "Allegiant", HA: "Hawaiian", MQ: "Envoy Air", NK: "Spirit", OH: "PSA Airlines", OO: "SkyWest", UA: "United", WN: "Southwest", YX: "Republic" };
const alName = c => AIRLINES[c] ? `${AIRLINES[c]} (${c})` : c;
let cities = {};
const city = i => cities[i] ? `${cities[i]} (${i})` : i;

let flights = [], airports = [], meta = {}, mode = "dayof", speed = 10;
let show = { planes: true, airports: true };
let predRoute = null, paused = false, clockMin = 0, planeSize = 22;
let lastList = 0, listRows = [], minRisk = 0, lastArrMin = 0, lastArrTick = 0;
const riskOf = f => mode === "pred" ? f.risk : f.drisk;
const visible = f => riskOf(f) >= minRisk;
const $ = id => document.getElementById(id);
const tip = $("tooltip");

const ICON = (() => {
 const c = document.createElement("canvas"); c.width = 128; c.height = 128;
 const x = c.getContext("2d"); x.fillStyle = "#fff";
 const P = pts => { x.beginPath(); x.moveTo(pts[0][0], pts[0][1]); pts.slice(1).forEach(p => x.lineTo(p[0], p[1])); x.closePath(); x.fill(); };
 P([[64, 12], [72, 44], [72, 86], [64, 116], [56, 86], [56, 44]]);
 P([[60, 54], [12, 82], [12, 90], [60, 70]]);
 P([[68, 54], [116, 82], [116, 90], [68, 70]]);
 P([[62, 100], [46, 112], [46, 116], [62, 106]]);
 P([[66, 100], [82, 112], [82, 116], [66, 106]]);
 return c;
})();

const hhmm = m => String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(Math.floor(m % 60)).padStart(2, "0");
const predMin = f => mode === "pred" ? f.pdelay : f.dpdelay;
const flightColor = f => mode === "real" ? realColor(f.delay) : realColor(predMin(f));

function onHover(info) {
 if (!info.object) { tip.style.display = "none"; return; }
 const o = info.object;
 tip.innerHTML = o.iata
 ? `<b>${o.iata}</b> ${o.name || ""}<br>${(o.delay_rate * 100).toFixed(0)}% de retards`
 : `<b>${alName(o.al)}</b><br>${city(o.o)} vers ${city(o.d)}<br>prédit ${(o.risk * 100).toFixed(0)}%, réel ${o.real ? "retard " + o.delay + " min" : "à l'heure"}`;
 tip.style.display = "block"; tip.style.left = info.x + 14 + "px"; tip.style.top = info.y + 14 + "px";
}

function showDetail(o) {
 const b = $("detail-body");
 if (o.iata) {
 b.innerHTML = `<h3>Aéroport ${o.iata}</h3><div class="d-sub">${o.name || ""}</div>
 <div class="d-big" style="color:rgb(${riskColor(o.delay_rate)})">${(o.delay_rate * 100).toFixed(0)}%</div>
 <div class="d-sub">de vols en retard (historique 2024)</div>
 <div class="d-row"><span>Vols dans l'année</span><b>${o.n_flights.toLocaleString()}</b></div>
 <div class="d-row"><span>Retard moyen</span><b>${o.avg_delay?.toFixed(0)} min</b></div>
 <div class="d-row"><span>Profil (cluster)</span><b>${o.cluster}${o.anomalie ? " (atypique)" : ""}</b></div>`;
 } else {
 const fmt = m => m < 10 ? "à l'heure" : `~${m} min`;
 const pct = r => Math.round(r * 100) + "%";
 const cur = predMin(o), curRisk = mode === "dayof" ? o.drisk : o.risk;
 const titre = mode === "dayof" ? "Prévision jour du vol" : "Prévision à la réservation";
 b.innerHTML = `<h3>${alName(o.al)}</h3><div class="d-sub">${city(o.o)} vers ${city(o.d)}</div>
 <div class="d-sub">départ ${hhmm(o.dep)}, durée ${o.dur} min</div>
 <div class="d-big" style="color:rgb(${realColor(cur)})">${fmt(cur)}</div>
 <div class="d-sub">${titre}, soit ${pct(curRisk)} de risque de dépasser 15 min</div>
 <div class="d-row"><span>À la réservation</span><b style="color:rgb(${realColor(o.pdelay)})">${fmt(o.pdelay)}, ${pct(o.risk)}</b></div>
 <div class="d-row"><span>Le jour du vol</span><b style="color:rgb(${realColor(o.dpdelay)})">${fmt(o.dpdelay)}, ${pct(o.drisk)}</b></div>
 <div class="d-row"><span>Avion précédent</span><b>${o.prev >= 10 ? "+" + o.prev + " min" : "à l'heure"}</b></div>
 <div class="d-row"><span>Retard réel observé</span><b style="color:rgb(${realColor(o.delay)})">${o.delay >= 10 ? "+" + o.delay + " min" : "à l'heure"}</b></div>`;
 }
 $("detail").classList.remove("hidden");
}
const onClick = info => { if (info.object) showDetail(info.object); };

function gcPath(o, q, n = 48) {
 const a = []; let prev = null;
 for (let i = 0; i <= n; i++) {
 const p = gcInterp(o, q, i / n);
 if (!isFinite(p[0]) || !isFinite(p[1])) continue;
 if (prev) { while (p[0] - prev[0] > 180) p[0] -= 360; while (p[0] - prev[0] < -180) p[0] += 360; }
 a.push(p); prev = p;
 }
 return a;
}

function layers(dayMin) {
 const L = [];
 if (predRoute) {
 L.push(new deck.PathLayer({ id: "predglow", data: [predRoute], getPath: d => d.path,
 getColor: [255, 255, 255, 60], getWidth: 12, widthUnits: "pixels", capRounded: true }));
 L.push(new deck.PathLayer({ id: "predpath", data: [predRoute], getPath: d => d.path,
 getColor: [255, 255, 255, 255], getWidth: 3, widthUnits: "pixels", capRounded: true }));
 L.push(new deck.ScatterplotLayer({ id: "predpts", data: [predRoute.p, predRoute.q],
 getPosition: d => d, getRadius: 7, radiusUnits: "pixels", getFillColor: [255, 255, 255], stroked: true, getLineColor: [10, 14, 23], lineWidthUnits: "pixels", getLineWidth: 2 }));
 const now = performance.now() / 1000;
 const f = (now * 0.05) % 1;
 const pp = gcInterp(predRoute.p, predRoute.q, f), pp2 = gcInterp(predRoute.p, predRoute.q, Math.min(1, f + 0.01));
 const pulse = 18 + 6 * Math.sin(now * 4);
 L.push(new deck.ScatterplotLayer({ id: "predglow2", data: [pp], getPosition: d => d, getRadius: pulse, radiusUnits: "pixels", getFillColor: [64, 224, 255, 90] }));
 L.push(new deck.IconLayer({ id: "predplane", data: [{ position: pp, bearing: bearing(pp, pp2) }], billboard: true,
 iconAtlas: ICON, iconMapping: { plane: { x: 0, y: 0, width: 128, height: 128, anchorX: 64, anchorY: 64, mask: true } },
 getIcon: () => "plane", getPosition: d => d.position, getAngle: d => -d.bearing, getSize: 40, sizeUnits: "pixels", getColor: [64, 224, 255] }));
 }
 if (show.airports) L.push(new deck.ScatterplotLayer({
 id: "airports", data: airports, pickable: true, onHover, onClick, radiusUnits: "pixels", stroked: true, lineWidthUnits: "pixels",
 getPosition: d => [d.lon, d.lat], getRadius: d => 3 + Math.sqrt(d.n_flights) / 95,
 getFillColor: d => [...(CLUSTER_COLORS[d.cluster] || [150, 150, 150]), 190],
 getLineColor: d => d.anomalie ? [255, 70, 70] : [255, 255, 255, 45], getLineWidth: d => d.anomalie ? 2 : 0.4
 }));
 let air = [];
 if (show.planes) {
 for (const f of flights) {
 if (dayMin < f.dep || dayMin > f.dep + f.dur || !visible(f)) continue;
 const frac = (dayMin - f.dep) / f.dur;
 const p = gcInterp([f.ox, f.oy], [f.dx, f.dy], frac);
 const p2 = gcInterp([f.ox, f.oy], [f.dx, f.dy], Math.min(1, frac + 0.01));
 air.push({ ...f, position: p, bearing: bearing(p, p2), color: flightColor(f) });
 }
 L.push(new deck.IconLayer({
 id: "planes", data: air, pickable: true, onHover, onClick, billboard: true,
 iconAtlas: ICON, iconMapping: { plane: { x: 0, y: 0, width: 128, height: 128, anchorX: 64, anchorY: 64, mask: true } },
 getIcon: () => "plane", getPosition: d => d.position, getAngle: d => -d.bearing,
 getSize: planeSize, sizeUnits: "pixels", getColor: d => predRoute ? [...d.color, 45] : d.color,
 updateTriggers: { getColor: [mode, !!predRoute], getSize: planeSize }
 }));
 }
 $("stat").innerHTML = `${air.length.toLocaleString()} avions en vol, ${flights.length.toLocaleString()} vols ce jour`;
 return L;
}

const map = new maplibregl.Map({ container: "map", style: MAP_STYLE, center: [-96, 38], zoom: 3.7 });
const overlay = new deck.MapboxOverlay({ layers: [] });
map.addControl(overlay);

function fill(sel, arr, def, label) { sel.innerHTML = arr.map(v => `<option value="${v}" ${v === def ? "selected" : ""}>${label(v)}</option>`).join(""); }

Promise.all([
 fetch("data/day.json").then(r => r.json()),
 fetch("data/airports.json").then(r => r.json()),
 fetch("data/meta.json").then(r => r.json())
]).then(([day, a, m]) => {
 flights = day.flights; airports = a; meta = m; cities = m.cities || {};
 fill($("airline"), meta.airlines, "AA", alName); fill($("origin"), meta.airports, "JFK", city); fill($("dest"), meta.airports, "LAX", city);
 fetch("data/days.json").then(r => r.json()).then(list => {
 $("day-in").innerHTML = list.map(d => `<option value="${d}" ${d === day.date ? "selected" : ""}>${d}</option>`).join("");
 }).catch(() => {});
 let last = performance.now();
 (function frame(now) {
 const dt = (now - last) / 1000; last = now;
 if (!paused) clockMin = (clockMin + dt * speed) % 1440;
 planeSize = Math.max(16, Math.min(64, 8 + (map.getZoom() - 2) * 6));
 $("clock").textContent = hhmm(clockMin);
 overlay.setProps({ layers: layers(clockMin) });
 if (now - lastList > 1000) { lastList = now; renderList(clockMin); renderScore(clockMin); }
 if (now - lastArrTick > 3000) { lastArrTick = now; renderArrivals(clockMin); }
 requestAnimationFrame(frame);
 })(last);
});

async function loadDay(date) {
 try {
 const r = await fetch("data/days/" + date + ".json");
 const j = await r.json();
 if (j.flights && j.flights.length) { flights = j.flights; clockMin = 0; lastArrMin = 0; $("arrivals").innerHTML = ""; paused = false; $("playpause").textContent = "Pause"; }
 } catch (e) {}
}
$("day-in").onchange = e => loadDay(e.target.value);
$("playpause").onclick = () => { paused = !paused; $("playpause").textContent = paused ? "Lecture" : "Pause"; };

$("speed").oninput = e => speed = +e.target.value;
$("minrisk").oninput = e => { minRisk = +e.target.value / 100; $("rmval").textContent = e.target.value; };
for (const [id, key] of [["t-planes", "planes"], ["t-airports", "airports"]])
 $(id).onchange = e => show[key] = e.target.checked;
for (const r of document.querySelectorAll("input[name=mode]"))
 r.onchange = e => { mode = e.target.value; $("arrivals").innerHTML = ""; lastArrMin = clockMin; renderScore(clockMin); renderList(clockMin); };
$("detail-close").onclick = () => $("detail").classList.add("hidden");
$("dayof-chk").onchange = e => $("prev-wrap").classList.toggle("hidden", !e.target.checked);
$("prev-in").oninput = e => $("pval").textContent = e.target.value;

const HOURS = [0.2, 0.21, 0.21, 0.19, 0.2, 0.09, 0.1, 0.12, 0.14, 0.15, 0.17, 0.18, 0.19, 0.21, 0.23, 0.25, 0.27, 0.28, 0.29, 0.3, 0.3, 0.28, 0.27, 0.21];
const MODELS = [["Référence (toujours à l'heure)", 0.50, false], ["Régression logistique", 0.56, false], ["Gradient boosting + météo", 0.65, false], ["Jour du vol (propagation + réseau)", 0.80, true]];
let storyInit = false;
function openStory() {
 $("story").classList.remove("hidden"); $("tab-story").classList.add("active"); $("tab-map").classList.remove("active");
 document.body.classList.add("story-open"); closeSheets();
 if (storyInit) return; storyInit = true;
 const mx = Math.max(...HOURS);
 $("hourbars").innerHTML = HOURS.map((v, i) => `<div class="b" style="height:${v / mx * 100}%" data-t="${i}h, ${(v * 100).toFixed(0)}%"></div>`).join("");
 $("modeltable").innerHTML = "<tr><th>Modèle</th><th>AUC</th></tr>" + MODELS.map(m => `<tr class="${m[2] ? "win" : ""}"><td>${m[0]}</td><td>${m[1].toFixed(2)}</td></tr>`).join("");
 let n = 0; const tgt = 7079061, step = tgt / 60;
 (function tick() { n = Math.min(tgt, n + step); $("counter").textContent = Math.floor(n).toLocaleString("fr-FR"); if (n < tgt) requestAnimationFrame(tick); })();
}
function openMap() { $("story").classList.add("hidden"); $("tab-map").classList.add("active"); $("tab-story").classList.remove("active"); document.body.classList.remove("story-open"); }
$("tab-story").onclick = openStory;
$("tab-map").onclick = openMap;

const SHEETS = [["mb-replay", "hud"], ["mb-list", "listpanel"], ["mb-predict", "side"]];
function closeSheets() { for (const [b, p] of SHEETS) { $(p).classList.remove("open"); $(b).classList.remove("active"); } }
function openSheet(btn, panel) {
 const open = !$(panel).classList.contains("open");
 closeSheets();
 $(panel).classList.toggle("open", open);
 $(btn).classList.toggle("active", open);
}
for (const [b, p] of SHEETS) $(b).onclick = () => openSheet(b, p);
$("go-map").onclick = openMap;
$("go-predict").onclick = () => {
 if (!meta.airlines) return;
 const rnd = a => a[Math.floor(Math.random() * a.length)];
 $("airline").value = rnd(meta.airlines); $("origin").value = rnd(meta.airports); $("dest").value = rnd(meta.airports);
 $("time-in").value = "18:00";
 openMap(); $("go").click();
};
for (const b of document.querySelectorAll(".quiz button"))
 b.onclick = () => $("quiz-rev").textContent = b.dataset.a === "1" ? "Exact, en soirée le risque grimpe à ~30 %." : "Raté, c'est en soirée que ça coince le plus.";

const navItems = [...document.querySelectorAll(".nav-item")];
for (const b of navItems)
 b.onclick = () => {
 navItems.forEach(n => n.classList.toggle("active", n === b));
 document.querySelectorAll(".chapter").forEach(c => c.classList.toggle("active", c.id === "ch-" + b.dataset.ch));
 $("ch-select").value = b.dataset.ch;
 document.querySelector(".story-main").scrollTop = 0;
 };
$("ch-select").innerHTML = navItems.map(b => `<option value="${b.dataset.ch}">${b.textContent}</option>`).join("");
$("ch-select").onchange = e => navItems.find(b => b.dataset.ch === e.target.value).click();

const NIV = { faible: [46, 204, 113], moyen: [241, 196, 15], fort: [231, 76, 60] };
function clearPred() { predRoute = null; $("result").innerHTML = ""; }

function facteurVol(f) {
 if (f.dep >= 17 * 60) return "soirée";
 if (f.dep <= 8 * 60) return "matin";
 return "journée";
}
function renderList(now) {
 listRows = flights.filter(f => now >= f.dep && now <= f.dep + f.dur && visible(f)).sort((a, b) => predMin(b) - predMin(a));
 $("fl-count").textContent = "(" + listRows.length + ")";
 const rows = listRows.slice(0, 40).map((f, i) => {
 const m = predMin(f);
 const pc = `rgb(${realColor(m)})`, rc = `rgb(${realColor(f.delay)})`;
 const reel = f.delay >= 10 ? "+" + f.delay + " min" : "à l'heure";
 const pred = m < 10 ? "à l'heure" : "+" + m + " min";
 return `<div class="fl-row" data-i="${i}">
 <div class="fl-r1"><b>${alName(f.al).replace(/ \(.*/, "")}</b> ${f.o} vers ${f.d} <span class="fl-fac">${facteurVol(f)}</span></div>
 <div class="fl-r2"><span style="color:${pc}">prédit ${pred}</span><span style="color:${rc}">réel ${reel}</span></div>
 </div>`;
 }).join("");
 $("fl-body").innerHTML = rows;
 for (const el of document.querySelectorAll(".fl-row")) el.onclick = () => showDetail(listRows[+el.dataset.i]);
}

function renderScore(now) {
 const done = flights.filter(f => now >= f.dep + f.dur);
 $("scorepanel").classList.toggle("show", done.length > 0);
 if (!done.length) { $("score").innerHTML = ""; return; }
 const predRate = done.reduce((s, f) => s + riskOf(f), 0) / done.length;
 const realRate = done.reduce((s, f) => s + f.real, 0) / done.length;
 const juste = done.filter(f => Math.abs(predMin(f) - Math.max(-30, Math.min(240, f.delay))) <= 15).length / done.length;
 const label = mode === "pred" ? "modèle réservation" : "modèle jour du vol";
 $("score").innerHTML = `<div class="legend-title">Fiabilité en direct</div>
 <div class="sc-model">${label}, ${done.length.toLocaleString()} vols atterris</div>
 <div class="sc-row"><span>Risque moyen prédit</span><b>${(predRate * 100).toFixed(0)}%</b></div>
 <div class="sc-row"><span>Retard réel observé</span><b>${(realRate * 100).toFixed(0)}%</b></div>
 <div class="sc-row big"><span>Prévisions justes à 15 min</span><b>${(juste * 100).toFixed(0)}%</b></div>`;
}

function renderArrivals(now) {
 if (now < lastArrMin) lastArrMin = 0;
 const landed = flights.filter(f => f.dep + f.dur > lastArrMin && f.dep + f.dur <= now).slice(0, 2);
 lastArrMin = now;
 const box = $("arrivals");
 for (const f of landed) {
   const p = predMin(f), reel = f.delay >= 10 ? "+" + f.delay + " min" : "à l'heure";
   const pred = p < 10 ? "à l'heure" : "~" + p + " min";
   const el = document.createElement("div");
   el.className = "arr-card";
   el.innerHTML = `<div class="a-t">${alName(f.al).replace(/ \(.*/, "")}, ${f.o} vers ${f.d}</div>
     <div class="a-row"><span>prédit</span><b style="color:rgb(${realColor(p)})">${pred}</b></div>
     <div class="a-row"><span>réel</span><b style="color:rgb(${realColor(f.delay)})">${reel}</b></div>`;
   box.prepend(el);
 }
 while (box.children.length > 10) box.lastChild.remove();
}
$("go").onclick = async () => {
 const dt = new Date($("date-in").value + "T00:00");
 const dow = ((dt.getDay() + 6) % 7) + 1;
 const hour = parseInt($("time-in").value.split(":")[0]) || 0;
 const o = $("origin").value, d = $("dest").value;
 const body = { airline: $("airline").value, origin: o, dest: d, dep_hour: hour, day_of_week: dow, month: dt.getMonth() + 1, date: $("date-in").value };
 if ($("dayof-chk").checked) body.prev_arr_delay = +$("prev-in").value;
 const res = $("result"); res.innerHTML = "<div class='res-lbl'>Calcul…</div>";
 try {
 const r = await fetch(API + "/predict", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
 const j = await r.json(); const p = j.proba_retard, m = j.retard_minutes;
 const niveau = p < 0.2 ? "Risque faible" : p < 0.35 ? "Risque modéré" : p < 0.55 ? "Risque élevé" : "Risque très élevé";
 const col = riskColor(p);
 const attendu = m < 10 ? "à l'heure le plus souvent" : `en moyenne ~${m} min de retard`;
 const facteurs = j.facteurs.map(f => `<span class="pill" style="background:rgba(${NIV[f[1]]},.18);color:rgb(${NIV[f[1]]})">${f[0]}</span>`).join(" ");
 res.innerHTML = `<div class="res-pct" style="color:rgb(${col})">${niveau}, ${(p * 100).toFixed(0)}%</div>
 <div class="gauge"><span style="width:${Math.min(100, p * 200)}%;background:rgb(${col})"></span></div>
 <div class="res-lbl">${city(o)} vers ${city(d)}, ${attendu}<br>prévision <b>${j.mode}</b>, ${(p * 100).toFixed(0)}% de risque de dépasser 15 min</div>
 <div class="factors"><div class="legend-title">Ce qui pèse sur ce vol</div>${facteurs}</div>
 <div class="res-lbl">Météo ${j.meteo_source} au départ : ${j.meteo.prcp} mm pluie, ${j.meteo.snow} mm neige, ${j.meteo.wspd} km/h vent</div>
 <button id="clear-pred" class="clear-btn">Effacer le trajet</button>`;
 $("clear-pred").onclick = clearPred;
 const co = meta.coords[o], cd = meta.coords[d];
 if (co && cd) { predRoute = { o, d, p: co, q: cd, path: gcPath(co, cd) }; map.fitBounds([[Math.min(co[0], cd[0]), Math.min(co[1], cd[1])], [Math.max(co[0], cd[0]), Math.max(co[1], cd[1])]], { padding: 120, duration: 800 }); }
 } catch (e) {
 res.innerHTML = `<div class="res-err">API non disponible. Lancez le backend :<br><code>uvicorn api.main:app --port 8000</code></div>`;
 }
};
