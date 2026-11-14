"""Collecteur des clôtures Novig, à faire tourner dans le cloud (GitHub Actions, toutes les 15 min).
Novig efface ses matchs de son catalogue public après règlement : ce collecteur relève, juste après chaque
coup d'envoi, la probabilité de clôture de chaque issue (transactions des 5 dernières minutes, sinon la dernière
des 6 heures précédentes) et l'écrit dans novig_closes.json. Bibliothèque standard seulement."""
import json, os, statistics, time, urllib.request

B = "https://api.novig.us/v3/public/catalog"
LEAGUES = ("NBA", "NFL", "EPL", "NHL", "MLS", "NCAAF", "NCAAB")
TYPES = ("MONEY", "MONEYLINE_3_WAY_WIN", "MONEYLINE_3_WAY_DRAW")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "novig_closes.json")
AHEAD = 6 * 3600       # marchés repérés dans les 6 h avant le coup d'envoi
LOOKBACK = 6 * 3600    # transaction la plus ancienne acceptée comme clôture
KEEP = 120 * 86400     # historique conservé


def get(u):
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if getattr(e, "code", 0) in (400, 401, 404): return None
            time.sleep(2 * (k + 1))


def pages(u, stop=None):
    out, after = [], None
    for _ in range(100):
        r = get(u + (f"&after={after}" if after else ""))
        if r is None: return out or None
        it = r.get("items", []); out += it; after = r.get("next")
        if not after or not it or (stop and stop(it)): break
    return out


def close_of(mid, outcomes, kick):  # {nom d'issue: proba} ; achat d'une issue à p ⇔ l'autre à 1 − p
    tr = pages(f"{B}/markets/{mid}/trades?limit=500", stop=lambda it: min(x["ts"] for x in it) / 1000 < kick - LOOKBACK)
    if tr is None: return None
    res = {}
    for oid, name in outcomes.items():
        pts = sorted((x["ts"] / 1000, float(x["price"]) if x["outcomeId"] == oid else 1 - float(x["price"]))
                     for x in tr if kick - LOOKBACK <= x["ts"] / 1000 <= kick and x["outcomeId"] in outcomes)
        if pts:
            last = [p for t, p in pts if t >= kick - 300]
            res[name] = round(statistics.median(last) if last else pts[-1][1], 4)
    return res


def main():
    try:
        with open(OUT, encoding="utf-8") as f: db = json.load(f)
    except Exception: db = {}
    now = time.time(); new = 0
    for lg in LEAGUES:
        for e in pages(f"{B}/events?league={lg}&limit=500") or []:
            st = e.get("startsTs", 0) / 1000
            if e["eventId"] in db or not now < st <= now + AHEAD: continue
            mk = {x["marketId"]: {"type": x["marketType"], "desc": x.get("description"),
                                  "outcomes": {o["outcomeId"]: o.get("name") for o in x.get("outcomes") or []}}
                  for x in pages(f"{B}/markets?event={e['eventId']}&limit=500") or [] if x.get("marketType") in TYPES}
            if mk: db[e["eventId"]] = {"desc": e.get("description"), "league": lg, "start": st, "mk": mk}; new += 1
    done = 0
    for ev in db.values():
        if "close" in ev or now < ev["start"] + 60: continue
        cl = {mid: close_of(mid, m["outcomes"], ev["start"]) for mid, m in ev["mk"].items()}
        if all(v is not None for v in cl.values()) or now > ev["start"] + 12 * 3600:
            ev["close"] = {mid: v for mid, v in cl.items() if v}; done += 1
    db = {k: v for k, v in db.items() if v["start"] > now - KEEP}
    with open(OUT + ".tmp", "w", encoding="utf-8") as f: json.dump(db, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(OUT + ".tmp", OUT)
    print(f"{new} matchs repérés, {done} clôtures relevées, {len(db)} matchs en base")


if __name__ == "__main__":
    main()
