"""Fill the Wayback cache for Test E in parallel, with the same URL selection as run_e.py."""
import json, re, sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import run_e
from run_e import allowed, NE
split = sys.argv[1]
ev_by = defaultdict(list)
for e in json.load(open("data/5pils/dataset/retrieval_results/evidence_urls.json")): ev_by[e["image_path"]].append(e)
cases = [x for x in json.load(open("data/5pils/dataset/%s.json" % split)) if x["type_of_image"] == "out-of-context"
         and NE not in (x["claimed_date"], x["date"]) and ev_by.get(x["image_path"]) and re.search(r"(19|20)\d\d", x["claimed_date"])]
urls = []
for x in cases:
    pages = []
    for e in ev_by[x["image_path"]]:
        if allowed(e["raw_url"]) and e["raw_url"] not in [p[0] for p in pages]:
            pages.append((e["raw_url"], [u for u in e.get("image_urls", []) if allowed(u)]))
    n = 0
    for i, (pu, imgs) in enumerate(pages):
        if i < 5: urls.append(pu)
        for u in imgs:
            if n >= 10: break
            n += 1; urls.append(u)
todo = [u for u in dict.fromkeys(urls) if u not in run_e.cache]
print("urls", len(set(urls)), "todo", len(todo), flush=True)
def job(u):
    run_e.first_capture(u)
with ThreadPoolExecutor(1) as ex:
    for k, _ in enumerate(ex.map(job, todo)):
        if k % 25 == 0:
            json.dump(run_e.cache, open(run_e.CACHE_F, "w")); print(k, flush=True)
json.dump(run_e.cache, open(run_e.CACHE_F, "w"))
print("done; failed lookups:", sum(u not in run_e.cache for u in todo))
