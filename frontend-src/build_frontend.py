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
# public sign-in page = the SAME design (3D scene, tagline, card) built from the same template, with NO knowledge data inside
g = (H / "template.html").read_text()
g = (g.replace("/*AH*/0", "1").replace("__KB__", "[]").replace("__OUTFIT__", b64("outfit-latin.woff2"))
      .replace("__LOGOP__", "data:image/png;base64," + b64("logo_p.png")).replace("__BD__", (A / "bd_main.json").read_text())
      .replace("__LOGOD__", "data:image/png;base64," + b64("logo_d.png")).replace("__LOGO__", "data:image/png;base64," + b64("logo.png")))
g = g.replace("/*GATE*/false", "true")
# the public page must hold NO company knowledge: blank every embedded data block (contacts, roadmap topics, notes)
for name in ("DEPTS", "P1", "P2", "P3", "NOTES"):
    g, n = re.subn(r"const " + name + r" = \[.*?\n?\];", "const " + name + " = [];", g, count=1, flags=re.S); assert n == 1, name
for bad in ("poc:'Mr.", "poc:'Ms.", "Mr. Mahmudul", "Sharfuddin", "Abdullah As Sadiq", "Mallik Samir", "NTTN foreign shareholding", "Q160", "Chapter 10.2", "BTRC publications"):
    assert bad not in g, "company data would leak into the public sign-in page: " + bad
g = re.sub(r"<!--THREE-->.*?<!--/THREE-->", lambda m: "<script>" + three + "</script>", g, flags=re.S)
lg = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
      '<meta name="robots" content="noindex,nofollow"><style>:root{color-scheme:light}html,body{margin:0}</style></head><body>' + g + "</body></html>")
(OUT / "login.html").write_text(lg)
print("vault.html", len(page), "| login.html", len(lg))
