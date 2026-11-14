"""Collecteur des clôtures ProphetX (bourse américaine : NBA, NFL, NHL, foot européen…).
L'API publique (sans compte) ne donne que le carnet du moment, sans historique : à chaque passage (15 min), ce
collecteur note les meilleurs prix vainqueur des matchs qui commencent dans les 40 minutes ; la clôture est le
dernier relevé avant le coup d'envoi (au plus ~15 min avant). Écrit px_closes.json. Bibliothèque standard seulement."""
import json, os, time, urllib.request
from datetime import datetime

API = "https://www.prophetx.co/trade/public/api"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "px_closes.json")
SPORTS = {"Soccer", "Basketball", "American Football", "Ice Hockey", "Esports", "E-Sports"}
AHEAD, KEEP = 40 * 60, 120 * 86400


def get(u):
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}), timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if getattr(e, "code", 0) in (400, 401, 403, 404): return None
            time.sleep(2 * (k + 1))


def ts(s): return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def tournaments():
    out, nxt = [], None
    for _ in range(20):
        r = get(f"{API}/v1/tournaments" + (f"?next={nxt}" if nxt else ""))
        if not r: break
        d = (r.get("data") or {}).get("tournaments") or []
        out += [t for t in d if (t.get("sport") or {}).get("name") in SPORTS]
        nxt = r.get("next")
        if not nxt or not d: break
    return out


def best_prices(ev):  # {nom d'issue: meilleure cote américaine à prendre} du marché vainqueur
    ms = ((get(f"{API}/v2/events/{ev['id']}/markets") or {}).get("data") or {}).get("markets") or []
    names = {c.get("id"): c.get("name") for c in ev.get("competitors") or []}
    for m in ms:
        if m.get("type") != "moneyline" or "player" in (m.get("subType") or "") or m.get("status") != "active": continue
        if (m.get("name") or "").strip().lower() not in ("moneyline", "match result", "1x2", "3-way moneyline", "full time result"): continue
        res = {}
        for sel in m.get("selections") or []:
            if not sel: continue
            s = sel[0]  # offres classées du meilleur prix au moins bon
            lab = names.get(s.get("competitorId")) or ("Draw" if "draw" in (s.get("name") or "").lower() or "tie" in (s.get("name") or "").lower() else None)
            if lab and s.get("odds") not in (None, 0): res[lab] = s["odds"]
        if len(res) >= 2: return res
    return None


def main():
    try:
        with open(OUT, encoding="utf-8") as f: db = json.load(f)
    except Exception: db = {}
    now, snaps = time.time(), 0
    for t in tournaments():
        r = get(f"{API}/v1/tournaments/{t['id']}/events?limit=100") or {}
        for ev in r.get("data") or []:
            try: start = ts(ev["scheduled"])
            except Exception: continue
            if ev.get("status") != "not_started" or not now < start <= now + AHEAD: continue
            px = best_prices(ev)
            if not px: continue
            comps = sorted(ev.get("competitors") or [], key=lambda c: c.get("seq", 0))
            db[str(ev["id"])] = {"name": ev.get("name"), "league": t.get("name"), "t1": comps[0]["name"] if comps else None,
                                 "t2": comps[1]["name"] if len(comps) > 1 else None, "start": start, "at": round(now), "odds": px}
            snaps += 1
    db = {k: v for k, v in db.items() if v["start"] > now - KEEP}
    with open(OUT + ".tmp", "w", encoding="utf-8") as f: json.dump(db, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(OUT + ".tmp", OUT)
    print(f"{snaps} relevés de matchs proches, {len(db)} matchs en base")


if __name__ == "__main__":
    main()
