"""Service catalog organized in 5 Netflix-style categories."""
from __future__ import annotations

import unicodedata
from typing import Any

CATEGORIES = [
    {"id":"operacao","title":"Atender no dia a dia","icon":"🎯",
     "tagline":"Resolver pedidos e problemas dos clientes","color":"#e50914"},
    {"id":"relacionamento","title":"Conhecer os clientes","icon":"👥",
     "tagline":"Saber tudo de cada cliente e evitar que saiam","color":"#3b82f6"},
    {"id":"comercial","title":"Vender","icon":"💰",
     "tagline":"Acompanhar negócios e prever quanto vai entrar","color":"#22c55e"},
    {"id":"growth","title":"Atrair clientes","icon":"📣",
     "tagline":"Conseguir e organizar novos interessados","color":"#f59e0b"},
    {"id":"governanca","title":"Gerir o negócio","icon":"⚙️",
     "tagline":"Ver os números, decidir e controlar acessos","color":"#a855f7"},
]

def _s(sid, cat_id, cat_label, title, tagline, summary, desc, inputs, steps, outcome, bench, integ):
    """summary=objetivo | desc=resumo geral | inputs=dados | steps=como usar | outcome=resultado esperado."""
    return {
        "id": sid,
        "category_id": cat_id,
        "category": cat_label,
        "title": title,
        "tagline": tagline,
        "summary": summary,
        "description": desc,
        "inputs": inputs,
        "steps": steps,
        "outcome": outcome,
        "benchmark": bench,
        "integrations": integ,
        "ready_to_use": True,
        "objetivo": summary,
        "resumo_geral": desc,
        "resultado_esperado": outcome,
        "dados_input": inputs,
        "como_usar": steps,
    }


def service_guide_payload(service: dict[str, Any]) -> dict[str, Any]:
    """Campos padronizados do guia (4 blocos + metadados)."""
    return {
        "id": service["id"],
        "title": service["title"],
        "category": service["category"],
        "tagline": service.get("tagline", ""),
        "objetivo": service.get("objetivo") or service.get("tagline", ""),
        "resumo_geral": service.get("resumo_geral") or service.get("description", ""),
        "resultado_esperado": service.get("resultado_esperado") or service.get("outcome", ""),
        "dados_input": service.get("dados_input") or service.get("inputs", []),
        "como_usar": service.get("como_usar") or service.get("steps", []),
        "exemplo_pratico": get_service_example(str(service["id"])),
    }

SERVICE_CATALOG = [
    _s("ticketing-sla", "operacao", "Atender no dia a dia", "Central de Atendimento",
       "Um cliente faz um pedido, dúvida ou reclamação.",
       "Organiza tudo o que os clientes pedem numa lista única, com prazo e um responsável.",
       "Cada solicitação vira um chamado com responsável e prazo, para nada se perder e todo mundo ser respondido a tempo.",
       ["Cliente cadastrado", "Assunto", "Prioridade", "Categoria", "Owner"],
       ["Abrir Atendimento", "Novo ticket", "Atribuir owner", "Acompanhar", "Resolver e CSAT"],
       "Ninguém fica sem resposta e você enxerga toda a fila.",
       "Salesforce Service Cloud, Zendesk, Freshdesk, RD Conversas.",
       ["channel-intake", "customer-360", "templates"]),
    _s("channel-intake", "operacao", "Atender no dia a dia", "Entrada de Mensagens (WhatsApp, E-mail, Site)",
       "Chega mensagem por WhatsApp, e-mail ou formulário do site.",
       "Junta as mensagens de todos os canais num lugar só, já viram atendimento.",
       "O que chega por WhatsApp, e-mail ou formulário entra automaticamente como um chamado ligado ao cliente certo.",
       ["Mensagem recebida", "Identificacao", "Canal"],
       ["Abrir Canais", "Selecionar aba", "Colar mensagem", "Validar", "Confirmar"],
       "Nenhuma mensagem se perde — tudo cai no mesmo lugar.",
       "RD Conversas, Twilio Flex, HubSpot Inbox.",
       ["ticketing-sla", "customer-360"]),
    _s("tasks-cadences", "operacao", "Atender no dia a dia", "Follow-up Automático (Lembretes)",
       "Você não quer esquecer de dar retorno para um cliente ou lead.",
       "Cria uma sequência de lembretes (falar hoje, retornar em 3 dias…) automaticamente.",
       "Você inscreve o cliente numa sequência e o sistema avisa a hora de falar de novo. Nenhum lead esfria.",
       ["Cliente alvo", "Cadência", "Responsável"],
       ["Abrir Cadências", "Selecionar", "Inscrever", "Receber lembretes", "Marcar feito"],
       "Nenhum cliente é esquecido e nenhum retorno é perdido.",
       "Outreach, Salesloft, Reev, Apollo.",
       ["templates", "pipeline", "customer-360"]),
    _s("customer-360", "relacionamento", "Conhecer os clientes", "Ficha Completa do Cliente",
       "Você precisa saber tudo sobre um cliente antes de falar com ele.",
       "Mostra numa tela só tudo o que já aconteceu com aquele cliente.",
       "Chamados, vendas, conversas e saúde da conta reunidos numa ficha única.",
       ["Conta cadastrada", "Interacoes registradas"],
       ["Abrir Clientes 360", "Filtrar", "Selecionar", "Revisar timeline"],
       "Você entende o cliente em segundos.",
       "Salesforce Customer 360, HubSpot, Zoho, Pipedrive.",
       ["timeline", "health-score", "ticketing-sla", "pipeline"]),
    _s("timeline", "relacionamento", "Conhecer os clientes", "Linha do Tempo do Cliente",
       "Você quer ver, em ordem, tudo o que já rolou com o cliente.",
       "Lista, do mais novo ao mais antigo, cada contato e ação com o cliente.",
       "Um diário automático de cada interação, para a equipe nunca perder o que já foi conversado.",
       ["Eventos automáticos", "Eventos manuais opcionais"],
       ["Abrir Clientes 360", "Selecionar conta", "Rolar histórico"],
       "Nada se perde na memória da equipe.",
       "HubSpot, linha do tempo Salesforce.",
       ["customer-360"]),
    _s("health-score", "relacionamento", "Conhecer os clientes", "Risco de Cancelamento (Saúde da Conta)",
       "Você quer saber quais clientes estão prestes a sair.",
       "Dá uma nota de 0 a 100 para cada cliente mostrando o risco de ele cancelar.",
       "Olha sinais como uso, atendimento e tempo de casa e aponta quem precisa de atenção agora.",
       ["Calculado dos dados existentes"],
       ["Abrir Saúde da Conta", "Recalcular", "Filtrar risco", "Acionar ação"],
       "Uma lista de quem está em risco, com o que fazer em cada caso.",
       "Gainsight, ChurnZero, Totango.",
       ["customer-360", "tasks-cadences", "ai-insights"]),
    _s("templates", "relacionamento", "Conhecer os clientes", "Modelos de Mensagem Prontos",
       "Você manda sempre o mesmo tipo de mensagem (boas-vindas, cobrança, retorno).",
       "Mensagens prontas que se preenchem sozinhas com o nome do cliente e outros dados.",
       "Escolha um modelo, o sistema completa com os dados do cliente e você só envia.",
       ["Cliente alvo", "Modelo selecionado"],
       ["Abrir Modelos", "Filtrar", "Selecionar cliente", "Copiar"],
       "Responde mais rápido, sem digitar tudo de novo.",
       "Intercom Saved Replies, Zendesk Macros.",
       ["tasks-cadences", "ticketing-sla", "channel-intake"]),
    _s("pipeline", "comercial", "Vender", "Funil de Vendas",
       "Você quer acompanhar suas vendas em andamento.",
       "Mostra cada negócio em etapas, do primeiro contato ao fechamento.",
       "Organiza as oportunidades por etapa, para ver onde cada venda está e o que travou.",
       ["Cliente cadastrado", "Nome, valor, prob., etapa"],
       ["Abrir Funil Comercial", "Nova oportunidade", "Acompanhar"],
       "Você enxerga onde estão as vendas e o que destravar.",
       "Pipedrive, RD CRM, HubSpot, Ploomes.",
       ["forecast", "customer-360", "tasks-cadences"]),
    _s("forecast", "comercial", "Vender", "Previsão de Receita",
       "Você quer saber quanto provavelmente vai entrar de dinheiro.",
       "Estima a receita do período com base na chance de cada negócio fechar.",
       "Soma os negócios em aberto pesando pela probabilidade de fechar, dando uma previsão realista.",
       ["Funil com oportunidades"],
       ["Abrir Previsão", "Selecionar período", "Analisar"],
       "Uma previsão confiável de quanto você deve faturar.",
       "Salesforce, HubSpot, Clari.",
       ["pipeline", "productivity"]),
    _s("productivity", "comercial", "Vender", "Produtividade do Time",
       "Você quer ver como cada pessoa do time está performando.",
       "Mostra quanto cada um vendeu, resolveu e atendeu.",
       "Compara resultados por pessoa e por canal, para reconhecer quem vai bem e ajudar quem precisa.",
       ["Periodo de analise"],
       ["Abrir Produtividade", "Selecionar periodo", "Comparar"],
       "Base clara para acompanhar e treinar o time.",
       "Salesforce Reports, Geckoboard, Domo.",
       ["pipeline", "ticketing-sla", "forecast"]),
    _s("marketing-campaigns", "growth", "Atrair clientes", "Campanhas de Marketing",
       "Você faz divulgação (e-mail, WhatsApp, anúncios) e quer medir o retorno.",
       "Registra cada campanha e mostra quanto cada uma trouxe de resultado.",
       "Cadastre a campanha, acompanhe quantos interessados e clientes ela gerou e veja o que vale a pena.",
       ["Nome, canal, leads, qualificados"],
       ["Abrir Marketing", "Nova campanha", "Comparar"],
       "Você sabe onde investir, pelo retorno de cada campanha.",
       "RD Station, HubSpot, Marketo.",
       ["lead-scoring", "customer-360"]),
    _s("lead-scoring", "growth", "Atrair clientes", "Priorização de Leads",
       "Você tem muitos interessados e não sabe por quem começar.",
       "Dá uma nota de 0 a 100 para cada lead, mostrando quem tem mais chance de comprar.",
       "Pontua os leads por sinais de interesse e separa em faixas (A = quente, D = frio) para o time focar nos melhores.",
       ["10 regras padrão editáveis"],
       ["Abrir Qualificação", "Recalcular", "Trabalhar por faixa"],
       "O time fala primeiro com quem está pronto para comprar.",
       "RD Station, HubSpot, Pardot.",
       ["marketing-campaigns", "customer-360", "pipeline"]),
    _s("segmentation", "growth", "Atrair clientes", "Listas de Clientes (Segmentação)",
       "Você quer falar só com um grupo específico (ex.: clientes de SP inativos).",
       "Filtra a base por características e monta listas para ações dirigidas.",
       "Combine filtros (região, status, valor) e exporte a lista pronta para campanhas.",
       ["Filtros (mercado, status, responsável)"],
       ["Abrir Segmentação", "Aplicar filtros", "Exportar"],
       "A comunicação certa para o público certo.",
       "RD Station Segmentos, HubSpot Lists.",
       ["marketing-campaigns", "tasks-cadences"]),
    _s("executive-view", "governanca", "Gerir o negócio", "Painel do Negócio (Visão Executiva)",
       "Você quer um resumo geral de como o negócio está indo.",
       "Reúne os principais números (vendas, atendimento, satisfação) numa tela.",
       "Os indicadores mais importantes lado a lado, para uma leitura rápida da operação.",
       ["Operação gera os números"],
       ["Abrir Visão Executiva", "Filtrar", "Revisar"],
       "Decisões com base em dados, não em achismo.",
       "Salesforce Lightning, Tableau, Power BI.",
       ["pipeline", "ticketing-sla", "forecast", "health-score"]),
    _s("ai-insights", "governanca", "Gerir o negócio", "Sugestões Automáticas (IA)",
       "Você quer que o sistema diga o que fazer a seguir.",
       "Lê os dados e sugere ações, resume clientes e aponta o que está fora do normal.",
       "O sistema analisa tudo sozinho e entrega recomendações práticas e alertas.",
       ["Dados existentes"],
       ["Abrir Insights com IA", "Selecionar", "Ler insight"],
       "A equipe ganha tempo e foca no que importa.",
       "Salesforce Einstein, HubSpot ChatSpot, Zendesk AI.",
       ["customer-360", "ticketing-sla", "health-score"]),
    _s("rbac-admin", "governanca", "Gerir o negócio", "Usuários e Permissões",
       "Você precisa definir quem pode ver e fazer o quê no sistema.",
       "Controla usuários, perfis e o que cada um tem permissão de acessar.",
       "Defina papéis e permissões e acompanhe um registro de tudo que foi feito (auditoria).",
       ["Usuários", "Ações padrão"],
       ["Abrir Administração", "Editar matriz", "Auditar"],
       "Acessos sob controle e histórico auditável.",
       "Salesforce Profiles, Auth0, Okta.",
       []),
    _s("benchmark", "governanca", "Gerir o negócio", "Comparação com Concorrentes",
       "Você quer comparar seu CRM com os concorrentes.",
       "Mostra o que cada grande CRM faz de melhor e onde dá para evoluir.",
       "Um comparativo com líderes do mercado para guiar os próximos passos do seu CRM.",
       ["Conhecimento estruturado"],
       ["Abrir Comparativo", "Revisar", "Conferir abas"],
       "Direção clara para evoluir o produto.",
       "G2, Capterra, Forrester, Gartner.",
       []),
]

def get_services_by_category(cid):
    return [s for s in SERVICE_CATALOG if s["category_id"] == cid]

def get_service_by_id(sid):
    for s in SERVICE_CATALOG:
        if s["id"] == sid: return s
    return None

SERVICE_TO_SECTION = {
    "ticketing-sla": "Atendimento",
    "channel-intake": "Canais",
    "tasks-cadences": "Cadências",
    "customer-360": "Clientes 360",
    "timeline": "Clientes 360",
    "health-score": "Saúde da Conta",
    "templates": "Modelos de Mensagem",
    "pipeline": "Funil Comercial",
    "forecast": "Previsão de Receita",
    "productivity": "Produtividade",
    "marketing-campaigns": "Marketing",
    "lead-scoring": "Qualificação de Leads",
    "segmentation": "Segmentação",
    "executive-view": "Visão Executiva",
    "ai-insights": "Insights com IA",
    "rbac-admin": "Administração",
    "benchmark": "Comparativo de Mercado",
}

def resolve_service_section(sid):
    return SERVICE_TO_SECTION.get(sid, "Visão Executiva")


# ---------------------------------------------------------------------------
# Exemplos práticos por serviço (exibidos no Guia).
# ---------------------------------------------------------------------------
SERVICE_EXAMPLES = {
    "ticketing-sla": (
        "A cliente Maria manda: «meu pedido chegou errado». Você abre a Central, "
        "cria um ticket para a Maria com prioridade Alta e responsável João. "
        "O sistema marca o prazo e, ao resolver, registra a satisfação dela."
    ),
    "channel-intake": (
        "Chegou um WhatsApp do Pedro perguntando preço. Você abre Canais, cola a "
        "mensagem na aba WhatsApp e confirma. O sistema acha o Pedro na base "
        "(ou cadastra) e já cria o atendimento ligado a ele."
    ),
    "tasks-cadences": (
        "A lead Ana pediu «me chama semana que vem». Você a inscreve na cadência "
        "de retorno: o sistema cria lembretes para D+3 e D+7. Na data, a tarefa "
        "aparece para você e nada fica esquecido."
    ),
    "customer-360": (
        "Antes de ligar para a TechCorp, você abre a ficha dela: 2 tickets "
        "abertos, última compra há 3 meses, saúde da conta em 68. Em 30 segundos "
        "você sabe exatamente o que falar."
    ),
    "timeline": (
        "O colega de férias atendia a LojaX. Você abre a linha do tempo dela e "
        "vê: proposta enviada dia 10, reclamação resolvida dia 15, follow-up "
        "prometido para hoje. Você assume sem perder o fio."
    ),
    "health-score": (
        "Segunda-feira, você abre a Saúde da Conta e filtra «risco alto»: "
        "3 clientes com nota abaixo de 40. Para cada um, o sistema sugere a ação "
        "(ligar, oferecer desconto, agendar visita) antes que cancelem."
    ),
    "templates": (
        "Cliente novo fechou? Escolha o modelo «Boas-vindas»: o sistema preenche "
        "nome e dados sozinho e você só copia e envia. O que levava 5 minutos "
        "passa a levar 10 segundos."
    ),
    "pipeline": (
        "Você cria a oportunidade «Projeto Site — R$ 15.000» na etapa Proposta. "
        "Na reunião semanal, o funil mostra que ela está parada há 10 dias — "
        "hora de fazer follow-up antes que esfrie."
    ),
    "forecast": (
        "O chefe pergunta: «quanto entra este mês?». Você abre a Previsão: "
        "R$ 80.000 em negócios abertos, ponderados pela chance de fechar = "
        "R$ 42.000 prováveis. Resposta na hora, com base real."
    ),
    "productivity": (
        "No fim do mês, você compara o time: a Carla resolveu 40 tickets com "
        "nota 4,8; o Bruno vendeu R$ 30.000. Você reconhece os destaques e "
        "treina quem ficou abaixo da média."
    ),
    "marketing-campaigns": (
        "Você investiu em anúncio no Instagram e disparo de e-mail. Cadastra as "
        "duas campanhas e descobre: o Instagram trouxe 50 leads (8 qualificados), "
        "o e-mail trouxe 20 (12 qualificados). Agora sabe onde investir."
    ),
    "lead-scoring": (
        "Chegaram 80 leads da campanha. Em vez de ligar um por um, você abre a "
        "Qualificação: 12 estão na faixa A (quentes). O time começa por eles e "
        "fecha mais rápido."
    ),
    "segmentation": (
        "Você quer reativar clientes de São Paulo parados há 60 dias. Monta a "
        "lista com 2 filtros, exporta e dispara uma oferta só para esse grupo — "
        "comunicação certa, sem spam para o resto da base."
    ),
    "executive-view": (
        "Reunião de segunda: você projeta o Painel do Negócio e mostra vendas do "
        "mês, fila de atendimento e satisfação — tudo numa tela, sem montar "
        "planilha na véspera."
    ),
    "ai-insights": (
        "Você abre os Insights e a IA aponta: «3 clientes com padrão de "
        "cancelamento», «tickets de cobrança subiram 40%». Cada alerta vem com a "
        "ação recomendada. Você age antes do problema crescer."
    ),
    "rbac-admin": (
        "Entrou uma estagiária no time. Você cria o usuário dela com perfil "
        "«Atendimento»: ela vê tickets e clientes, mas não acessa números de "
        "faturamento nem configurações. Tudo fica registrado na auditoria."
    ),
    "benchmark": (
        "Antes de decidir o próximo investimento no CRM, você abre o Comparativo "
        "e vê o que Salesforce e HubSpot oferecem a mais — e o que já está no "
        "mesmo nível. Decisão informada, sem achismo."
    ),
}


def get_service_example(sid: str) -> str:
    return SERVICE_EXAMPLES.get(sid, "")


# ---------------------------------------------------------------------------
# Busca em linguagem natural: sinônimos e termos do dia a dia por serviço.
# ---------------------------------------------------------------------------
SEARCH_KEYWORDS = {
    "ticketing-sla": (
        "atender atendimento chamado ticket reclamacao reclamar pedido duvida "
        "problema sla prazo fila resposta responder suporte resolver demanda "
        "solicitacao cliente reclamou"
    ),
    "channel-intake": (
        "whatsapp zap email e-mail site formulario mensagem canal canais entrada "
        "receber inbox chegou mandou enviou omnichannel centralizar"
    ),
    "tasks-cadences": (
        "lembrete lembrar followup follow retorno retornar esquecer esqueci "
        "cadencia tarefa agenda avisar aviso lead esfriar recontato cobrar depois"
    ),
    "customer-360": (
        "ficha cliente completo historico tudo sobre conta perfil 360 conhecer "
        "informacao dados quem antes de ligar contexto"
    ),
    "timeline": (
        "linha tempo historico cronologico ordem interacao diario timeline "
        "aconteceu conversado registro passado"
    ),
    "health-score": (
        "cancelamento cancelar churn risco saude conta sair perder cliente "
        "retencao reter abandonar insatisfeito prestes evitar fuga"
    ),
    "templates": (
        "modelo mensagem pronta template resposta rapida boas-vindas cobranca "
        "macro padrao copiar texto pronto agilizar"
    ),
    "pipeline": (
        "funil venda vendas vender negocio negocios oportunidade etapa fechar "
        "fechamento deal comercial pipeline proposta acompanhar travou"
    ),
    "forecast": (
        "previsao prever receita faturar faturamento quanto entrar dinheiro "
        "projecao meta forecast estimar mes resultado financeiro"
    ),
    "productivity": (
        "produtividade time equipe desempenho performance vendedor ranking "
        "comparar pessoa quem vendeu resolveu metrica individual"
    ),
    "marketing-campaigns": (
        "campanha marketing divulgacao divulgar anuncio roi retorno investimento "
        "disparo publicidade midia trouxe resultado instagram google"
    ),
    "lead-scoring": (
        "lead leads priorizar qualificar qualificacao nota score quente frio "
        "interessado potencial comprar comecar por quem melhor"
    ),
    "segmentation": (
        "lista listas segmento segmentacao filtro filtrar grupo publico exportar "
        "base recorte regiao inativo especifico"
    ),
    "executive-view": (
        "painel resumo kpi indicador numero numeros visao geral executivo "
        "dashboard negocio gestor chefe reuniao relatorio"
    ),
    "ai-insights": (
        "ia inteligencia artificial sugestao sugerir recomendacao insight "
        "automatico alerta anomalia o que fazer proximo passo assistente"
    ),
    "rbac-admin": (
        "usuario usuarios permissao permissoes acesso acessos perfil papel senha "
        "administrar administracao seguranca auditoria liberar bloquear"
    ),
    "benchmark": (
        "concorrente concorrentes comparar mercado benchmark salesforce hubspot "
        "comparativo evoluir referencia"
    ),
}

_STOPWORDS = {
    "que", "com", "para", "por", "quero", "como", "uma", "meu", "minha", "dos",
    "das", "nao", "não", "mais", "ver", "saber", "fazer", "preciso", "quais",
    "qual", "onde", "esta", "estao", "sem", "ter", "vou", "ser",
}


def _normalize_text(text: str) -> str:
    """Minúsculas e sem acentos, para casar «previsão» com «previsao»."""
    return (
        unicodedata.normalize("NFKD", str(text).lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def search_services(query: str, limit: int = 6) -> list[dict[str, Any]]:
    """Busca em linguagem natural: entende frases como «cliente quer cancelar».

    Pontuação: palavra-chave dedicada vale 3, título vale 2, demais textos valem 1.
    Retorna os serviços ordenados por relevância (apenas score > 0).
    """
    tokens = [
        t for t in _normalize_text(query).split()
        if len(t) >= 3 and t not in _STOPWORDS
    ]
    if not tokens:
        return []

    scored: list[tuple[int, dict[str, Any]]] = []
    for service in SERVICE_CATALOG:
        sid = str(service["id"])
        keywords = _normalize_text(SEARCH_KEYWORDS.get(sid, ""))
        title = _normalize_text(service["title"])
        body = _normalize_text(
            " ".join([
                str(service.get("tagline", "")),
                str(service.get("summary", "")),
                str(service.get("description", "")),
                str(service.get("outcome", "")),
            ])
        )
        score = 0
        for token in tokens:
            if token in keywords:
                score += 3
            if token in title:
                score += 2
            if token in body:
                score += 1
        if score > 0:
            scored.append((score, service))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [service for _, service in scored[:limit]]
