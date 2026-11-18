#!/usr/bin/env python3
"""Gera assets/contribuicoes-{light,dark}.svg: calendário de commits públicos com varredura animada.

Só biblioteca padrão. Fonte: API de busca de commits do GitHub (só repositórios públicos, branch padrão).
Uso:
  GITHUB_TOKEN=... python3 tools/contribuicoes.py --user LucasRikelmi --out assets
  python3 tools/contribuicoes.py --dados commits.json --out assets          # offline
"""
import argparse, datetime as dt, json, os, urllib.request, urllib.parse
from collections import Counter

AQUI = os.path.dirname(os.path.abspath(__file__))
G = json.load(open(os.path.join(AQUI, "glyphs.json"), encoding="utf-8"))
ADV = G["advance"] / G["upem"]
BRT = dt.timezone(dt.timedelta(hours=-3))

T = {
    "light": dict(win="#ffffff", bar="#f3f5f8", line="#dde2e8", ink="#0f1419", muted="#5b6573", dim="#c3cad3",
                  ok="#15803d", accent="#5b3fd9", data="#0369a1", flash="#0369a1", track="#eef1f5",
                  lv=["#9d8ff0", "#7a66e3", "#5b3fd9", "#3b2299"]),
    "dark": dict(win="#11161d", bar="#19202b", line="#2a3340", ink="#e7eaef", muted="#8b96a5", dim="#2e3744",
                 ok="#4ade80", accent="#a99bff", data="#5cc8ff", flash="#5cc8ff", track="#19202b",
                 lv=["#5e52a8", "#8073dc", "#a99bff", "#dcd5ff"]),
}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# ── dados ────────────────────────────────────────────────────────────────────
def buscar(user, token):
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({"q": f"author:{user}", "per_page": 100, "page": page, "sort": "author-date"})
        req = urllib.request.Request(f"https://api.github.com/search/commits?{q}", headers={
            "Accept": "application/vnd.github+json", "User-Agent": "perfil-contribuicoes",
            **({"Authorization": f"Bearer {token}"} if token else {})})
        with urllib.request.urlopen(req, timeout=30) as r:
            items = json.load(r)["items"]
        out += [{"repo": i["repository"]["full_name"], "date": i["commit"]["author"]["date"], "sha": i["sha"]} for i in items]
        if len(items) < 100 or page == 10:  # a busca devolve no máximo 1000 resultados
            return out
        page += 1


def dia(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(BRT).date()


# ── texto como path (sem fonte externa) ─────────────────────────────────────
class Txt:
    def __init__(self):
        self.used = set()

    def __call__(self, s, x, y, size, fill, bold=False, cls="", style=""):
        face = "mono-b" if bold else "mono"
        k = size / G["upem"]
        parts = []
        for i, ch in enumerate(s):
            if ch == " " or ch not in G["glyphs"][face]:
                continue
            self.used.add((face, ch))
            parts.append(f'<use href="#{gid(face, ch)}" x="{(x + i * size * ADV) / k:.0f}" y="{-y / k:.0f}"/>')
        if not parts:
            return ""
        c = f' class="{cls}"' if cls else ""
        st = f' style="{style}"' if style else ""
        return f'<g fill="{fill}" transform="scale({k:.5f} {-k:.5f})"{c}{st}>{"".join(parts)}</g>'

    def defs(self):
        return "".join(f'<path id="{gid(f, ch)}" d="{G["glyphs"][f][ch]}"/>' for f, ch in sorted(self.used))


def gid(face, ch):
    return f"{'b' if face == 'mono-b' else 'r'}{ord(ch):x}"


def check(x, y, s, col):
    return f'<path d="M{x} {y - s * .45}l{s * .32} {s * .32} {s * .6}-{s * .7}" fill="none" stroke="{col}" stroke-width="{s * .16:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'


# ── SVG ─────────────────────────────────────────────────────────────────────
def gerar(commits, user, th, hoje):
    c = T[th]
    t = Txt()
    por_dia = Counter(dia(x["date"]) for x in commits)
    fim = hoje
    ini = fim - dt.timedelta(days=fim.isoweekday() % 7 + 52 * 7)  # domingo, 53 semanas
    dias = [ini + dt.timedelta(d) for d in range((fim - ini).days + 1)]
    no_periodo = {d: n for d, n in por_dia.items() if ini <= d <= fim}
    total = sum(no_periodo.values())
    repos = len({x["repo"] for x in commits if ini <= dia(x["date"]) <= fim})
    seq = best = 0
    for d in dias:
        seq = seq + 1 if no_periodo.get(d) else 0
        best = max(best, seq)

    W, H, bar = 1000, 300, 40
    gx, gy, cw, ch = 74, 112, 16.5, 16.5
    ncol = len(dias) // 7 + (1 if len(dias) % 7 else 0)
    DUR = 9.0
    o = []
    o.append(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="14" fill="{c["win"]}"/>')
    o.append(f'<path d="M1 15a14 14 0 0 1 14-14H{W - 15}a14 14 0 0 1 14 14V{bar}H1Z" fill="{c["bar"]}"/><path d="M1 {bar}.5H{W - 1}" stroke="{c["line"]}"/>')
    for i, col in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        o.append(f'<circle cx="{24 + i * 19}" cy="{bar / 2}" r="6" fill="{col}"/>')
    title = f"contribuições — @{user}"
    o.append(t(title, (W - len(title) * 13 * ADV) / 2, bar / 2 + 4.5, 13, c["muted"]))
    o.append(t("~ $", 28, 74, 14, c["ok"]))
    o.append(t('git log --since="1 year" --format=%as | uniq -c', 28 + 4 * 14 * ADV, 74, 14, c["ink"]))

    mes_ant = None
    for w in range(ncol):
        d = dias[w * 7]
        if d.month != mes_ant and w < ncol - 2:
            o.append(t(MESES[d.month - 1], gx + w * cw, gy - 8, 11, c["muted"]))
            mes_ant = d.month
    for r, nome in ((1, "seg"), (3, "qua"), (5, "sex")):
        o.append(t(nome, gx - 38, gy + r * ch + 12, 11, c["muted"]))

    cells = []
    for i, d in enumerate(dias):
        w, r = divmod(i, 7)
        x, y = gx + w * cw, gy + r * ch + 12
        n = no_periodo.get(d, 0)
        delay = f"animation-delay:{DUR * (w + .5) / ncol:.2f}s"
        if n == 0:
            cells.append(t("·", x + 1, y, 13, c["dim"]))
        else:
            lv = 0 if n < 3 else 1 if n < 8 else 2 if n < 20 else 3
            s = str(n) if n < 10 else "+"
            cells.append(t(s, x + 1, y, 13, c["lv"][lv], bold=True, cls=f"h{lv}", style=delay))
    o.append("".join(cells))

    gw, gh = ncol * cw, 7 * ch
    o.append(f'<defs><linearGradient id="sg" x1="0" x2="1"><stop offset="0" stop-color="{c["flash"]}" stop-opacity="0"/>'
             f'<stop offset=".85" stop-color="{c["flash"]}" stop-opacity=".18"/><stop offset="1" stop-color="{c["flash"]}" stop-opacity=".7"/></linearGradient>'
             f'<clipPath id="sc"><rect x="{gx - 4}" y="{gy - 2}" width="{gw + 8:.1f}" height="{gh + 4:.1f}"/></clipPath></defs>')
    o.append(f'<g clip-path="url(#sc)"><g class="scan"><rect x="{gx - 72}" y="{gy - 2}" width="70" height="{gh + 4:.1f}" fill="url(#sg)"/>'
             f'<rect x="{gx - 3}" y="{gy - 2}" width="2" height="{gh + 4:.1f}" fill="{c["flash"]}"/></g></g>')

    by = gy + gh + 34
    pw = 560
    o.append(t("[", 28, by + 4, 13, c["muted"]))
    o.append(f'<rect x="42" y="{by - 7}" width="{pw}" height="11" rx="2" fill="{c["track"]}"/>')
    o.append(f'<rect class="prog" x="42" y="{by - 7}" width="{pw}" height="11" rx="2" fill="{c["accent"]}"/>')
    o.append(t("]", 48 + pw, by + 4, 13, c["muted"]))
    o.append(t("indexando...", 72 + pw, by + 4, 13, c["data"], cls="a"))
    o.append(f'<g class="b">{check(72 + pw, by + 3, 13, c["ok"])}{t("pronto", 90 + pw, by + 4, 13, c["ok"])}</g>')

    sy = by + 30
    o.append(check(28, sy - 1, 14, c["ok"]))
    resumo = f"{total} commits · {len(no_periodo)} dias ativos · {repos} repositórios públicos · maior sequência: {best} {'dia' if best == 1 else 'dias'}"
    o.append(t(resumo, 50, sy, 13, c["ink"]))
    o.append(f'<rect class="cur" x="{50 + (len(resumo) + 1) * 13 * ADV:.1f}" y="{sy - 12}" width="8" height="15" fill="{c["ink"]}"/>')
    o.append(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="14" fill="none" stroke="{c["line"]}" stroke-width="1.5"/>')

    css = (f".scan{{animation:scan {DUR}s linear infinite}}"
           f"@keyframes scan{{0%{{transform:translateX(0);opacity:1}}97%{{opacity:1}}100%{{transform:translateX({gw + 4:.1f}px);opacity:0}}}}"
           + "".join(f".h{i}{{animation:h{i} {DUR}s linear infinite}}"
                     f"@keyframes h{i}{{0%{{fill:{c['flash']}}}3%{{fill:{c['ink']}}}9%,100%{{fill:{col}}}}}"
                     for i, col in enumerate(c["lv"])) +
           f".prog{{transform-box:fill-box;transform-origin:0 50%;animation:prog {DUR}s linear infinite}}"
           f"@keyframes prog{{from{{transform:scaleX(0)}}}}"
           f".a{{opacity:0;animation:a {DUR}s steps(1) infinite}}@keyframes a{{0%{{opacity:1}}96%,100%{{opacity:0}}}}"
           f".b{{animation:b {DUR}s steps(1) infinite}}@keyframes b{{0%{{opacity:0}}96%,100%{{opacity:1}}}}"
           ".cur{animation:bl 1.06s steps(1) infinite}@keyframes bl{50%{opacity:0}}"
           "@media (prefers-reduced-motion:reduce){*{animation:none!important}.scan{opacity:0}}")
    label = f"Contribuições de @{user} nos últimos 12 meses: {resumo}."
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{label}">'
            f'<style>{css}</style><defs>{t.defs()}</defs>{"".join(o)}</svg>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="LucasRikelmi")
    ap.add_argument("--dados", help="JSON com [{repo, date, sha}] em vez de consultar a API")
    ap.add_argument("--hoje", help="AAAA-MM-DD (padrão: hoje em Brasília)")
    ap.add_argument("--out", default="assets")
    a = ap.parse_args()
    commits = json.load(open(a.dados)) if a.dados else buscar(a.user, os.environ.get("GITHUB_TOKEN"))
    hoje = dt.date.fromisoformat(a.hoje) if a.hoje else dt.datetime.now(BRT).date()
    os.makedirs(a.out, exist_ok=True)
    for th in ("light", "dark"):
        with open(os.path.join(a.out, f"contribuicoes-{th}.svg"), "w", encoding="utf-8") as f:
            f.write(gerar(commits, a.user, th, hoje))
    print(f"{len(commits)} commits lidos")


if __name__ == "__main__":
    main()
