import requests
from collections import Counter

BASE = "https://api.jolpi.ca/ergast/f1"

rows = []
for off in range(0, 500, 100):
    d = requests.get(f"{BASE}/2024/results/",
                     params={"limit": 100, "offset": off}).json()["MRData"]
    for race in d["RaceTable"]["Races"]:
        rows.extend(race["Results"])

print("result rows:", len(rows))

keys = Counter(k for r in rows for k in r)
print("\nKEY PRESENCE:")
for k, c in keys.most_common():
    flag = "  <-- OPTIONAL" if c < len(rows) else ""
    print(f"  {k:<14} {c:>4}/{len(rows)}{flag}")

print("\npositionText values:", sorted(set(r['positionText'] for r in rows)))

dnf = [r for r in rows if 'Time' not in r]
print("\nDNF sample:", {k: v for k, v in dnf[0].items()
                        if k not in ('Driver', 'Constructor')} if dnf else "none")