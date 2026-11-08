"""Builds the two pages the server hands out:
   ../web/vault.html  - the full Knowledge Vault (served only after a verified email-code sign-in)
   ../web/login.html  - the public sign-in page (contains no company knowledge)
Run from anywhere:  python3 frontend-src/build_frontend.py"""
import base64, json, pathlib, re
H = pathlib.Path(__file__).resolve().parent; A = H / "assets"; OUT = H.parent / "web"
b64 = lambda n: base64.b64encode((A / n).read_bytes()).decode()
kb = json.dumps(json.load(open(H / "kb.json")), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
t = (H / "template.html").read_text()
# the access-code login of the offline file is not used in server mode; a random hash means no code can ever match
t = (t.replace("/*AH*/0", "1").replace("__KB__", kb).replace("__OUTFIT__", b64("outfit-latin.woff2"))
      .replace("__LOGOP__", "data:image/png;base64," + b64("logo_p.png")).replace("__BD__", (A / "bd_main.json").read_text())
      .replace("__LOGOD__", "data:image/png;base64," + b64("logo_d.png")).replace("__LOGO__", "data:image/png;base64," + b64("logo.png")))
t = t.replace("/*SA*/false", "true").replace("/*SRV*/false", "true")
three = (A / "three.min.js").read_text(); assert "</script" not in three
t = re.sub(r"<!--THREE-->.*?<!--/THREE-->", lambda m: "<script>" + three + "</script>", t, flags=re.S)
page = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow"><style>:root{color-scheme:light}html,body{margin:0}</style></head><body>' + t + "</body></html>")
OUT.mkdir(exist_ok=True); (OUT / "vault.html").write_text(page)
lg = (H / "login.tpl.html").read_text().replace("__OUTFIT__", b64("outfit-latin.woff2")).replace("__LOGO__", b64("logo_p.png"))
(OUT / "login.html").write_text(lg)
print("vault.html", len(page), "| login.html", len(lg))
