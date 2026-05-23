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
    {"id": "1yd4nJ1SKuIvDHrjC3U4qmwQ5hYUE43QLpy2Jc2dWD3A", "emp": "Casa no Antares",       "corretor": "Gedson"},
    {"id": "1yd4nJ1SKuIvDHrjC3U4qmwQ5hYUE43QLpy2Jc2dWD3A", "emp": "Edf. Paradise Beach",   "corretor": "Gedson"},
    {"id": "1LX2da2em-wAuKEY-STLrsSSDWLHthvMfGtQO5cyqK7A", "emp": "Edf. Jorge",            "corretor": "Tatiana"},
    {"id": "1IT1HQIo6D0H4l7BnEqURLawADgKtEn4UtS0M46PiV_c", "emp": "Edf. Greco",            "corretor": "Rose"},
    {"id": "1bh7_Kskh0AWelAgJHL81g0QfM84ftPA7fOEL2cHBoWc", "emp": "Edf. Sensia",           "corretor": "Fernanda"},
    {"id": "1XL1IdmiGtzvwwtFYq_7cfLDuZAprjwq5WeWmucLyocs", "emp": "Edf. Sensia",           "corretor": "Guilherme"},
    {"id": "1QmkWwavrGXhDtYcdPqbYgmCB3E8LBV2pt355BIMk85U", "emp": "Edf. Sensia",           "corretor": "Nath"},
    {"id": "1r4njxyOa17slTPMU0GDSkoxftTuduDRmPK8XvgsTXKc", "emp": "Edf. Guaxuma",          "corretor": "Fernanda"},
    {"id": "1cMELjUGTsSmVNVYlHQmpeNqk4ic_eo9J7M23BWVGnJI", "emp": "JTR Jatiúca",           "corretor": "Nathalia"},
    {"id": "1lHgTHSYo1Bo5xd3AOWNXB_PtcrpfcEBgZMs9GbgOx5Y", "emp": "Jatiúca",               "corretor": "Adriana"},
    {"id": "13-KSacklkV1cgeRGPeG55YROAuToTM7he3Xbw20N9ac", "emp": "Blend Grand Reserva",   "corretor": "Marcos Jr"},
    {"id": "1zroEFtWi4HEHiKRR6zDDpiSlVg_zhSsUHIrr7W0ECRs", "emp": "Blend Grand Reserva",   "corretor": "Stefan"},
    {"id": "1cMRG523pO2PT-yPv5oZ3k6IGxKVMsLN66nCfQ9gMun0", "emp": "Blend Grand Reserva",   "corretor": "Tati"},
    {"id": "1cMRG523pO2PT-yPv5oZ3k6IGxKVMsLN66nCfQ9gMun0", "emp": "Edf. Ametista",         "corretor": "Tati"},
]

META_AD_ACCOUNT = "act_916115436468748"

# Período "total" do relatório (dinâmico: do dia 1 do mês passado até hoje)
_today = datetime.now() - timedelta(hours=3)  # BRT
_start_default = (_today.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d")
PERIOD_START = os.environ.get("PERIOD_START") or _start_default
PERIOD_END = os.environ.get("PERIOD_END") or _today.strftime("%Y-%m-%d")

# Datas de ativação puxadas dos ads do Meta (cada criativo roda 30 dias).
# empreendimentos.json funciona como override manual se preciso.
EMP_DATE_OVERRIDES = {}
_OVERRIDE_PATH = os.path.join(os.path.dirname(__file__), "empreendimentos.json")
if os.path.exists(_OVERRIDE_PATH):
    try:
        EMP_DATE_OVERRIDES = {k: v for k, v in json.load(open(_OVERRIDE_PATH, encoding="utf-8")).items()
                              if not k.startswith("_")}
    except Exception as e:
        print(f"  [override] erro: {e}", file=sys.stderr)

# Cache dos ads (preenchido em fetch_ads_for_campaign)
_ADS_CACHE = None


def fetch_ads_for_campaign(campaign_id):
    """Retorna todos os ads de uma campanha com status e data de criação."""
    global _ADS_CACHE
    if _ADS_CACHE is not None:
        return _ADS_CACHE
    token = os.environ.get("META_ACCESS_TOKEN")
    if not token or not campaign_id:
        return []
    url = f"https://graph.facebook.com/v21.0/{campaign_id}/ads?" + urllib.parse.urlencode({
        "fields": "id,name,effective_status,created_time",
        "limit": 200,
        "access_token": token,
    })
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        _ADS_CACHE = data.get("data", [])
    except Exception as e:
        print(f"  [ads] erro: {e}", file=sys.stderr)
        _ADS_CACHE = []
    return _ADS_CACHE


def fetch_ad_spend(account_id, start_str, end_str):
    """Retorna {ad_name: spend} no período (level=ad). Usa name pq facilita o matching."""
    token = os.environ.get("META_ACCESS_TOKEN")
    if not token:
        return {}
    url = f"https://graph.facebook.com/v21.0/{account_id}/insights?" + urllib.parse.urlencode({
        "fields": "ad_id,ad_name,spend",
        "time_range": json.dumps({"since": start_str, "until": end_str}),
        "level": "ad",
        "limit": 500,
        "access_token": token,
    })
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  [ad spend] erro: {e}", file=sys.stderr)
        return {}
    out = defaultdict(float)
    for row in data.get("data", []):
        name = row.get("ad_name") or row.get("ad_id")
        out[name] += float(row.get("spend", 0))
    return dict(out)


def _norm(s):
    s = (s or "").lower()
    for a, b in [("á","a"),("â","a"),("ã","a"),("é","e"),("ê","e"),("í","i"),
                 ("ó","o"),("ô","o"),("õ","o"),("ú","u"),("ç","c")]:
        s = s.replace(a, b)
    return s


def find_emp_ad(emp, corretor):
    """Procura o ad que corresponde a um empreendimento + corretor.
    Retorna o ad ATIVO mais antigo (a campanha começou quando subiu o primeiro ad ativo).
    Se não houver ATIVO, retorna o PAUSED mais recente.
    """
    ads = _ADS_CACHE or []
    emp_k = _norm(emp).replace("edf. ", "").replace("edf ", "").strip()
    cor_k = _norm(corretor).strip()
    matches = []
    for ad in ads:
        name = _norm(ad.get("name", ""))
        if emp_k not in name:
            continue
        # match perfeito de corretor; ou nome do corretor está na lista (ex "Nath/Guilherme/Fernanda")
        cor_in_name = cor_k in name
        matches.append((ad, cor_in_name))
    # prioriza match exato de corretor; se não houver, qualquer ad do empreendimento
    exact = [a for a, m in matches if m]
    pool = exact if exact else [a for a, _ in matches]
    if not pool:
        return None
    actives = [a for a in pool if a.get("effective_status") == "ACTIVE"]
    if actives:
        return min(actives, key=lambda a: a["created_time"])
    return max(pool, key=lambda a: a["created_time"])


def emp_timing(emp, corretor, today=None):
    """Calcula o timing do empreendimento. Prioridade: override manual > ad Meta + 30 dias."""
    today = today or datetime.now().date()
    out = {"start": None, "end": None, "days_active": None, "days_left": None,
           "start_label": None, "end_label": None, "ad_status": None, "ad_name": None}

    # 1) override manual (se preenchido no JSON)
    key = f"{emp}|{corretor}"
    ov = EMP_DATE_OVERRIDES.get(key, {})
    start_str = (ov.get("start") or "").strip() or None
    end_str = (ov.get("end") or "").strip() or None

    # 2) tenta puxar do ad do Meta
    if not start_str:
        ad = find_emp_ad(emp, corretor)
        if ad:
            ct = ad.get("created_time", "")[:10]
            try:
                sd = datetime.strptime(ct, "%Y-%m-%d").date()
                start_str = sd.strftime("%Y-%m-%d")
                end_str = end_str or (sd + timedelta(days=30)).strftime("%Y-%m-%d")
                out["ad_status"] = ad.get("effective_status")
                out["ad_name"] = ad.get("name")
            except Exception:
                pass

    out["start"] = start_str
    out["end"] = end_str
    if start_str:
        try:
            sd = datetime.strptime(start_str, "%Y-%m-%d").date()
            out["days_active"] = (today - sd).days
            out["start_label"] = sd.strftime("%d/%m/%y")
        except ValueError:
            pass
    if end_str:
        try:
            ed = datetime.strptime(end_str, "%Y-%m-%d").date()
            out["days_left"] = (ed - today).days
            out["end_label"] = ed.strftime("%d/%m/%y")
        except ValueError:
            pass
    return out


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
def emp_spend_in_period(emp, corretor, ad_spend_by_name):
    """Retorna (spend_total, is_shared). spend é o gasto bruto dos ads do empreendimento;
    is_shared=True quando o ad é compartilhado entre múltiplos corretores."""
    if not ad_spend_by_name:
        return 0.0, False
    emp_k = _norm(emp).replace("edf. ", "").replace("edf ", "").strip()
    cor_k = _norm(corretor).strip()
    total_exact = 0.0
    has_exact = False
    for name, spend in ad_spend_by_name.items():
        n = _norm(name)
        if emp_k in n and cor_k in n:
            total_exact += spend
            has_exact = True
    if has_exact:
        return total_exact, False
    # fallback: ad compartilhado (ex Sensia)
    total = 0.0
    for name, spend in ad_spend_by_name.items():
        n = _norm(name)
        if emp_k in n:
            total += spend
    return total, total > 0


def process_view(rows_by_sheet, start_str, end_str, ad_spend_by_name=None):
    ini = datetime.strptime(start_str, "%Y-%m-%d")
    fim = datetime.strptime(end_str, "%Y-%m-%d") + timedelta(hours=23, minutes=59, seconds=59)

    per_emp = []
    totals = Counter()
    motivos = Counter()
    motivos_by_emp = defaultdict(Counter)   # {empreendimento: Counter(motivo: count)}
    perdas_by_emp = []                      # [{emp, corretor, perdas, motivos: {...}}]
    daily = defaultdict(lambda: Counter())

    for sheet, rows in zip(SHEETS, rows_by_sheet):
        emp_data = Counter()
        emp_motivos = Counter()
        emp_key = f"{sheet['emp']} ({sheet['corretor']})"
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
                m = cat_motivo(obs)
                motivos[m] += 1
                emp_motivos[m] += 1
                motivos_by_emp[emp_key][m] += 1

        perdas_total = emp_data["desqualificado"] + emp_data["perdido"]
        if perdas_total > 0:
            perdas_by_emp.append({
                "emp": sheet["emp"],
                "corretor": sheet["corretor"],
                "perdas": perdas_total,
                "motivos": dict(emp_motivos),
            })

        timing = emp_timing(sheet["emp"], sheet["corretor"])
        spend, shared = emp_spend_in_period(sheet["emp"], sheet["corretor"], ad_spend_by_name)
        timing["spend"] = round(spend, 2)
        timing["spend_shared"] = shared
        per_emp.append({
            "emp": sheet["emp"],
            "corretor": sheet["corretor"],
            "leads": sum(emp_data.values()),
            "atend": emp_data["em_atendimento"],
            "visita": emp_data["visita"],
            "qual": emp_data["qualificado"],
            "proposta": emp_data["proposta"],
            "perda": perdas_total,
            "outros": emp_data["outros_produtos"] + emp_data["nao_momento"],
            "sem": emp_data["sem_status"],
            "timing": timing,
        })

    perdas_by_emp.sort(key=lambda x: -x["perdas"])

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
        "perdas_by_emp": perdas_by_emp,
        "series": series,
    }


# ─── META API ────────────────────────────────────────────────────────────
def fetch_campaign_status():
    """Retorna status agregado das campanhas da conta. Pega a campanha ATIVA
    (effective_status=ACTIVE) se houver; senão retorna a mais recentemente pausada."""
    token = os.environ.get("META_ACCESS_TOKEN")
    if not token:
        return None
    url = f"https://graph.facebook.com/v21.0/{META_AD_ACCOUNT}/campaigns?" + urllib.parse.urlencode({
        "fields": "name,effective_status,objective,start_time,stop_time",
        "limit": 100,
        "access_token": token,
    })
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  [Meta campanhas] erro: {e}", file=sys.stderr)
        return None
    campaigns = data.get("data", [])
    active = [c for c in campaigns if c.get("effective_status") == "ACTIVE"]
    if active:
        c = active[0]
        return {"name": c.get("name"), "status": "ACTIVE", "label": "Ativa",
                "start_time": c.get("start_time"), "objective": c.get("objective")}
    # senão, primeira pausada (pra dar contexto)
    paused = [c for c in campaigns if c.get("effective_status") == "PAUSED"]
    if paused:
        c = paused[0]
        return {"name": c.get("name"), "status": "PAUSED", "label": "Pausada",
                "start_time": c.get("start_time"), "objective": c.get("objective")}
    return {"name": None, "status": "NONE", "label": "Sem campanha ativa"}


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
        "campaign": fetch_campaign_status(),
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
    # spend por ad no período
    ad_spend = fetch_ad_spend(META_AD_ACCOUNT, start_str, end_str)
    stats = process_view(rows_by_sheet, start_str, end_str, ad_spend_by_name=ad_spend)
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

    # Pré-carrega ads da campanha ativa, pra mapear data de ativação por empreendimento.
    print("\nPuxando campanha + ads do Meta...", file=sys.stderr)
    camp = fetch_campaign_status()
    if camp and camp.get("status") in ("ACTIVE", "PAUSED"):
        # busca o ID da campanha pra puxar os ads
        token = os.environ.get("META_ACCESS_TOKEN")
        if token:
            url = f"https://graph.facebook.com/v21.0/{META_AD_ACCOUNT}/campaigns?" + urllib.parse.urlencode({
                "fields": "id,name,effective_status",
                "limit": 100,
                "access_token": token,
            })
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    cdata = json.loads(resp.read())
                active = next((c for c in cdata.get("data", []) if c.get("effective_status") == "ACTIVE"), None)
                if active:
                    ads = fetch_ads_for_campaign(active["id"])
                    print(f"  {len(ads)} ads encontrados na campanha ativa", file=sys.stderr)
            except Exception as e:
                print(f"  [ads main] erro: {e}", file=sys.stderr)

    # Define os 3 períodos. "total" usa as env vars; abril é fixo;
    # maio expande conforme PERIOD_END (até a data mais recente do total).
    maio_end = PERIOD_END if PERIOD_END >= "2026-05-01" else "2026-05-31"
    views = {
        "total": build_view(rows_by_sheet, PERIOD_START, PERIOD_END, "Período total"),
        "abril": build_view(rows_by_sheet, "2026-04-01", "2026-04-30", "Abril"),
        "maio":  build_view(rows_by_sheet, "2026-05-01", maio_end, "Maio"),
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
