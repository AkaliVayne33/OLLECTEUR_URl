"""Collecteur des clôtures Hyperliquid (marchés outcome HIP-4 : sport).
Les bougies d'un marché Hyperliquid disparaissent à son règlement : ce collecteur relève, juste après chaque coup
d'envoi, le prix de clôture de chaque côté (médiane des clôtures minute des 5 dernières minutes, sinon la dernière des
15 minutes précédentes) et l'écrit dans hl_closes.json : {"#<jeton>": {"k": coup d'envoi, "c": prix}}.
Aucun compte : marchés publics uniquement. Bibliothèque standard seulement."""
import json, os, statistics, time, urllib.request
from datetime import datetime, timezone

INFO = "https://api.hyperliquid.xyz/info"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hl_closes.json")
RETRY, KEEP = 12 * 3600, 120 * 86400


def post(body):
    for k in range(3):
        try:
            req = urllib.request.Request(INFO, json.dumps(body).encode(), {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r: return json.load(r)
        except Exception as e:
            if getattr(e, "code", 0) in (400, 404, 422): return None
            time.sleep(2 * (k + 1))


def kv(desc): return dict(x.split(":", 1) for x in (desc or "").split("|") if ":" in x)


def kick_of(desc):
    s = kv(desc).get("scheduledStart")
    try: return int(datetime.strptime(s, "%Y%m%d-%H%M").replace(tzinfo=timezone.utc).timestamp())
    except Exception: return None


def main():
    try:
        with open(OUT, encoding="utf-8") as f: db = json.load(f)
    except Exception: db = {}
    meta = post({"type": "outcomeMeta"}) or {}
    qdesc = {o: q.get("description") for q in meta.get("questions", []) for o in q.get("namedOutcomes", []) + [q.get("fallbackOutcome")]}
    now, done = time.time(), 0
    for o in meta.get("outcomes", []):
        k = kick_of(o.get("description")) or kick_of(qdesc.get(o["outcome"]))
        if not k or not k + 60 <= now <= k + RETRY: continue
        for side in (0, 1):
            coin = f"#{o['outcome'] * 10 + side}"
            if coin in db: continue
            cd = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1m", "startTime": (k - 900) * 1000, "endTime": k * 1000}})
            cd = [c for c in cd or [] if c["t"] < k * 1000]  # la bougie qui s'ouvre au coup d'envoi est déjà en direct
            if not cd: continue
            last = [float(c["c"]) for c in cd if c["t"] / 1000 >= k - 300]
            db[coin] = {"k": k, "c": round(statistics.median(last) if last else float(cd[-1]["c"]), 5)}; done += 1
    db = {c: v for c, v in db.items() if v["k"] > now - KEEP}
    with open(OUT + ".tmp", "w", encoding="utf-8") as f: json.dump(db, f, separators=(",", ":"))
    os.replace(OUT + ".tmp", OUT)
    print(f"{len(meta.get('outcomes', []))} marchés Hyperliquid, {done} clôtures relevées, {len(db)} en base")


if __name__ == "__main__":
    main()
