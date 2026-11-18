#!/usr/bin/env python3
"""Gera assets/contribuicoes-{light,dark}.svg: calendário de contribuições com varredura animada.

Só biblioteca padrão. Fonte: calendário de contribuições do perfil (GraphQL), o mesmo do gráfico do GitHub.
Uso:
  GITHUB_TOKEN=... python3 tools/contribuicoes.py --user LucasRikelmi --out assets
  python3 tools/contribuicoes.py --dados calendario.json --out assets        # offline
"""
import argparse, datetime as dt, json, os, urllib.request, urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
G = json.load(open(os.path.join(AQUI, "glyphs.json"), encoding="utf-8"))
ADV = G["advance"] / G["upem"]
BRT = dt.timezone(dt.timedelta(hours=-3))

T = {
    "light": dict(win="#ffffff", bar="#f3f5f8", line="#dde2e8", ink="#0f1419", muted="#5b6573", dim="#c3cad3",
                  ok="#15803d", accent="#5b3fd9", data="#0369a1", flash="#0369a1", track="#eef1f5", zero="#e6eaef",
                  lv=["#9d8ff0", "#7a66e3", "#5b3fd9", "#3b2299"]),
    "dark": dict(win="#11161d", bar="#19202b", line="#2a3340", ink="#e7eaef", muted="#8b96a5", dim="#2e3744",
                 ok="#4ade80", accent="#a99bff", data="#5cc8ff", flash="#5cc8ff", track="#19202b", zero="#1c2430",
                 lv=["#5e52a8", "#8073dc", "#a99bff", "#dcd5ff"]),
}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# ── dados ────────────────────────────────────────────────────────────────────
QUERY = """query($login: String!, $from: DateTime!, $to: DateTime!) { user(login: $login) {
  contributionsCollection(from: $from, to: $to) {
    contributionCalendar { weeks { contributionDays { date contributionCount } } }
    totalCommitContributions totalPullRequestContributions totalIssueContributions
    totalPullRequestReviewContributions totalRepositoryContributions
    commitContributionsByRepository(maxRepositories: 100) { contributions(first: 100) { nodes { occurredAt commitCount } } }
    pullRequestContributions(first: 100) { nodes { occurredAt } }
    issueContributions(first: 100) { nodes { occurredAt } }
    pullRequestReviewContributions(first: 100) { nodes { occurredAt } }
    repositoryContributions(first: 100) { nodes { occurredAt } } } } }"""
TIPOS = [("commits", "commits"), ("prs", "PRs"), ("issues", "issues"), ("revisoes", "revisões"), ("repos", "repositórios")]


def _brt(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(BRT).date().isoformat()


def buscar(user, token):
    """Mesmo calendário do perfil (GraphQL contributionCalendar) + detalhamento por tipo.
    Uma consulta só (custo baixo); listas paginadas em 100, os totais por tipo vêm dos campos total*."""
    # Sem from/to a API corta os dias em UTC; com o fuso de Brasília no intervalo, os dias batem com o perfil.
    agora = dt.datetime.now(BRT)
    fim = agora.replace(hour=23, minute=59, second=59, microsecond=0)
    ini = (fim - dt.timedelta(days=365)).replace(hour=0, minute=0, second=0) + dt.timedelta(days=1)
    body = json.dumps({"query": QUERY, "variables": {"login": user, "from": ini.isoformat(), "to": fim.isoformat()}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "perfil-contribuicoes"})
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    if "errors" in resp:
        raise SystemExit(f"GraphQL: {resp['errors']}")
    cc = resp["data"]["user"]["contributionsCollection"]
    total = {d["date"]: d["contributionCount"] for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]}

    outros = {}
    for k, campo in (("prs", "pullRequestContributions"), ("issues", "issueContributions"),
                     ("revisoes", "pullRequestReviewContributions"), ("repos", "repositoryContributions")):
        for n in cc[campo]["nodes"]:
            outros.setdefault(_brt(n["occurredAt"]), {}).setdefault(k, 0)
            outros[_brt(n["occurredAt"])][k] += 1
    nodes = [n for r in cc["commitContributionsByRepository"] for n in r["contributions"]["nodes"]]

    # Commits vêm agregados por dia; o carimbo pode ser meia-noite no fuso da consulta ou em UTC.
    # Escolhe a leitura que fecha com o calendário em mais dias.
    def montar(chave):
        det = {d: dict(v) for d, v in outros.items()}
        for n in nodes:
            det.setdefault(chave(n["occurredAt"]), {}).setdefault("commits", 0)
            det[chave(n["occurredAt"])]["commits"] += n["commitCount"]
        ok = sum(1 for d, n in total.items() if n and sum(det.get(d, {}).values()) == n)
        return ok, det
    _, det = max(montar(lambda s: s[:10]), montar(_brt), key=lambda x: x[0])

    dias = {}
    for d, n in total.items():
        v = {k: det.get(d, {}).get(k, 0) for k, _ in TIPOS}
        resto = n - sum(v.values())
        if resto:
            v["outros"] = resto  # o calendário conta algo que as listas não trouxeram (ou vice-versa)
        dias[d] = {"total": n, **{k: x for k, x in v.items() if x}}
    tot = {"commits": cc["totalCommitContributions"], "prs": cc["totalPullRequestContributions"],
           "issues": cc["totalIssueContributions"], "revisoes": cc["totalPullRequestReviewContributions"],
           "repos": cc["totalRepositoryContributions"]}
    return {"dias": dias, "totais": tot}


def normalizar(dados):
    """Aceita o formato novo ({dias, totais}) ou o antigo ({data: total})."""
    if "dias" in dados:
        return dados
    return {"dias": {d: {"total": n} for d, n in dados.items()}, "totais": None}


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
def gerar(dados, user, th):
    cal = {d: v["total"] for d, v in dados["dias"].items()}
    tot = dados["totais"]
    c = T[th]
    t = Txt()
    datas = sorted(dt.date.fromisoformat(d) for d in cal)
    ini, fim = datas[0], datas[-1]
    ini -= dt.timedelta(days=ini.isoweekday() % 7)  # a grade começa no domingo, como no perfil
    dias = [ini + dt.timedelta(d) for d in range((fim - ini).days + 1)]
    no_periodo = {dt.date.fromisoformat(d): n for d, n in cal.items() if n > 0}
    total = sum(no_periodo.values())
    seq = best = 0
    for d in dias:
        seq = seq + 1 if no_periodo.get(d) else 0
        best = max(best, seq)

    W, H, bar = 1000, 322 if tot else 300, 40
    gx, gy, cw, ch = 66, 112, 16.3, 16.5
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
    o.append(t(f'gh api graphql -F login={user} -f query=@calendario.graphql', 28 + 4 * 14 * ADV, 74, 14, c["ink"]))

    mes_ant = None
    for w in range(ncol):
        d = dias[w * 7]
        if d.month != mes_ant and w < ncol - 2:
            o.append(t(MESES[d.month - 1], gx + w * cw, gy - 8, 11, c["muted"]))
            mes_ant = d.month
    for r, nome in ((1, "seg"), (3, "qua"), (5, "sex")):
        o.append(t(nome, gx - 38, gy + r * ch + 10, 11, c["muted"]))

    cells = []
    nz = sorted(no_periodo.values())
    q = [nz[min(len(nz) - 1, int(len(nz) * f))] for f in (.25, .5, .75)] if nz else [0, 0, 0]
    for i, d in enumerate(dias):
        w, r = divmod(i, 7)
        x, y = gx + w * cw, gy + r * ch + 11.5
        n = no_periodo.get(d, 0)
        delay = f"animation-delay:{DUR * (w + .5) / ncol:.2f}s"
        fs = 10.5
        if n == 0:
            cells.append(t("0", x + fs * ADV / 2, y, fs, c["dim"], cls="hz", style=delay))
        else:
            lv = 0 if n <= q[0] else 1 if n <= q[1] else 2 if n <= q[2] else 3
            s_ = str(min(n, 99))  # 2 caracteres por célula mantêm a grade alinhada; acima de 99 o exato fica no calendario.json
            cells.append(t(s_, x + (2 - len(s_)) * fs * ADV / 2, y, fs, c["lv"][lv], bold=True, cls=f"h{lv}", style=delay))
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
    resumo = f"{total} {'contribuição indexada' if total == 1 else 'contribuições indexadas'} · {len(no_periodo)} dias ativos · maior sequência: {best} {'dia' if best == 1 else 'dias'}"
    o.append(t(resumo, 50, sy, 13, c["ink"]))
    o.append(f'<rect class="cur" x="{50 + (len(resumo) + 1) * 13 * ADV:.1f}" y="{sy - 12}" width="8" height="15" fill="{c["ink"]}"/>')
    if tot:
        tipos = " · ".join(f"{tot[k]} {nome}" for k, nome in TIPOS if tot[k])
        o.append(t("↳", 30, sy + 22, 13, c["muted"]) if "↳" in G["glyphs"]["mono"] else "")
        o.append(t(tipos, 50, sy + 22, 13, c["muted"]))
    lx = W - 28 - len("mais") * 11 * ADV
    o.append(t("mais", lx, sy, 11, c["muted"]))
    for k, col in enumerate(reversed([c["dim"]] + c["lv"])):
        lx -= 14
        o.append(f'<rect x="{lx:.1f}" y="{sy - 10}" width="11" height="11" rx="2.5" fill="{c["zero"] if k == 4 else col}"/>')
    lx -= 10 + len("menos") * 11 * ADV
    o.append(t("menos", lx, sy, 11, c["muted"]))
    o.append(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="14" fill="none" stroke="{c["line"]}" stroke-width="1.5"/>')

    css = (f".scan{{animation:scan {DUR}s linear infinite}}"
           f"@keyframes scan{{0%{{transform:translateX(0);opacity:1}}97%{{opacity:1}}100%{{transform:translateX({gw + 4:.1f}px);opacity:0}}}}"
           + f".hz{{animation:hz {DUR}s linear infinite}}@keyframes hz{{0%{{fill:{c['muted']}}}6%,100%{{fill:{c['dim']}}}}}"
           + "".join(f".h{i}{{animation:h{i} {DUR}s linear infinite}}"
                     f"@keyframes h{i}{{0%{{fill:{c['ink']}}}3%{{fill:{c['flash']}}}10%,100%{{fill:{col}}}}}"
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


def rodape(th):
    c = T[th]
    t = Txt()
    W, H = 1000, 118
    o = [f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="14" fill="{c["win"]}" stroke="{c["line"]}" stroke-width="1.5"/>']
    sz, x0, y1, y2 = 15, 32, 50, 86
    adv = sz * ADV
    o.append(t("lucas@github", x0, y1, sz, c["ok"]))
    o.append(t(":~$", x0 + 12 * adv, y1, sz, c["muted"]))
    o.append(t("exit", x0 + 16 * adv, y1, sz, c["ink"]))
    w = 4 * adv
    o.append(f'<g class="ty" transform="translate({w:.1f} 0)"><rect x="{x0 + 16 * adv:.1f}" y="{y1 - sz}" width="{w + 4:.1f}" height="{sz + 6}" fill="{c["win"]}"/></g>')
    msg = "obrigado pela visita!"
    line2 = (t(">", x0, y2, sz, c["muted"]) + t(msg, x0 + 2 * adv, y2, sz, c["ok"])
             + f'<rect class="cur" x="{x0 + (3 + len(msg)) * adv:.1f}" y="{y2 - sz + 2}" width="{adv:.1f}" height="{sz + 2}" fill="{c["ink"]}"/>')
    fim = "[sessão encerrada · código 0]"
    line2 += t(fim, W - 32 - len(fim) * 13 * ADV, y2, 13, c["muted"])
    o.append(f'<g class="l2">{line2}</g>')
    css = (".ty{animation:ty .5s steps(4,end) .6s both}@keyframes ty{from{transform:translateX(0)}}"
           ".l2{animation:l2 .4s ease-out 1.4s both}@keyframes l2{from{opacity:0}}"
           ".cur{animation:bl 1.06s steps(1) infinite}@keyframes bl{50%{opacity:0}}"
           "@media (prefers-reduced-motion:reduce){*{animation:none!important}}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
            f'aria-label="exit: obrigado pela visita!"><style>{css}</style><defs>{t.defs()}</defs>{"".join(o)}</svg>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="LucasRikelmi")
    ap.add_argument("--dados", help="JSON {AAAA-MM-DD: contagem} em vez de consultar a API")
    ap.add_argument("--out", default="assets")
    ap.add_argument("--rodape", action="store_true", help="gera só assets/rodape-{light,dark}.svg (estático, vai no main)")
    a = ap.parse_args()
    if a.rodape:
        for th in ("light", "dark"):
            with open(os.path.join(a.out, f"rodape-{th}.svg"), "w", encoding="utf-8") as f:
                f.write(rodape(th))
        return
    dados = normalizar(json.load(open(a.dados))) if a.dados else buscar(a.user, os.environ["GITHUB_TOKEN"])
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "calendario.json"), "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=1, sort_keys=True, ensure_ascii=False)  # dados brutos publicados junto, para conferência
    for th in ("light", "dark"):
        with open(os.path.join(a.out, f"contribuicoes-{th}.svg"), "w", encoding="utf-8") as f:
            f.write(gerar(dados, a.user, th))
    print(f"{sum(v['total'] for v in dados['dias'].values())} contribuições; totais por tipo: {dados['totais']}")


if __name__ == "__main__":
    main()
