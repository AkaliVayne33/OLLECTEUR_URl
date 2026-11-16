"""Collecteur des clôtures Novig, à faire tourner dans le cloud (GitHub Actions, toutes les 15 min).
Novig efface ses matchs de son catalogue public après règlement : ce collecteur relève, juste après chaque
coup d'envoi, la probabilité de clôture de chaque issue (transactions des 5 dernières minutes, sinon la dernière
des 6 heures précédentes) et l'écrit dans novig_closes.json. Dans l'heure avant le match, le carnet public est
photographié à chaque passage : la dernière photo donne « close_mid » (milieu achat / vente, prioritaire dans
hl_verif) et « mid_age » (secondes avant le coup d'envoi). Bibliothèque standard seulement."""
import json, os, statistics, time, urllib.request

B = "https://api.novig.us/v3/public/catalog"
LEAGUES = ("NBA", "NFL", "EPL")  # les seules ligues Novig rapprochées par hl_verif (NLEAGUE)
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
        if r is None: return None  # page en échec : liste incomplète refusée (la clôture sera retentée au passage suivant)
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


def book_mid(mid, outcomes):
    """Carnet public (/book : ordres d'achat par issue) -> {nom d'issue: milieu}. Vendre une issue = acheter l'autre :
    prix de vente de A = 1 − meilleur achat de B. Écart > 10 c (carnet vide ou mince) : pas de milieu."""
    b = get(f"{B}/markets/{mid}/book")
    if not b or len(outcomes) != 2: return None
    best = {oid: max((float(o["price"]) for o in (b.get("orders") or {}).get(oid) or [] if o.get("qty")), default=None) for oid in outcomes}
    if any(v is None for v in best.values()): return None
    (o1, b1), (o2, b2) = best.items()
    if (1 - b2) - b1 > 0.10 or (1 - b1) - b2 > 0.10 or b1 + b2 > 1.0001: return None
    m1 = (b1 + 1 - b2) / 2
    return {outcomes[o1]: round(m1, 4), outcomes[o2]: round(1 - m1, 4)}


SNAP = 3600  # carnet photographié à chaque passage dans l'heure avant le coup d'envoi ; la dernière photo fait clôture


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
    done = snaps = 0
    for ev in db.values():
        if "close" not in ev and ev["start"] - SNAP <= now < ev["start"]:  # photo du carnet (la plus récente gardée)
            mids = {mid: book_mid(mid, m["outcomes"]) for mid, m in ev["mk"].items()}
            mids = {k: v for k, v in mids.items() if v}
            if mids: ev["snap"] = {"t": round(now), "mk": mids}; snaps += 1
        if "close" in ev or now < ev["start"] + 60: continue
        cl = {mid: close_of(mid, m["outcomes"], ev["start"]) for mid, m in ev["mk"].items()}
        if all(v is not None for v in cl.values()) or now > ev["start"] + 12 * 3600:
            ev["close"] = {mid: v for mid, v in cl.items() if v}; done += 1
            if ev.get("snap"):  # milieu du carnet au plus près du coup d'envoi (prioritaire dans hl_verif)
                ev["close_mid"], ev["mid_age"] = ev["snap"]["mk"], round(ev["start"] - ev["snap"]["t"])
    db = {k: v for k, v in db.items() if v["start"] > now - KEEP}
    with open(OUT + ".tmp", "w", encoding="utf-8") as f: json.dump(db, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(OUT + ".tmp", OUT)
    print(f"{new} matchs repérés, {snaps} carnets photographiés, {done} clôtures relevées, {len(db)} matchs en base")


if __name__ == "__main__":
    main()
