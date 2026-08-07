"""Comparativo de benchmark: os CRMs que disputam o mercado brasileiro.

Fonte única do comparativo exibido no catálogo de Serviços, no Manual e na
tela «Comparativo de Mercado». Os preços foram consultados nas páginas
oficiais na data em PRICE_CHECKED_AT — preço de software muda, então o dado
é datado e a fonte fica registrada. Onde o valor não é público, o campo diz
«sob consulta»; onde a informação não pôde ser confirmada, diz «não
confirmado». Nunca preencher com estimativa: isto é conteúdo dentro do
produto, e número inventado destrói a credibilidade do comparativo inteiro.

A regra editorial do campo `trust_diff` é a mesma: onde o concorrente é
melhor que o Trust CRM, o texto diz isso. Comparativo que só elogia a casa
não serve para decidir nada.
"""

from __future__ import annotations

from typing import Any

PRICE_CHECKED_AT = "07/08/2026"

# Cada bloco: origem, público, preço de entrada (com plano e moeda), pontos
# fortes, limitações conhecidas, o que oferece de Brasil e o nosso diferencial.
COMPETITORS: list[dict[str, Any]] = [
    {
        "name": "RD Station CRM",
        "brazilian": True,
        "origin": "Brasil (TOTVS)",
        "audience": "PMEs brasileiras com marketing e vendas juntos",
        "price": "R$ 73/usuário/mês (Basic mensal) · R$ 65,70 no anual · Free até 4 usuários",
        "price_source": "rdstation.com",
        "strengths": [
            "Marketing e CRM no mesmo ecossistema",
            "IA que transcreve áudio de WhatsApp direto no CRM",
            "60 mil+ empresas brasileiras e rede de parceiros local",
        ],
        "limitations": [
            "Plano gratuito bem limitado (4 usuários, sem automações)",
            "Recursos avançados exigem contratar outros produtos da suíte",
        ],
        "brasil": "WhatsApp nativo com IA · LGPD (empresa brasileira)",
        "trust_diff": (
            "Eles ganham em marketing integrado e maturidade de mercado. "
            "Ganhamos em validação de CPF/CNPJ com dígito verificador e consulta "
            "automática na Receita — que no RD não é nativo — e em custo por usuário."
        ),
    },
    {
        "name": "Agendor",
        "brazilian": True,
        "origin": "Brasil (São Paulo)",
        "audience": "PMEs brasileiras, vendas B2B e B2C",
        "price": "R$ 59/usuário/mês (Pro) · R$ 83 (Performance) · Free até 3 usuários",
        "price_source": "agendor.com.br/planos-precos",
        "strengths": [
            "Melhor custo-benefício de entrada entre os brasileiros",
            "Interface simples, adoção rápida sem equipe técnica",
            "Plano gratuito funcional para times pequenos",
        ],
        "limitations": [
            "Automação só a partir do plano Performance",
            "Sem módulo nativo de propostas/documentos",
            "Ecossistema de integrações menor que o dos globais",
        ],
        "brasil": "WhatsApp via integração (não nativo) · LGPD (empresa brasileira)",
        "trust_diff": (
            "Concorrente mais próximo em simplicidade. Ganhamos em automações "
            "já no uso básico (sem plano superior), análise de perdas com motivo "
            "obrigatório e código-fonte próprio — nenhuma mensalidade por usuário."
        ),
    },
    {
        "name": "Ploomes",
        "brazilian": True,
        "origin": "Brasil (São Paulo)",
        "audience": "B2B médio e grande: indústria, distribuidoras, SaaS",
        "price": "R$ 85/usuário/mês (Básico) · módulos CPQ/Workflow sob consulta · mínimo 3 usuários",
        "price_source": "ploomes.com/precos",
        "strengths": [
            "Geração de propostas, pedidos e contratos automatizada (CPQ)",
            "Integração nativa com ERPs brasileiros (TOTVS, SAP, Omie, Sankhya)",
            "API aberta e suporte especializado bem avaliado",
        ],
        "limitations": [
            "Sem plano gratuito e com implantação paga obrigatória",
            "Preço dos módulos avançados só sob consulta",
            "Robusto demais para PME simples",
        ],
        "brasil": "WhatsApp via extensão · integra NF/pedidos por ERP · PIX · LGPD",
        "trust_diff": (
            "Eles ganham claramente em proposta/CPQ e integração com ERP — não temos. "
            "Ganhamos em custo, em tempo de implantação (já está no ar) e em "
            "liberdade para criar qualquer regra específica da Trust."
        ),
    },
    {
        "name": "Moskit CRM",
        "brazilian": True,
        "origin": "Brasil (Londrina)",
        "audience": "PMEs B2B, serviços e indústria",
        "price": "R$ 89/usuário/mês (entrada mensal) · R$ 75,65 no anual",
        "price_source": "moskitcrm.com/planos",
        "strengths": [
            "Sincronização com WhatsApp Web e histórico de conversas",
            "IA para preencher campos e transcrever reuniões",
            "Produto pensado para o jeito brasileiro de vender",
        ],
        "limitations": [
            "Empresa passou por forte reestruturação em 2026 — atenção à continuidade",
            "Sem emissão de propostas nativa",
            "Base de usuários menor que a dos líderes",
        ],
        "brasil": "WhatsApp nativo (Web) · LGPD (empresa brasileira)",
        "trust_diff": (
            "Ganhamos em previsibilidade: nosso código é da Trust, não depende da "
            "saúde financeira de fornecedor. Empatamos em WhatsApp para o uso "
            "prático (nosso é por link, sem custo de API)."
        ),
    },
    {
        "name": "Nectar CRM",
        "brazilian": True,
        "origin": "Brasil (Goiânia)",
        "audience": "B2B consultivo de ciclo longo (mínimo 4 usuários)",
        "price": "A partir de R$ 396/mês (pacote de 4 usuários) — preço por usuário não publicado com clareza",
        "price_source": "lp.nectarcrm.com.br",
        "strengths": [
            "Foco em pipeline consultivo complexo",
            "BI e relatórios avançados por vendedor",
            "Integra VoIP, WhatsApp e agenda com histórico central",
        ],
        "limitations": [
            "Exige mínimo de 4 usuários",
            "Sem plano gratuito ou teste self-service claro",
        ],
        "brasil": "WhatsApp · consulta de CNPJ na Receita · LGPD",
        "trust_diff": (
            "É o concorrente que mais se parece conosco em consulta de CNPJ. "
            "Ganhamos por não ter piso de usuários e por entregar funil, atendimento "
            "e marketing no mesmo preço (zero por usuário)."
        ),
    },
    {
        "name": "Meets CRM",
        "brazilian": True,
        "origin": "Brasil (Recife)",
        "audience": "PMEs em clínicas, educação e imobiliário",
        "price": "Não publicado na página oficial · Free para 1 usuário",
        "price_source": "meets.com.br/planos",
        "strengths": [
            "Omnichannel nativo (WhatsApp, Instagram, Messenger, site, e-mail)",
            "Chatbot com IA 24h nos planos superiores",
            "Desenhado para verticais brasileiras",
        ],
        "limitations": [
            "Preço não publicado dificulta comparação",
            "WhatsApp omnichannel só do plano Profissional em diante",
        ],
        "brasil": "WhatsApp nativo (API oficial ou QR) · campo CNPJ · LGPD",
        "trust_diff": (
            "Eles ganham em caixa de entrada omnichannel e chatbot — nosso intake "
            "é operacional (colar a mensagem). Ganhamos em funil comercial, "
            "previsão ponderada e análise de perdas."
        ),
    },
    {
        "name": "Kommo (ex-amoCRM)",
        "brazilian": False,
        "origin": "Rússia (forte operação no Brasil)",
        "audience": "Quem vende por mensagem (WhatsApp, Instagram, Telegram)",
        "price": "US$ 15/usuário/mês (Básico) — sobe para US$ 25 em set/2026 · mínimo 6 meses",
        "price_source": "kommo.com/br/precos",
        "strengths": [
            "CRM construído em torno de mensageiros",
            "Pipeline visual com automação de mensagens",
            "Rede de parceiros no Brasil com suporte em português",
        ],
        "limitations": [
            "Preço em dólar (exposição cambial) e aumento confirmado para set/2026",
            "Relatórios mais fracos que os dos líderes",
            "Dados fora do Brasil — LGPD não confirmada",
        ],
        "brasil": "WhatsApp nativo (centro do produto) · PIX via parceiros",
        "trust_diff": (
            "Eles ganham em conversas centralizadas. Ganhamos em soberania do dado "
            "(banco no Brasil, sob a Trust), preço em real e trilha de auditoria completa."
        ),
    },
    {
        "name": "Pipedrive",
        "brazilian": False,
        "origin": "Estônia (uso amplo no Brasil)",
        "audience": "Times de vendas de PME e midmarket",
        "price": "US$ 14/usuário/mês (Lite anual) · US$ 39 (Growth) · US$ 59 (Premium)",
        "price_source": "pipedrive.com/pt/pricing",
        "strengths": [
            "Pipeline visual que virou padrão do mercado",
            "Automação de sequências de e-mail (Growth+)",
            "Marketplace com 500+ integrações",
        ],
        "limitations": [
            "Preço em dólar",
            "WhatsApp não é nativo (depende do marketplace)",
            "Plano Lite limita 2.500 leads+negócios por usuário",
        ],
        "brasil": "Sem WhatsApp nativo · sem CNPJ · dados fora do Brasil",
        "trust_diff": (
            "É a nossa referência de funil — copiamos a linguagem visual e os padrões "
            "(kanban, apodrecimento, ganho/perdido com motivo). Eles ganham em e-mail "
            "e integrações; ganhamos em CPF/CNPJ, WhatsApp sem custo de API e preço."
        ),
    },
    {
        "name": "HubSpot CRM",
        "brazilian": False,
        "origin": "Estados Unidos",
        "audience": "De startup a enterprise, marketing + vendas",
        "price": "Free até 2 usuários · US$ 7/usuário/mês (Starter anual)",
        "price_source": "hubspot.com/pricing/crm",
        "strengths": [
            "Marketing, vendas e atendimento na mesma plataforma",
            "Plano gratuito generoso e sem prazo",
            "Integração nativa com Gmail, Outlook e LinkedIn",
        ],
        "limitations": [
            "Preço escala rápido nos planos Professional e Enterprise",
            "WhatsApp não é nativo",
            "Curva de aprendizado do ecossistema completo",
        ],
        "brasil": "Sem WhatsApp nativo · sem CNPJ · dados fora do Brasil",
        "trust_diff": (
            "Tomamos deles o «Meu Dia» (Sales Workspace) e o baixo atrito de adoção. "
            "Eles ganham em e-mail e ecossistema; ganhamos em adequação ao Brasil "
            "e em não escalar custo por contato."
        ),
    },
    {
        "name": "Zoho CRM",
        "brazilian": False,
        "origin": "Índia",
        "audience": "PME a enterprise, amplo espectro",
        "price": "Free até 3 usuários · US$ 14/usuário/mês (Standard anual) · US$ 23 (Professional)",
        "price_source": "zoho.com (tabela oficial USD)",
        "strengths": [
            "Melhor custo-benefício entre os globais",
            "Zoho One com 40+ aplicativos integrados",
            "IA Zia com previsão e detecção de anomalias",
        ],
        "limitations": [
            "Interface complexa, curva de aprendizado alta",
            "Suporte no Brasil por parceiros (qualidade variável)",
            "Localização brasileira limitada",
        ],
        "brasil": "Sem WhatsApp nativo · sem CNPJ · dados fora do Brasil",
        "trust_diff": (
            "Eles ganham em amplitude de aplicativos. Ganhamos em foco: nossas telas "
            "resolvem o processo da Trust, sem configurar uma plataforma genérica."
        ),
    },
    {
        "name": "Bitrix24",
        "brazilian": False,
        "origin": "Rússia",
        "audience": "Times que querem CRM + colaboração + projetos juntos",
        "price": "Free com usuários ilimitados · R$ 279/mês (Basic anual, até 5 usuários) — cobrança por empresa",
        "price_source": "bitrix24.com.br/prices",
        "strengths": [
            "Cobra por empresa, não por usuário — favorece time grande",
            "Suíte ampla: CRM, projetos, contact center, site",
            "Plano gratuito com usuários ilimitados",
        ],
        "limitations": [
            "Reputação fraca no Reclame Aqui (baixa taxa de resposta)",
            "Relatos de bloqueio de dados na não renovação",
            "Curva de aprendizado alta pela amplitude",
        ],
        "brasil": "WhatsApp no Standard+ · PIX e boleto aceitos",
        "trust_diff": (
            "Modelo de preço deles é forte para time grande. Ganhamos em risco: "
            "nossos dados estão no nosso Supabase, sem dependência de renovação de "
            "contrato para continuar acessando a base."
        ),
    },
    {
        "name": "Salesforce Sales Cloud",
        "brazilian": False,
        "origin": "Estados Unidos",
        "audience": "Midmarket e enterprise com ciclos complexos",
        "price": "US$ 25/usuário/mês (Starter) · US$ 100 (Pro) · US$ 175 (Enterprise)",
        "price_source": "salesforce.com/br/sales/pricing",
        "strengths": [
            "Maior ecossistema do mundo (2.500+ integrações)",
            "Agentforce: agentes de IA autônomos para vendas",
            "Escala enterprise: territórios, aprovações, sandbox",
        ],
        "limitations": [
            "Preço elevado e implantação cara com consultoria",
            "Sem plano gratuito permanente",
            "Suporte premium é pago à parte",
        ],
        "brasil": "Sem WhatsApp nativo · sem CNPJ · dados fora do Brasil por padrão",
        "trust_diff": (
            "É o teto de mercado — eles ganham em tudo que exige escala e ecossistema. "
            "Nossa vantagem é econômica e de foco: o que a Trust usa de fato custa "
            "uma fração e já está funcionando."
        ),
    },
]

# Capacidade a capacidade. `trust` e `market` descrevem fatos verificáveis —
# inclusive as três linhas em que estamos atrás.
CAPABILITY_MATRIX: list[dict[str, str]] = [
    {
        "capability": "Validação de CPF/CNPJ (dígito verificador)",
        "trust": "✅ Nativo",
        "market": "Raro — nenhum global tem; entre os brasileiros, poucos validam o dígito",
        "verdict": "vantagem",
    },
    {
        "capability": "Consulta automática de CNPJ na Receita",
        "trust": "✅ Nativo (BrasilAPI)",
        "market": "Nectar tem; globais não têm",
        "verdict": "vantagem",
    },
    {
        "capability": "Funil kanban arrastar e soltar",
        "trust": "✅ Com portão de etapa",
        "market": "Padrão em todos",
        "verdict": "empate",
    },
    {
        "capability": "Ganho/Perdido com motivo obrigatório",
        "trust": "✅ Motivo exigido + análise de perdas",
        "market": "Comum, mas motivo costuma ser opcional",
        "verdict": "vantagem",
    },
    {
        "capability": "Automações (regras que criam tarefa)",
        "trust": "✅ 4 regras com prévia e sem duplicar",
        "market": "Todos têm; nos brasileiros costuma exigir plano superior",
        "verdict": "empate",
    },
    {
        "capability": "Importação de planilha",
        "trust": "✅ Com validação e detecção de duplicado",
        "market": "Padrão em todos",
        "verdict": "empate",
    },
    {
        "capability": "WhatsApp",
        "trust": "⚠️ Por link (wa.me), sem custo de API",
        "market": "Nativo nos brasileiros; ausente nos globais",
        "verdict": "parcial",
    },
    {
        "capability": "E-mail (envio e sincronização)",
        "trust": "❌ Não temos",
        "market": "Todos têm",
        "verdict": "atras",
    },
    {
        "capability": "Marketplace de integrações",
        "trust": "❌ Integrações sob medida",
        "market": "Pipedrive 500+, Salesforce 2.500+",
        "verdict": "atras",
    },
    {
        "capability": "Multiempresa (vender como SaaS)",
        "trust": "❌ Fundação pronta, não ativa",
        "market": "Todos são multiempresa",
        "verdict": "atras",
    },
    {
        "capability": "Trilha de auditoria por ação",
        "trust": "✅ Todo evento registrado",
        "market": "Geralmente só nos planos enterprise",
        "verdict": "vantagem",
    },
    {
        "capability": "Custo por usuário",
        "trust": "✅ Zero (infraestrutura própria)",
        "market": "R$ 59 a R$ 175+ por usuário/mês",
        "verdict": "vantagem",
    },
]

TRUST_POSITION = {
    "ganhamos": [
        "**Brasil de verdade** — CPF/CNPJ validado por dígito e CNPJ consultado na Receita, nativos.",
        "**Custo** — nenhuma mensalidade por usuário; 10 pessoas no Pipedrive Premium passariam de R$ 3 mil/mês.",
        "**Soberania do dado** — banco da Trust no Supabase; nada depende de renovação de contrato.",
        "**Sob medida** — qualquer regra específica da operação entra em horas, não em roadmap de fornecedor.",
        "**Auditoria completa** — cada mudança registrada com autor, antes e depois.",
    ],
    "atras": [
        "**E-mail** — não enviamos nem sincronizamos; todo concorrente faz. É a maior lacuna.",
        "**Ecossistema** — eles têm centenas de integrações prontas; aqui é sob medida.",
        "**Multiempresa** — não dá para vender como SaaS a terceiros hoje.",
    ],
    "empate": [
        "Funil kanban, previsão ponderada, cliente 360, importação de dados e automações básicas.",
    ],
}


def brazilian_competitors() -> list[dict[str, Any]]:
    """Só os CRMs de origem brasileira (marcação explícita, não por texto)."""
    return [c for c in COMPETITORS if c.get("brazilian")]


def global_competitors() -> list[dict[str, Any]]:
    """Players globais que disputam o mercado brasileiro."""
    return [c for c in COMPETITORS if not c.get("brazilian")]


def capability_score() -> dict[str, int]:
    """Placar da matriz: em quantas capacidades estamos à frente, empatados e atrás."""
    placar = {"vantagem": 0, "empate": 0, "parcial": 0, "atras": 0}
    for linha in CAPABILITY_MATRIX:
        chave = str(linha.get("verdict", ""))
        if chave in placar:
            placar[chave] += 1
    return placar


def benchmark_markdown() -> str:
    """Comparativo em Markdown — entra no manual, no download e no PDF."""
    placar = capability_score()
    linhas = [
        "## Comparativo Benchmark — o mercado brasileiro",
        "",
        f"Preços consultados nas páginas oficiais em {PRICE_CHECKED_AT}. "
        "Valores em dólar estão marcados; software muda de preço, confira antes de decidir.",
        "",
        f"**Placar de capacidades:** {placar['vantagem']} à frente · "
        f"{placar['empate'] + placar['parcial']} equivalentes · {placar['atras']} atrás.",
        "",
        "| Concorrente | Origem | Preço de entrada | Nosso diferencial |",
        "|---|---|---|---|",
    ]
    for c in COMPETITORS:
        linhas.append(
            f"| **{c['name']}** | {c['origin']} | {c['price']} | {c['trust_diff']} |"
        )

    linhas += ["", "### Capacidade a capacidade", "",
               "| Capacidade | Trust CRM | Mercado |", "|---|---|---|"]
    for linha in CAPABILITY_MATRIX:
        linhas.append(f"| {linha['capability']} | {linha['trust']} | {linha['market']} |")

    linhas += ["", "### Onde ganhamos", ""]
    linhas += [f"- {item}" for item in TRUST_POSITION["ganhamos"]]
    linhas += ["", "### Onde estamos atrás", ""]
    linhas += [f"- {item}" for item in TRUST_POSITION["atras"]]
    return "\n".join(linhas)
