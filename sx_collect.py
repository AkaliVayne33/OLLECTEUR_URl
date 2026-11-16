"""Collecteur des clôtures SX Bet (bourse sportive : NBA, NFL, foot dont sélections nationales, esport…).
L'API publique (trades-v3/public, sans clé) ne montre plus les matchs réglés : ce collecteur lit le fil des
transactions toutes les 15 min, garde celles des marchés vainqueur avant le coup d'envoi, puis calcule la clôture
au milieu du carnet, reconstitué par les deux côtés des preneurs (voir close_of), dans sx_closes.json.
Le carnet lui-même (orders-v3) demande une clé API liée à un compte SX : pas utilisé."""
import json, os, statistics, time, urllib.request
from datetime import datetime

API = "https://api.sx.bet/trades-v3/public?perPage=100"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT, STATE = os.path.join(HERE, "sx_closes.json"), os.path.join(HERE, "sx_state.json")
TYPES = {1, 52, 226}            # 1 = 1X2 (3 marchés binaires « X / Not X »), 52 / 226 = vainqueur (prolongation comprise)
FIRST_SCAN = 2 * 86400          # premier passage : 2 jours d'historique
LOOKBACK, KEEP = 6 * 3600, 120 * 86400
BUDGET = 170           # secondes de lecture du fil par passage (l'étape GitHub est coupée à 4 min)


def get(u):
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 * (k + 1))


def ts(s): return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def rj(p, d):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except Exception: return d


def wj(p, o):
    with open(p + ".tmp", "w", encoding="utf-8") as f: json.dump(o, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(p + ".tmp", p)


def close_of(tr, start):
    """Clôture de l'issue « one » : (proba, méthode). Le fil public ne montre que les preneurs : un preneur sur « one »
    paie le prix de vente de « one », un preneur sur l'autre issue révèle son prix d'achat. Moyenne des médianes des
    deux côtés = milieu du carnet (« milieu »), sur 5 min, sinon 30 min, sinon 2 h avant le coup d'envoi.
    Un seul côté traité : médiane des 5 dernières minutes, sinon dernière transaction des 6 h (« un côté », ancien calcul)."""
    pts = sorted(x for x in tr if start - LOOKBACK <= x[0] <= start)
    if not pts: return None
    for w in (300, 1800, 7200):
        a = [x[2] for x in pts if x[0] >= start - w and len(x) > 3 and x[3] == 1]
        b = [x[2] for x in pts if x[0] >= start - w and len(x) > 3 and x[3] == 2]
        if a and b: return round((statistics.median(a) + statistics.median(b)) / 2, 4), "milieu"
    last = [x[2] for x in pts if x[0] >= start - 300]
    return round(statistics.median(last) if last else pts[-1][2], 4), "un côté"


def main():
    now = time.time()
    db, st = rj(OUT, {}), rj(STATE, {"newest": now - FIRST_SCAN, "open": {}})
    opened = st["open"]  # événements à venir : {eventId: {t1, t2, league, start, mk: {hash: {type, one}}, tr: [[t, hash, p_one]]}}
    newest, nk, n, complete, cut = st["newest"], None, 0, False, False
    for _ in range(600):  # fil des transactions, du plus récent au plus ancien, jusqu'au dernier relevé
        if time.time() - now > BUDGET: cut = True; break  # finir avant la limite de l'étape GitHub (4 min) et tout enregistrer
        r = get(API + (f"&nextKey={nk}" if nk else ""))
        if not r: break  # échec : le repère n'avance pas, ces transactions seront relues au passage suivant
        d = r.get("data") or {}; tr = d.get("trades") or []; nk = d.get("nextKey")
        for x in tr:
            t = ts(x["betTime"])
            if t <= st["newest"]: nk = None; break
            newest = max(newest, t); n += 1
            if x.get("isParlay") or x.get("type") not in TYPES or not x.get("eventId") or not x.get("gameTime"): continue
            start = ts(x["gameTime"])
            if not start - LOOKBACK <= t <= start: continue  # seules les 6 h avant le coup d'envoi servent à la clôture
            e = opened.setdefault(x["eventId"], {"t1": x.get("teamOneName"), "t2": x.get("teamTwoName"), "league": x.get("leagueLabel"),
                                                 "start": start, "mk": {}, "tr": []})
            lab = x.get("outcomeLabel") or ""
            one = (lab if x["isBettingOutcomeOne"] else (lab[4:] if lab.lower().startswith("not ") else None)) if x["type"] == 1 else x.get("teamOneName")
            m = e["mk"].setdefault(x["marketHash"], {"type": x["type"], "one": None})
            if one and not m["one"]: m["one"] = one
            p = int(x["weightedAverageOdds"]) / 1e20  # proba implicite de l'issue jouée
            if x["tradeId"] not in e.setdefault("ids", []):  # pas de doublon si une page est relue
                e["ids"].append(x["tradeId"])  # côté du preneur gardé (1 / 2) : clôture au milieu, voir close_of
                e["tr"].append([t, x["marketHash"], round(p if x["isBettingOutcomeOne"] else 1 - p, 5), 1 if x["isBettingOutcomeOne"] else 2])
        if not nk or not tr: complete = True; break
    if cut and newest > st["newest"]:  # retard trop grand (panne, planning GitHub sauté) : on garde le plus récent, le trou est perdu
        print(f"retard : fil lu sur {n} transactions seulement, les plus anciennes du trou sont abandonnées")
        complete = True
    if complete: st["newest"] = newest  # repère avancé seulement si tout le fil jusqu'au repère précédent a été lu
    done = 0
    for eid, e in list(opened.items()):
        if now < e["start"] + 60: continue
        if not complete and now < e["start"] + 12 * 3600: continue  # fil pas lu jusqu'au bout : on ne fige pas la clôture
        close, how = {}, {}
        for h, m in e["mk"].items():
            if not m["one"]: continue
            r = close_of([x for x in e["tr"] if x[1] == h], e["start"])
            if r: close.setdefault(str(m["type"]), {})[m["one"]], how[h] = r
        if not close and now < e["start"] + 12 * 3600: continue  # rien encore : retenté pendant 12 h
        db[eid] = {k: e[k] for k in ("t1", "t2", "league", "start")} | {"close": close, "how": sorted(set(how.values()))}
        del opened[eid]; done += 1
    db = {k: v for k, v in db.items() if v["start"] > now - KEEP}
    wj(OUT, db); wj(STATE, st)
    print(f"{n} transactions lues, {len(opened)} matchs suivis, {done} clôtures relevées, {len(db)} en base")


if __name__ == "__main__":
    main()
