# NI Negócios — Relatório Comercial

Dashboard automatizado da conta **NI Negócios**, integrando:
- 9 planilhas Google dos corretores (status de leads por empreendimento)
- Meta Ads API (investimento e CPL)

## Como funciona

- `build.py` baixa as 9 planilhas (CSV público), puxa Meta API e gera `data.js` com todas as métricas calculadas
- `index.html` carrega `data.js` e renderiza o dashboard (Inter + Chart.js)
- GitHub Actions roda diariamente às 8h (horário de Brasília) e publica via GitHub Pages

## Rodar local

```bash
export META_ACCESS_TOKEN="seu_token"
python3 build.py
python3 -m http.server 8000
# abrir http://localhost:8000
```

## Período personalizado

Por padrão usa `01/04/2026 a 04/05/2026`. Pra mudar:

```bash
PERIOD_START=2026-05-01 PERIOD_END=2026-05-31 python3 build.py
```

Ou via Actions: `Actions → Build NI Report → Run workflow` e preencher os inputs.

## Adicionar novo empreendimento

Editar `SHEETS` em `build.py` com:

```python
{"id": "<google_sheet_id>", "emp": "Nome do Empreendimento", "corretor": "Nome"}
```

## Secrets necessários

- `META_ACCESS_TOKEN` — token de acesso ao Meta Ads (Graph API v21+)
