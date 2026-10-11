# Auditor de Sites Institucionais

Encontra empresas por **categoria + cidade/UF**, audita o site de cada uma em 8 dimensões, gera um **relatório de falhas** para o cliente (link + PDF) e transforma o mesmo diagnóstico no **briefing do site novo**.

Implementação do documento *“Auditor de Sites Institucionais — PRD, TRD, App Flow, Design, Backend e Plano”* (24/09/2026).

## Arquitetura

Monólito modular em Django com workers assíncronos (TRD 2.1):

```
backend/                Django 5 + DRF + Celery
  apps/accounts         usuários (Administrador/Analista), 2FA TOTP, bloqueio após 5 tentativas
  apps/geo              municípios do IBGE (autocomplete e validação de cidade/UF)
  apps/catalog          categorias, pesos por dimensão, checklist, catálogo de regras
  apps/leads            buscas, empresas, sites, funil (CRM leve), descoberta e deduplicação
    discovery/          Google Places, base CNPJ da Receita, busca web, deduplicação
  apps/audits           auditorias, etapas, achados, artefatos
    engine/             motor: rastreio → capturas → Lighthouse → axe → segurança →
                        tecnologia → regras → IA → pontuação
  apps/reports          relatório público /r/{token}, PDF, comparativo, briefing
  apps/core             trilha de auditoria, custos de API, prompts versionados, marca
  templates/reports     relatório do cliente (HTML sem JS, mesmo template do PDF)
frontend/               React + TypeScript + Vite + Tailwind (painel interno)
docker-compose.yml      PostgreSQL 16, Redis, web, workers por fila, beat, Flower, backup
```

## Rodando em desenvolvimento (sem Docker)

Sem `DATABASE_URL`/`CELERY_BROKER_URL`, o sistema usa **SQLite** e roda os jobs em **threads** do próprio servidor — suficiente para testar.

```bash
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements-dev.txt     # Linux/macOS: .venv/bin/pip
.venv/Scripts/python -m playwright install chromium            # capturas, métricas e PDF
cd backend
npm install                                                    # axe-core e Lighthouse
../.venv/Scripts/python manage.py migrate
../.venv/Scripts/python manage.py load_ibge                    # 5.570 municípios
../.venv/Scripts/python manage.py seed_categories              # 8 categorias + regras
../.venv/Scripts/python manage.py create_operator voce@empresa.com.br --role admin --nome "Seu Nome" --password "senha-forte-aqui"
../.venv/Scripts/python manage.py runserver 8000
```

Em outro terminal:

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxy para o Django na porta 8000)
```

Em desenvolvimento o 2FA fica desligado (`REQUIRE_2FA` segue `not DEBUG`). Com `DJANGO_DEBUG=false` ele é sempre exigido: no primeiro login o sistema mostra o QR code para o aplicativo autenticador.

## Produção (Docker Compose)

```bash
cp .env.example .env        # preencha segredos e chaves
docker compose up -d --build
docker compose exec web python manage.py load_ibge
docker compose exec web python manage.py seed_categories
docker compose exec web python manage.py create_operator voce@empresa.com.br --role admin --password '...'
```

- `web` serve a API, o painel compilado (`frontend/dist`) e o relatório público.
- `worker-audit` roda 5 auditorias em paralelo; `worker-discovery` as buscas; `worker-misc` IA, PDFs e manutenção.
- `beat` agenda: rechecagem mensal de sites, expiração diária de links, limpeza semanal de capturas com mais de 12 meses.
- `backup` faz `pg_dump` diário em `./backups` com retenção de 30 dias. Restauração: `pg_restore -h db -U auditor -d auditor --clean backups/auditor-AAAA-MM-DD.dump`.
- Coloque um proxy HTTPS (Caddy, Nginx ou o load balancer da AWS) na frente da porta 8000.

## Descoberta de empresas sem custo

A busca funciona sem nenhuma API paga, combinando três fontes gratuitas:

1. **Base aberta de CNPJ (Receita)**: todas as empresas ativas do CNAE na cidade, inclusive as que não aparecem no Google. É a fonte principal; importe com `import_cnpj` (abaixo).
2. **Site pelo e-mail do CNPJ**: se o e-mail cadastral for corporativo (ex.: `contato@clinicasorriso.com.br`), o sistema testa `clinicasorriso.com.br` em segundo plano. O site só é aceito se responder, não for domínio estacionado e mostrar o nome da empresa (evita pegar o site do escritório de contabilidade dela). Só o domínio é guardado, nunca o e-mail.
3. **OpenStreetMap** (API Overpass): filtrado pelo código IBGE do município e pelas tags da categoria (ex.: `amenity=dentist`). A cobertura varia muito por cidade; em Vitória da Conquista/BA, por exemplo, trouxe poucas clínicas e sem site. Serve como complemento.

O Google Places continua disponível como fonte opcional (maior cobertura, com nota e avaliações), bastando configurar a chave.

## Gerador de site novo

Na ficha do lead, **Site novo** monta um site completo a partir do diagnóstico (regras confirmadas) e do checklist da categoria:

- Página única com serviços, sobre, avaliações do Google (nota real, quando existe), dúvidas frequentes e contato, mais a política de privacidade (LGPD).
- Já resolve as falhas típicas: celular primeiro, sem dependências externas (carrega rápido), WCAG 2.1 AA, título e descrição para o Google, dados estruturados `LocalBusiness`, WhatsApp/telefone clicáveis, “Como chegar”, formulário com consentimento, sitemap e robots.txt.
- Textos escritos pela IA configurada (Gemini, Claude ou local), com a regra de não inventar fatos: nada de registros profissionais, anos de experiência, preços ou depoimentos. O que depende do cliente aparece em “Confirmar com o cliente”. Sem IA, usa textos-base neutros.
- O analista edita textos, dados e cores, vê a prévia em computador e celular e baixa o site em `.zip`, pronto para qualquer hospedagem.
- **Antes × depois:** “Auditar site novo” passa o site gerado pelo mesmo motor de auditoria. HTTPS e cabeçalhos ficam de fora da prévia, porque dependem da hospedagem.

As prévias ficam em `SITES_BASE_URL/s/<token>/`. Use um host separado do painel (local: `http://127.0.0.1:8000`; produção: por exemplo `https://previa.seudominio.com.br`); nesse host o robots.txt libera apenas `/s/`.

## Integrações

Todas são opcionais; sem a chave, a etapa aparece como **“não medida”** no relatório e a nota redistribui os pesos entre o que foi medido.

| Integração | Variável | Uso |
|---|---|---|
| OpenStreetMap (gratuito) | `OSM_ENABLED`, `OVERPASS_URLS` | Fonte complementar da busca |
| Site pelo e-mail do CNPJ (gratuito) | `EMAIL_DOMAIN_DISCOVERY` | Descobre o site das empresas da base CNPJ |
| Google Places API (New), pago | `GOOGLE_PLACES_API_KEY` | Fonte opcional, com nota e avaliações do Google |
| Programmable Search | `GOOGLE_CSE_ID`, `GOOGLE_CSE_API_KEY` | Acha o site de empresas que o Places não trouxe |
| Base CNPJ (Receita) | `manage.py import_cnpj` | Empresas fora do Google e sem site |
| Gemini (plano gratuito do Google AI Studio) | `GEMINI_API_KEY`, `AI_MODEL` | Análise qualitativa das capturas, sem custo (padrão `gemini-flash-latest`, o Flash mais recente) |
| Claude API (pago) | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Alternativa para a análise qualitativa (padrão `claude-opus-5`) |
| IA local (Ollama) ou OpenRouter/Groq | `AI_PROVIDER=openai_compat`, `AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY` | Qualquer API compatível com o formato da OpenAI |
| Lighthouse / axe-core | `npm install` em `backend/` | Desempenho, SEO, boas práticas, WCAG 2.1 AA |
| S3 / MinIO | `AWS_STORAGE_BUCKET_NAME` etc. | Capturas, JSON do Lighthouse e PDFs |
| Sentry | `SENTRY_DSN` | Erros |

Base CNPJ (arquivos em arquivos.receitafederal.gov.br, Dados Abertos CNPJ). Baixe o `Municipios.zip`, os `Estabelecimentos0.zip` a `Estabelecimentos9.zip` e, se quiser a razão social, os `Empresas*.zip` do mês mais recente. São vários GB; o comando lê os zips sem descompactar e guarda só as empresas ativas dos CNAEs das categorias:

```bash
python manage.py import_cnpj --municipios Municipios.zip --estabelecimentos Estabelecimentos*.zip --empresas Empresas*.zip --uf BA
```

A IA usa *structured outputs* (JSON validado por schema, uma nova tentativa se vier inválido) e *fallback* do servidor em caso de recusa. Ela nunca fornece números: os achados de IA nascem “pendentes de revisão” e só entram no relatório depois de confirmados. Os prompts são versionados em Configurações → Prompts de IA.

## Testes

```bash
cd backend
../.venv/Scripts/python -m pytest --cov=apps       # 82 testes
cd ../frontend && npm run build                     # type-check + build
```

Os testes cobrem pontuação, deduplicação, as regras automáticas, a API (2FA, funil, revisão, relatório público, briefing) e o motor rodando contra um site HTTP local.

## Como o documento foi atendido

| Item do PDF | Situação |
|---|---|
| RF01–RF03 busca, IBGE, deduplicação | Pronto (domínio → telefone → trigram ≥ 0,8 no mesmo município; cache de 30 dias) |
| RF04 auditoria individual ou em lote (até 50) | Pronto |
| RF05 histórico por site | Pronto (auditoria concluída é imutável; “Reauditar” cria outra) |
| RF06 nota 0–100 com pesos por categoria | Pronto (`engine/scoring.py`, fórmula do TRD 2.4) |
| RF07 confirmar/editar/descartar achados | Pronto (tela de revisão com atalhos C/E/D/J/K) |
| RF08 relatório com link expirável + PDF com a marca | Pronto (token de 32 bytes, 60 dias, revogação) |
| RF09 briefing (PDF/Markdown) | Pronto em Markdown; editável na tela |
| RF10 comparativo com até 5 concorrentes | Pronto |
| RF11 rastreio de abertura | Pronto (IP guardado só como hash) |
| RF12 categorias, pesos e checklist | Pronto |
| RF13 exportar CSV | Pronto |
| RF14 painel de custos de API | Pronto (teto mensal com alerta a 80%) |
| 8 dimensões e ~40 regras | Pronto (`engine/rules.py`) |
| Relatório público com Lighthouse ≥ 95 | Desempenho 100, Acessibilidade 100, Boas práticas 100. SEO 66, só porque o relatório é `noindex` de propósito (é privado do prospect) |
| Política de privacidade e página de exclusão | `/privacidade` e `/exclusao-de-dados`; exclusão completa pelo botão na ficha do lead |

### Pendências que dependem de vocês

- **Questões em aberto do PRD 1.8**: categorias iniciais (há 8 cadastradas, ajustáveis), marca do relatório (Configurações → Marca) e orçamento mensal de APIs (`MONTHLY_API_BUDGET_BRL`, padrão R$ 500).
- Chaves do Google Places e da Claude API.
- Parecer jurídico sobre LGPD e termos de uso antes do lançamento (plano 6.3).
- Testar a restauração do backup no servidor de produção.
- Wappalyzer foi substituído por assinaturas locais (`engine/tech.py`), porque a biblioteca Python original não é mais mantida.
