"""
Build do dashboard NI Negócios.
Gera data.js com 3 visões: período total, abril, maio.
"""
import csv
import io
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from collections import Counter, defaultdict

# ─── CONFIG ─────────────────────────────────────────────────────────────
SHEETS = [
    {"id": "1yd4nJ1SKuIvDHrjC3U4qmwQ5hYUE43QLpy2Jc2dWD3A", "emp": "Casa no Antares", "corretor": "Gedson"},
    {"id": "1LX2da2em-wAuKEY-STLrsSSDWLHthvMfGtQO5cyqK7A", "emp": "Edf. Jorge",      "corretor": "Tatiana"},
    {"id": "1IT1HQIo6D0H4l7BnEqURLawADgKtEn4UtS0M46PiV_c", "emp": "Edf. Greco",      "corretor": "Rose"},
    {"id": "1bh7_Kskh0AWelAgJHL81g0QfM84ftPA7fOEL2cHBoWc", "emp": "Edf. Sensia",     "corretor": "Fernanda"},
    {"id": "1XL1IdmiGtzvwwtFYq_7cfLDuZAprjwq5WeWmucLyocs", "emp": "Edf. Sensia",     "corretor": "Guilherme"},
    {"id": "1QmkWwavrGXhDtYcdPqbYgmCB3E8LBV2pt355BIMk85U", "emp": "Edf. Sensia",     "corretor": "Nath"},
    {"id": "1r4njxyOa17slTPMU0GDSkoxftTuduDRmPK8XvgsTXKc", "emp": "Edf. Guaxuma",    "corretor": "Fernanda"},
    {"id": "1cMELjUGTsSmVNVYlHQmpeNqk4ic_eo9J7M23BWVGnJI", "emp": "JTR Jatiúca",     "corretor": "Nathalia"},
    {"id": "1lHgTHSYo1Bo5xd3AOWNXB_PtcrpfcEBgZMs9GbgOx5Y", "emp": "Jatiúca",         "corretor": "Adriana"},
]

META_AD_ACCOUNT = "act_916115436468748"

# Período "total" do relatório
PERIOD_START = os.environ.get("PERIOD_START") or "2026-04-01"
PERIOD_END = os.environ.get("PERIOD_END") or "2026-05-04"


# ─── HELPERS ─────────────────────────────────────────────────────────────
def parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def norm_status(s):
    s = (s or "").strip().lower()
    if not s:
        return "sem_status"
    if "proposta" in s:
        return "proposta"
    if "desqualif" in s:
        return "desqualificado"
    if "perdid" in s:
        return "perdido"
    if "outros produtos" in s:
        return "outros_produtos"
    if "não é momento" in s or "nao e momento" in s:
        return "nao_momento"
    if "qualific" in s:
        return "qualificado"
    if "reuni" in s or "visit" in s:
        return "visita"
    if "atendimento" in s:
        return "em_atendimento"
    if "venda" in s or "vendido" in s:
        return "venda"
    return "outro"


def cat_motivo(obs):
    o = (obs or "").lower()
    if not o:
        return "Sem motivo registrado"
    if any(k in o for k in ["não atend", "nao atend", "sem sucesso", "não respond", "nao respond", "parou de respond", "nada de respond"]):
        return "Não responde / não atende"
    if "repet" in o:
        return "Lead repetido"
    if "não gost" in o or "nao gost" in o:
        return "Não gostou do imóvel/região"
    if any(k in o for k in ["valor", "preço", "preco", "caro"]):
        return "Valor / orçamento"
    if any(k in o for k in ["outra região", "outra regiao", "outra cidade", "goian"]):
        return "Buscava outra região"
    if any(k in o for k in ["achou", "comprou", "fechou com outr"]):
        return "Comprou com concorrente"
    if any(k in o for k in ["número errado", "numero errado", "errado"]):
        return "Lead inválido"
    return "Motivo ambíguo (revisar)"


def fetch_csv(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ni-report"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def label_period(start, end):
    a = datetime.strptime(start, "%Y-%m-%d").strftime("%d/%m")
    b = datetime.strptime(end, "%Y-%m-%d").strftime("%d/%m")
    return f"{a} a {b}"


# ─── PROCESSA UMA VIEW (período arbitrário) ─────────────────────────────
def process_view(rows_by_sheet, start_str, end_str):
    ini = datetime.strptime(start_str, "%Y-%m-%d")
    fim = datetime.strptime(end_str, "%Y-%m-%d") + timedelta(hours=23, minutes=59, seconds=59)

    per_emp = []
    totals = Counter()
    motivos = Counter()
    daily = defaultdict(lambda: Counter())

    for sheet, rows in zip(SHEETS, rows_by_sheet):
        emp_data = Counter()
        for row in rows:
            d = parse_date(row.get("Data de entrada", ""))
            if not d or d < ini or d > fim:
                continue
            st = norm_status(row.get("Status", ""))
            obs = row.get("Observação", "") or ""
            emp_data[st] += 1
            totals[st] += 1
            day_key = d.strftime("%Y-%m-%d")
            daily[day_key]["total"] += 1
            mapping = {"em_atendimento": "atend", "qualificado": "qual"}
            if st in ("em_atendimento", "visita", "qualificado", "proposta"):
                daily[day_key][mapping.get(st, st)] += 1
            elif st in ("desqualificado", "perdido"):
                daily[day_key]["perda"] += 1
                motivos[cat_motivo(obs)] += 1

        per_emp.append({
            "emp": sheet["emp"],
            "corretor": sheet["corretor"],
            "leads": sum(emp_data.values()),
            "atend": emp_data["em_atendimento"],
            "visita": emp_data["visita"],
            "qual": emp_data["qualificado"],
            "proposta": emp_data["proposta"],
            "perda": emp_data["desqualificado"] + emp_data["perdido"],
            "outros": emp_data["outros_produtos"] + emp_data["nao_momento"],
            "sem": emp_data["sem_status"],
        })

    per_emp.sort(key=lambda x: -x["leads"])

    # Daily series do período
    day = ini
    series = {"labels": [], "total": [], "perda": [], "atend": [], "visita": [], "qual": [], "proposta": []}
    while day <= fim:
        k = day.strftime("%Y-%m-%d")
        series["labels"].append(day.strftime("%d/%m"))
        for metric in ("total", "perda", "atend", "visita", "qual", "proposta"):
            series[metric].append(daily[k][metric])
        day += timedelta(days=1)

    n_total = sum(totals.values())
    perdidos = totals["desqualificado"] + totals["perdido"]
    motivos_total = sum(motivos.values())

    return {
        "totals": dict(totals),
        "n_total": n_total,
        "perdidos": perdidos,
        "pct_perda": round(perdidos / n_total * 100, 1) if n_total else 0,
        "empreend": per_emp,
        "motivos": [{"label": m, "value": n, "pct": round(n / motivos_total * 100, 1) if motivos_total else 0}
                    for m, n in motivos.most_common()],
        "motivos_total": motivos_total,
        "series": series,
    }


# ─── META API ────────────────────────────────────────────────────────────
def fetch_meta(start_str, end_str):
    token = os.environ.get("META_ACCESS_TOKEN")
    if not token:
        print(f"  [Meta] sem token, pulando", file=sys.stderr)
        return None

    base = f"https://graph.facebook.com/v21.0/{META_AD_ACCOUNT}/insights"
    params = {
        "fields": "spend,impressions,clicks,ctr,frequency,reach,actions,cost_per_action_type,inline_link_clicks",
        "time_range": json.dumps({"since": start_str, "until": end_str}),
        "level": "account",
        "access_token": token,
    }
    url = f"{base}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  [Meta] erro: {e}", file=sys.stderr)
        return None

    if not data.get("data"):
        return None

    d = data["data"][0]
    actions = {a["action_type"]: int(a["value"]) for a in d.get("actions", [])}
    leads_form = actions.get("lead", 0)
    msg_started = actions.get("onsite_conversion.messaging_conversation_started_7d", 0)
    total_meta = leads_form + msg_started
    spend = float(d["spend"])

    return {
        "spend": spend,
        "impressions": int(d["impressions"]),
        "clicks": int(d["clicks"]),
        "ctr": round(float(d["ctr"]), 2),
        "frequency": round(float(d["frequency"]), 2),
        "reach": int(d["reach"]),
        "leads_form": leads_form,
        "msg_started": msg_started,
        "total_meta": total_meta,
        "cpl": round(spend / total_meta, 2) if total_meta else 0,
    }


# ─── PLANO DE AÇÃO ───────────────────────────────────────────────────────
def build_plan(stats):
    plan = []
    nao_responde = next((m for m in stats["motivos"] if "Não responde" in m["label"]), None)
    if nao_responde and nao_responde["pct"] > 30:
        plan.append({
            "tag": "Prioridade alta", "cls": "crit", "icon": "alert",
            "title": "Resgatar a base não respondida",
            "desc": f"<b>{nao_responde['value']} leads</b> do período entraram e não retornaram contato. Antes de aumentar volume, rodar uma cadência de reengajamento e revisar tempo médio de primeiro toque. <b>Maior ponto de alavancagem do mês.</b>",
        })

    sensia_total = sum(e["leads"] for e in stats["empreend"] if e["emp"] == "Edf. Sensia")
    if sensia_total > 0:
        plan.append({
            "tag": "Time comercial", "cls": "proc", "icon": "team",
            "title": "Sensia, calibrar distribuição",
            "desc": "3 corretores no mesmo produto. A <b>única proposta do período saiu daqui</b>, o produto tem demanda. Revisar como leads são distribuídos e padronizar a abordagem pode acelerar o ciclo.",
        })

    sem_status = sum(e["sem"] for e in stats["empreend"])
    if sem_status > 0 and stats["n_total"] > 0:
        pct = sem_status / stats["n_total"] * 100
        plan.append({
            "tag": "Processo", "cls": "proc", "icon": "process",
            "title": "Padronizar planilhas",
            "desc": f"<b>{pct:.0f}% dos leads sem status</b> ({sem_status} leads). Definir status obrigatório e motivo de perda destrava a próxima camada de análise por produto.",
        })

    return plan


# ─── BUILD UMA VIEW COMPLETA ─────────────────────────────────────────────
def build_view(rows_by_sheet, start_str, end_str, label):
    print(f"\n[{label}] {start_str} a {end_str}", file=sys.stderr)
    stats = process_view(rows_by_sheet, start_str, end_str)
    print(f"  {stats['n_total']} leads, {stats['pct_perda']}% perda", file=sys.stderr)

    meta = fetch_meta(start_str, end_str)
    if meta:
        print(f"  Meta: R$ {meta['spend']:,.2f}, {meta['total_meta']} leads, CPL R$ {meta['cpl']:.2f}", file=sys.stderr)

    return {
        "period": {"start": start_str, "end": end_str, "label": label_period(start_str, end_str), "name": label},
        "stats": stats,
        "meta": meta,
        "plan": build_plan(stats),
    }


# ─── MAIN ────────────────────────────────────────────────────────────────
def main():
    print("Baixando planilhas...", file=sys.stderr)
    rows_by_sheet = []
    for sheet in SHEETS:
        try:
            rows = fetch_csv(sheet["id"])
            print(f"  {sheet['emp']} ({sheet['corretor']}): {len(rows)} linhas", file=sys.stderr)
        except Exception as e:
            print(f"  {sheet['emp']} ({sheet['corretor']}): ERRO {e}", file=sys.stderr)
            rows = []
        rows_by_sheet.append(rows)

    # Define os 3 períodos. "total" usa as env vars; abril e maio são fixos.
    views = {
        "total": build_view(rows_by_sheet, PERIOD_START, PERIOD_END, "Período total"),
        "abril": build_view(rows_by_sheet, "2026-04-01", "2026-04-30", "Abril"),
        "maio":  build_view(rows_by_sheet, "2026-05-01", "2026-05-04", "Maio"),
    }

    payload = {
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "default_view": "total",
        "views": views,
    }

    out = os.path.join(os.path.dirname(__file__), "data.js")
    with open(out, "w", encoding="utf-8") as f:
        f.write("window.NI_DATA = ")
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    print(f"\nGerado: {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
