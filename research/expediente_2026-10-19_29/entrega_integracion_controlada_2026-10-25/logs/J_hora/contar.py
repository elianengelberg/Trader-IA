import sys
import xml.etree.ElementTree as ET
r = ET.parse(sys.argv[1]).getroot()
out = []
for c in r.iter("testcase"):
    st = "passed"
    for k in ("failure", "error", "skipped"):
        if c.find(k) is not None:
            st = k
    if "five_restored" in c.get("name") or "day" in c.get("name") or st != "passed":
        out.append(f"{c.get('name')[:70]}={st}")
tot = {k: sum(1 for c in r.iter('testcase') if c.find(k) is not None) for k in ('failure', 'error', 'skipped')}
print(f"tests={sum(1 for _ in r.iter('testcase'))} {tot} :: " + " | ".join(out))
