"""Carga de demonstração com a operação da MEiSHOP.

Para que serve
--------------
Mostrar o CRM funcionando com dados que se parecem com o trabalho real da
MEiSHOP, em vez dos clientes genéricos do exemplo original ("Northwind Labs",
"Clina Prime"). Uma demonstração só convence quando a pessoa reconhece a
própria operação na tela.

O que este arquivo NÃO é
------------------------
Não é migração, não é importação e não serve para popular produção. Os dados
são inventados a partir do que o site meishop.com.br descreve publicamente:
não há cliente, CNPJ, telefone ou valor real de contrato aqui.

Trava de segurança
------------------
O script se recusa a rodar quando `DATABASE_URL` está definida. É a variável
que aponta para o Postgres do Supabase — ou seja, para a base de verdade.
Demonstração escreve em arquivo local e em nenhum outro lugar.

Como usar
---------
    python demo_meishop.py                    # cria Data/demo_meishop.sqlite3
    CRM_DB_PATH=/tmp/x.sqlite3 python demo_meishop.py

Depois, para abrir o CRM sobre essa base:

    CRM_DB_PATH=Data/demo_meishop.sqlite3 streamlit run crm_app.py

Modelagem
---------
Duas coisas convivem no cadastro de clientes, porque convivem no negócio:

- **Contratos de rede** (franqueadora, construtora, rede de vendas diretas).
  Uma conta que representa centenas de MEIs. É a venda grande, com ciclo
  longo, e é o que enche o funil.
- **MEIs individuais**, que chegam pelo Instagram e assinam o plano sozinhos.
  Ticket pequeno, volume alto, praticamente sem ciclo de venda.

O valor do negócio é sempre **anual** (mensalidade × pessoas × 12), para que a
previsão ponderada do funil signifique receita de um ano.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

HOJE = date(2026, 8, 13)


def _dia(delta: int) -> str:
    return (HOJE + timedelta(days=delta)).isoformat()


def _hora(delta_horas: int) -> str:
    from datetime import datetime, timezone

    base = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)
    return (base - timedelta(hours=delta_horas)).strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Equipe
#
# As contas do seed têm nomes de pessoas fictícias. A demonstração renomeia
# para o papel que exercem, o que evita inventar funcionários e deixa claro na
# tela quem cuida do quê.
# ---------------------------------------------------------------------------
EQUIPE = {
    "vendas": "Comercial Parcerias",
    "atendimento": "Suporte MEI",
    "marketing": "Conteudo @dicasmei",
    "cs": "Relacionamento",
}

COMERCIAL = "vendas"
SUPORTE = "atendimento"
CONTEUDO = "marketing"
RELACIONAMENTO = "cs"


# ---------------------------------------------------------------------------
# Contas
#
# `segment` usa a própria segmentação do site: Beleza, Vendas Diretas,
# Franquias, Construção Civil, Prestador de Serviços, Microempresa.
# ---------------------------------------------------------------------------
CONTAS = [
    # --- Contratos de rede: a venda grande ---
    {
        "name": "Rede Bella Hair — Franqueadora",
        "segment": "Beleza",
        "city": "Sao Paulo",
        "owner": COMERCIAL,
        "status": "Expansao",
        "health": 82,
        "ltv": 112320,
        "channel": "Indicacao",
        "source": "Parceria",
        "next": "Fechar piloto com 40 profissionais antes do contrato cheio",
        "pessoas": 240,
    },
    {
        "name": "Construtora Vale Verde",
        "segment": "Construcao Civil",
        "city": "Bauru",
        "owner": COMERCIAL,
        "status": "Ativo",
        "health": 68,
        "ltv": 39780,
        "channel": "Formulario",
        "source": "Site",
        "next": "Enviar comparativo de risco trabalhista para o juridico deles",
        "pessoas": 85,
    },
    {
        "name": "Essencia Cosmeticos — Vendas Diretas",
        "segment": "Vendas Diretas",
        "city": "Campinas",
        "owner": COMERCIAL,
        "status": "Novo",
        "health": 55,
        "ltv": 0,
        "channel": "LinkedIn",
        "source": "Prospeccao ativa",
        "next": "Descobrir quantas revendedoras ja tem CNPJ",
        "pessoas": 420,
    },
    {
        "name": "Instituto Avante — Educacao Empreendedora",
        "segment": "Franquias",
        "city": "Belo Horizonte",
        "owner": COMERCIAL,
        "status": "Ativo",
        "health": 91,
        "ltv": 70200,
        "channel": "Indicacao",
        "source": "Parceria",
        "next": "Renovacao em outubro — antecipar conversa",
        "pessoas": 150,
    },
    {
        "name": "TechDev Solucoes — contrata PJ",
        "segment": "Prestador de Servicos",
        "city": "Sao Paulo",
        "owner": COMERCIAL,
        "status": "Expansao",
        "health": 74,
        "ltv": 14040,
        "channel": "Formulario",
        "source": "Site",
        "next": "Proposta para incluir os 12 novos contratados de setembro",
        "pessoas": 30,
    },
    {
        "name": "Studio Lumine Estetica",
        "segment": "Beleza",
        "city": "Bauru",
        "owner": RELACIONAMENTO,
        "status": "Ativo",
        "health": 88,
        "ltv": 5616,
        "channel": "Instagram",
        "source": "@dicasmei",
        "next": "Convidar para depoimento em video",
        "pessoas": 12,
    },
    {
        "name": "Barbearia Dom Rafael — 3 unidades",
        "segment": "Beleza",
        "city": "Ribeirao Preto",
        "owner": RELACIONAMENTO,
        "status": "Risco",
        "health": 41,
        "ltv": 3744,
        "channel": "WhatsApp",
        "source": "@dicasmei",
        "next": "Dois profissionais com DAS atrasado — ligar hoje",
        "pessoas": 8,
    },
    {
        "name": "Grupo Mineiro de Servicos Predias",
        "segment": "Microempresa",
        "city": "Belo Horizonte",
        "owner": COMERCIAL,
        "status": "Ativo",
        "health": 77,
        "ltv": 18000,
        "channel": "Indicacao",
        "source": "Parceria",
        "next": "Migrou de MEI para ME — validar plano contabil mensal",
        "pessoas": 1,
    },
    # --- MEIs individuais: volume vindo do conteúdo ---
    {
        "name": "Juliana Prado — Manicure",
        "segment": "Beleza",
        "city": "Bauru",
        "owner": SUPORTE,
        "status": "Ativo",
        "health": 80,
        "ltv": 468,
        "channel": "Instagram",
        "source": "@dicasmei",
        "next": "Primeira NFS-e do mes ainda nao emitida",
    },
    {
        "name": "Marcos Vieira — Eletricista",
        "segment": "Construcao Civil",
        "city": "Jau",
        "owner": SUPORTE,
        "status": "Ativo",
        "health": 72,
        "ltv": 468,
        "channel": "WhatsApp",
        "source": "@dicasmei",
        "next": "Confirmar CNAE apos regularizacao",
    },
    {
        "name": "Patricia Lemos — Consultora de Vendas",
        "segment": "Vendas Diretas",
        "city": "Marilia",
        "owner": SUPORTE,
        "status": "Ativo",
        "health": 65,
        "ltv": 468,
        "channel": "Instagram",
        "source": "@dicasmei",
        "next": "Faturamento em 71% do limite — avisar sobre mudanca de porte",
    },
    {
        "name": "Rodrigo Salles — Personal Trainer",
        "segment": "Prestador de Servicos",
        "city": "Sao Paulo",
        "owner": SUPORTE,
        "status": "Novo",
        "health": 60,
        "ltv": 0,
        "channel": "Instagram",
        "source": "@dicasmei",
        "next": "Abertura de CNPJ em andamento — cobrar documento pendente",
    },
    {
        "name": "Camila Aoki — Designer",
        "segment": "Prestador de Servicos",
        "city": "Bauru",
        "owner": SUPORTE,
        "status": "Ativo",
        "health": 84,
        "ltv": 936,
        "channel": "YouTube",
        "source": "Organico",
        "next": "Renovou por 2 anos — pedir indicacao",
    },
    {
        "name": "Antonio Ferraz — Pedreiro",
        "segment": "Construcao Civil",
        "city": "Bauru",
        "owner": SUPORTE,
        "status": "Risco",
        "health": 38,
        "ltv": 234,
        "channel": "WhatsApp",
        "source": "Construtora Vale Verde",
        "next": "DAS de junho e julho em aberto — risco de perder o CNPJ",
    },
]


# ---------------------------------------------------------------------------
# Funil
#
# Os estágios são os que o CRM já usa: Prospeccao, Proposta, Negociacao,
# Fechado ganho, Fechado perdido.
# ---------------------------------------------------------------------------
# ATENÇÃO — descoberta ao montar esta carga:
#
# A primeira versão deste arquivo usava "Prospeccao" como etapa. O negócio de
# R$ 196 mil foi gravado sem erro e **desapareceu do funil**: o kanban e o
# «Resumo do funil» filtram por uma lista fechada
# ("Descoberta", "Proposta", "Negociacao"), enquanto outra métrica do produto
# conta tudo que não está fechado. Duas telas, dois totais, nenhum aviso.
#
# Nada no sistema valida o campo `stage` — nem `add_deal`, nem `update_entity`,
# nem a API do webhook. Qualquer string entra e o dinheiro sai da conta.
#
# Aqui as etapas são as canônicas. O defeito do produto segue em aberto.
NEGOCIOS = [
    {
        "conta": "Rede Bella Hair — Franqueadora",
        "name": "Lei do Salao Parceiro — 240 profissionais",
        "stage": "Negociacao",
        "value": 112320,
        "prob": 60,
        "owner": COMERCIAL,
        "close": _dia(32),
        "source": "Parceria",
    },
    {
        "conta": "Essencia Cosmeticos — Vendas Diretas",
        "name": "Abertura de MEI em lote — 420 revendedoras",
        "stage": "Descoberta",
        "value": 196560,
        "prob": 15,
        "owner": COMERCIAL,
        "close": _dia(94),
        "source": "Prospeccao ativa",
    },
    {
        "conta": "Construtora Vale Verde",
        "name": "Terceirizados regularizados — 85 CNPJs",
        "stage": "Proposta",
        "value": 39780,
        "prob": 45,
        "owner": COMERCIAL,
        "close": _dia(21),
        "source": "Site",
    },
    {
        "conta": "TechDev Solucoes — contrata PJ",
        "name": "Expansao — 12 contratados de setembro",
        "stage": "Negociacao",
        "value": 5616,
        "prob": 75,
        "owner": COMERCIAL,
        "close": _dia(11),
        "source": "Base instalada",
    },
    {
        "conta": "Instituto Avante — Educacao Empreendedora",
        "name": "Renovacao anual — 150 alunos empreendedores",
        "stage": "Proposta",
        "value": 70200,
        "prob": 70,
        "owner": COMERCIAL,
        "close": _dia(58),
        "source": "Base instalada",
    },
    {
        "conta": "Grupo Mineiro de Servicos Predias",
        "name": "Contador Online Mensal — migracao MEI para ME",
        "stage": "Fechado ganho",
        "value": 18000,
        "prob": 100,
        "owner": COMERCIAL,
        "close": _dia(-9),
        "source": "Parceria",
    },
    {
        "conta": "Studio Lumine Estetica",
        "name": "Plano anual — 12 profissionais",
        "stage": "Fechado ganho",
        "value": 5616,
        "prob": 100,
        "owner": RELACIONAMENTO,
        "close": _dia(-24),
        "source": "@dicasmei",
    },
    {
        "conta": "Barbearia Dom Rafael — 3 unidades",
        "name": "Ampliacao para a 3a unidade",
        "stage": "Fechado perdido",
        "value": 3744,
        "prob": 0,
        "owner": RELACIONAMENTO,
        "close": _dia(-4),
        "source": "@dicasmei",
    },
]


# ---------------------------------------------------------------------------
# Atendimento
#
# São os chamados que aparecem de verdade numa operação de MEI: boleto que não
# chegou, nota recusada pela prefeitura, CNAE velho, teto de faturamento.
# ---------------------------------------------------------------------------
CHAMADOS = [
    {
        "conta": "Antonio Ferraz — Pedreiro",
        "subject": "DAS de junho e julho em aberto",
        "channel": "WhatsApp",
        "priority": "Alta",
        "status": "Em progresso",
        "sla": 4,
        "idade": 26,
        "categoria": "DAS",
        "owner": SUPORTE,
        "msg": "Cliente diz que nao recebeu o boleto. Verificar e-mail cadastrado "
               "e reenviar as duas guias com a multa recalculada.",
    },
    {
        "conta": "Juliana Prado — Manicure",
        "subject": "NFS-e recusada pela prefeitura — codigo de servico",
        "channel": "WhatsApp",
        "priority": "Alta",
        "status": "Em progresso",
        "sla": 4,
        "idade": 6,
        "categoria": "Nota Fiscal",
        "owner": SUPORTE,
        "msg": "Prefeitura devolveu com erro no codigo de servico. Corrigir e "
               "reemitir hoje: o cliente final dela paga contra nota.",
    },
    {
        "conta": "Patricia Lemos — Consultora de Vendas",
        "subject": "Faturamento em 71% do limite do MEI",
        "channel": "E-mail",
        "priority": "Media",
        "status": "Novo",
        "sla": 24,
        "idade": 12,
        "categoria": "Faturamento",
        "owner": RELACIONAMENTO,
        "msg": "No ritmo atual estoura o teto em novembro. Explicar mudanca de "
               "porte antes de virar problema, nao depois.",
    },
    {
        "conta": "Marcos Vieira — Eletricista",
        "subject": "Regularizacao de CNAE antigo",
        "channel": "WhatsApp",
        "priority": "Media",
        "status": "Aguardando cliente",
        "sla": 48,
        "idade": 51,
        "categoria": "Cadastro",
        "owner": SUPORTE,
        "msg": "Falta o comprovante de endereco para concluir a alteracao.",
    },
    {
        "conta": "Rodrigo Salles — Personal Trainer",
        "subject": "Abertura de CNPJ MEI — documento pendente",
        "channel": "Instagram",
        "priority": "Media",
        "status": "Aguardando cliente",
        "sla": 24,
        "idade": 30,
        "categoria": "Abertura",
        "owner": SUPORTE,
        "msg": "Veio de um Reels sobre quem pode ser MEI. Falta o titulo de "
               "eleitor para finalizar o cadastro.",
    },
    {
        "conta": "Rede Bella Hair — Franqueadora",
        "subject": "Piloto: 40 profissionais para abrir nesta semana",
        "channel": "E-mail",
        "priority": "Alta",
        "status": "Em progresso",
        "sla": 8,
        "idade": 3,
        "categoria": "Abertura",
        "owner": SUPORTE,
        "msg": "Planilha recebida com 40 nomes. O piloto e o que decide o "
               "contrato dos 240 — tratar como prioridade comercial.",
    },
    {
        "conta": "Construtora Vale Verde",
        "subject": "Relatorio mensal de CNPJs ativos para o RH",
        "channel": "E-mail",
        "priority": "Baixa",
        "status": "Resolvido",
        "sla": 48,
        "idade": 74,
        "categoria": "Relatorio",
        "owner": SUPORTE,
        "csat": 4.8,
        "msg": "Enviado com os 85 CNPJs e a situacao de cada um.",
    },
]


TAREFAS = [
    {
        "task": "Ligar para a Bella Hair sobre o piloto de 40 profissionais",
        "owner": COMERCIAL,
        "due": _dia(0),
        "priority": "Alta",
        "entity": "Rede Bella Hair — Franqueadora",
    },
    {
        "task": "Reemitir as NFS-e recusadas pela prefeitura de Bauru",
        "owner": SUPORTE,
        "due": _dia(0),
        "priority": "Alta",
        "entity": "Juliana Prado — Manicure",
    },
    {
        "task": "Recalcular e reenviar DAS em atraso — 6 clientes",
        "owner": SUPORTE,
        "due": _dia(1),
        "priority": "Alta",
        "entity": "Carteira",
    },
    {
        "task": "Enviar comparativo de risco trabalhista para a Vale Verde",
        "owner": COMERCIAL,
        "due": _dia(2),
        "priority": "Media",
        "entity": "Construtora Vale Verde",
    },
    {
        "task": "Avisar quem passou de 70% do limite de faturamento",
        "owner": RELACIONAMENTO,
        "due": _dia(4),
        "priority": "Media",
        "entity": "Carteira",
    },
    {
        "task": "Gravar Reels sobre DASN para o @dicasmei",
        "owner": CONTEUDO,
        "due": _dia(6),
        "priority": "Baixa",
        "entity": "Conteudo",
    },
    {
        "task": "Antecipar conversa de renovacao com o Instituto Avante",
        "owner": COMERCIAL,
        "due": _dia(9),
        "priority": "Media",
        "entity": "Instituto Avante — Educacao Empreendedora",
    },
]


# `revenue` é receita anual atribuída à campanha.
CAMPANHAS = [
    {
        "campaign": "Instagram @dicasmei — Reels 'quem pode ser MEI'",
        "channel": "Instagram",
        "leads": 1840,
        "qualified": 212,
        "conv": 11.5,
        "revenue": 99216,
    },
    {
        "campaign": "Instagram @dicasmei — Carrossel prazo da DASN",
        "channel": "Instagram",
        "leads": 960,
        "qualified": 74,
        "conv": 7.7,
        "revenue": 34632,
    },
    {
        "campaign": "YouTube — Como emitir NFS-e passo a passo",
        "channel": "YouTube",
        "leads": 430,
        "qualified": 61,
        "conv": 14.2,
        "revenue": 28548,
    },
    {
        "campaign": "Prospeccao B2B — franqueadoras e construtoras",
        "channel": "Outbound",
        "leads": 78,
        "qualified": 19,
        "conv": 24.4,
        "revenue": 240660,
    },
    {
        "campaign": "E-mail mensal do boleto DAS — recuperacao de atraso",
        "channel": "E-mail",
        "leads": 310,
        "qualified": 148,
        "conv": 47.7,
        "revenue": 21528,
    },
]


# Conversas para a linha do tempo, além das que as próprias criações geram.
CONVERSAS = [
    (
        "Rede Bella Hair — Franqueadora",
        "Reuniao com a diretoria",
        "Fecharam em fazer um piloto com 40 profissionais de duas unidades "
        "antes de assinar os 240. Criterio de sucesso: todos com CNPJ ativo e "
        "primeira NFS-e emitida em 15 dias.",
        "Reuniao",
        -6,
    ),
    (
        "Rede Bella Hair — Franqueadora",
        "Planilha do piloto recebida",
        "40 nomes com CPF e atividade. Suporte iniciou as aberturas.",
        "E-mail",
        -3,
    ),
    (
        "Barbearia Dom Rafael — 3 unidades",
        "Cliente reclamou do atraso no DAS",
        "Dois profissionais ficaram com o CNPJ irregular porque o boleto foi "
        "para um e-mail antigo. Perdemos a ampliacao da 3a unidade por isso.",
        "WhatsApp",
        -4,
    ),
    (
        "Patricia Lemos — Consultora de Vendas",
        "Alerta de faturamento enviado",
        "Explicado por audio o que muda ao virar ME e quanto custa. Ela pediu "
        "para revisar em setembro com o numero fechado de agosto.",
        "WhatsApp",
        -2,
    ),
    (
        "Studio Lumine Estetica",
        "Aceitou dar depoimento",
        "Vai gravar um video curto contando que reduziu imposto com a Lei do "
        "Salao Parceiro. Material para o @dicasmei.",
        "WhatsApp",
        -1,
    ),
    (
        "Essencia Cosmeticos — Vendas Diretas",
        "Primeiro contato",
        "Gerente comercial pediu um caso parecido antes de levar para a "
        "diretoria. Enviado o formato usado na Bella Hair.",
        "LinkedIn",
        -8,
    ),
]


class ProducaoProtegida(RuntimeError):
    """Tentativa de carregar dado fictício onde vive o dado real."""


DATASET = "meishop"


def modo_demonstracao() -> bool:
    """A instância atual é a vitrine pública?

    Ligada por `CRM_DEMO_DATASET=meishop` no serviço de demonstração do
    Railway. A instância de produção não define a variável e portanto nunca
    entra neste caminho.
    """
    return os.getenv("CRM_DEMO_DATASET", "").strip().lower() == DATASET


def _proteger_producao() -> None:
    """Recusa escrever no banco de verdade.

    A demonstração inventa clientes, contratos e chamados, e o passo seguinte
    apaga as tabelas antes de popular. Fazer isso no Postgres de produção
    misturaria dado falso com dado real numa base sem rotina de backup
    própria — estrago difícil de desfazer e fácil de evitar.

    A trava olha `DATABASE_URL` porque é exatamente ela que distingue as duas
    instâncias: produção aponta para o Supabase, a demonstração roda em SQLite
    dentro do contêiner. Se alguém ligar `CRM_DEMO_DATASET` no serviço errado,
    é aqui que a bala para.
    """
    if os.getenv("DATABASE_URL"):
        raise ProducaoProtegida(
            "DATABASE_URL está definida, o que aponta para o banco de produção. "
            "Esta carga é de demonstração e só escreve em banco local."
        )


CHAVE_DE_CARGA = "demo_dataset_carregado"


def ja_carregada() -> bool:
    """A vitrine deste banco já foi montada?

    Marca explícita em `meta_state`, e não "a tabela de clientes está vazia".
    A primeira versão usava o critério de vazio e **não funcionou**: o
    `init_database` semeia clientes de exemplo antes desta verificação
    acontecer, então o banco nunca está vazio e a carga nunca rodava. A
    vitrine subia mostrando "Ecoplus Engenharia" e "Grupo Aurora" — os dados
    genéricos que ela existe para substituir.

    Uma marca própria também é mais honesta: a pergunta não é quantos clientes
    existem, é se este conjunto de dados já foi aplicado aqui.
    """
    import crm_backend as backend

    with backend._connect() as conexao:
        linha = conexao.execute(
            "SELECT value FROM meta_state WHERE key = ?", (CHAVE_DE_CARGA,)
        ).fetchone()
    return linha is not None and str(linha["value"]) == DATASET


def _marcar_como_carregada() -> None:
    import crm_backend as backend

    with backend._connect() as conexao:
        conexao.execute(
            "INSERT OR REPLACE INTO meta_state (key, value) VALUES (?, ?)",
            (CHAVE_DE_CARGA, DATASET),
        )
        conexao.commit()


def preparar_demonstracao_no_arranque() -> bool:
    """Popula a vitrine na primeira vez que o contêiner responde.

    Chamada pelo `crm_app.py` a cada sessão, mas só faz trabalho na primeira.
    Como a demonstração roda em SQLite dentro do contêiner, a marca de carga
    morre junto com o contêiner — o que dá de graça a propriedade mais útil de
    uma vitrine: **ela se restaura sozinha**. Um visitante pode apagar, editar
    e desarrumar o que quiser; o próximo deploy devolve tudo.

    Devolve True quando carregou, False quando não havia o que fazer. Nunca
    levanta exceção: uma falha aqui não pode derrubar a tela de login.
    """
    if not modo_demonstracao():
        return False
    try:
        _proteger_producao()
        if ja_carregada():
            return False
        _popular()
        _marcar_como_carregada()
        return True
    except Exception as erro:  # pragma: no cover - proteção de arranque
        print(f"[demo] não carreguei a demonstração: {erro}", file=sys.stderr, flush=True)
        return False


def carregar() -> dict[str, int]:
    """Uso por linha de comando: escolhe um arquivo local e popula."""
    _proteger_producao()

    os.environ.setdefault("CRM_DB_PATH", os.path.join("Data", "demo_meishop.sqlite3"))
    os.environ.setdefault("CRM_SEED_PASSWORD_ADMIN", "demonstracao-meishop-2026")

    import crm_backend as backend

    backend.init_database()
    return _popular()


def _popular() -> dict[str, int]:
    """Substitui o conteúdo do banco atual pela operação da MEiSHOP.

    Pressupõe schema criado e contas de usuário existentes. Quem chama é
    responsável por ter passado pela trava de produção.
    """
    import crm_backend as backend

    # Limpa os dados de exemplo do seed original.
    #
    # `init_database` semeia clientes genéricos ("Northwind Labs", "Clina
    # Prime") e chamados como "Treinamento do time de recepcao". Sem apagar,
    # a demonstração mistura os dois mundos e perde o efeito: a pessoa vê
    # metade da tela falando da operação dela e metade falando de nada.
    #
    # As contas de usuário ficam: são a equipe, não dado de exemplo.
    with backend._connect() as conexao:
        for tabela in ("interactions", "tickets", "deals", "tasks", "campaigns", "customers"):
            conexao.execute(f"DELETE FROM {tabela}")
        conexao.commit()

    admin = {"username": "admin", "full_name": "FLAVIO RINALDI", "role": "admin"}

    for login, rotulo in EQUIPE.items():
        try:
            backend.update_user(username=login, full_name=rotulo, actor=admin)
        except Exception as erro:  # pragma: no cover - ambiente de demonstração
            print(f"  aviso: não renomeei '{login}': {erro}")

    ids: dict[str, str] = {}
    for conta in CONTAS:
        pessoas = conta.get("pessoas")
        sufixo = f" · {pessoas} pessoas" if pessoas and pessoas > 1 else ""
        ids[conta["name"]] = backend.add_customer(
            {
                "name": conta["name"],
                "segment": conta["segment"],
                "city": conta["city"],
                "country": "Brasil",
                "owner": conta["owner"],
                "status": conta["status"],
                "health_score": conta["health"],
                "lifetime_value": conta["ltv"],
                "last_purchase": _dia(-14),
                "channel": conta["channel"],
                "next_action": conta["next"] + sufixo,
                "source": conta["source"],
            },
            actor=admin,
            source="demo-meishop",
        )

    for negocio in NEGOCIOS:
        backend.add_deal(
            {
                "customer_id": ids[negocio["conta"]],
                "name": negocio["name"],
                "stage": negocio["stage"],
                "value": negocio["value"],
                "probability": negocio["prob"],
                "owner": negocio["owner"],
                "close_date": negocio["close"],
                "source": negocio["source"],
            },
            actor=admin,
            source="demo-meishop",
        )

    for chamado in CHAMADOS:
        backend.add_ticket(
            {
                "customer_id": ids[chamado["conta"]],
                "subject": chamado["subject"],
                "channel": chamado["channel"],
                "status": chamado["status"],
                "priority": chamado["priority"],
                "owner": chamado["owner"],
                "sla_hours": chamado["sla"],
                "age_hours": chamado["idade"],
                "csat": chamado.get("csat", 0.0),
                "category": chamado["categoria"],
                "opened_at": _hora(chamado["idade"]),
                "message": chamado["msg"],
            },
            actor=admin,
            source="demo-meishop",
        )

    for campanha in CAMPANHAS:
        backend.add_campaign(
            {
                "campaign": campanha["campaign"],
                "channel": campanha["channel"],
                "leads": campanha["leads"],
                "qualified": campanha["qualified"],
                "conversion_rate": campanha["conv"],
                "revenue": campanha["revenue"],
            },
            actor=admin,
            source="demo-meishop",
        )

    with backend._connect() as conexao:
        conexao.execute("DELETE FROM tasks")
        for tarefa in TAREFAS:
            # Devolve o par (nome exibido, login) — as duas colunas da posse.
            nome, login = backend._resolver_username_do_responsavel(conexao, tarefa["owner"])
            conexao.execute(
                """
                INSERT INTO tasks (task, owner, owner_username, due_date, priority, entity, status)
                VALUES (?, ?, ?, ?, ?, ?, 'aberta')
                """,
                (
                    tarefa["task"],
                    nome,
                    login,
                    tarefa["due"],
                    tarefa["priority"],
                    tarefa["entity"],
                ),
            )
        conexao.commit()

    # As conversas vão por INSERT direto porque precisam de data no passado, e
    # `add_interaction` sempre grava o instante atual — correto para uso real,
    # inconveniente para montar uma linha do tempo de demonstração.
    with backend._connect() as conexao:
        for conta, titulo, corpo, canal, dias in CONVERSAS:
            conexao.execute(
                """
                INSERT INTO interactions
                    (customer_id, event_at, event_type, title, body, channel, owner, related_id)
                VALUES (?, ?, 'note', ?, ?, ?, ?, '')
                """,
                (ids[conta], f"{_dia(dias)}T14:00:00+00:00", titulo, corpo, canal,
                 EQUIPE[COMERCIAL]),
            )
        conexao.commit()

    return {
        "contas": len(CONTAS),
        "negocios": len(NEGOCIOS),
        "chamados": len(CHAMADOS),
        "tarefas": len(TAREFAS),
        "campanhas": len(CAMPANHAS),
        "conversas": len(CONVERSAS),
    }


if __name__ == "__main__":
    try:
        total = carregar()
    except ProducaoProtegida as erro:
        sys.exit(
            f"{erro}\n\n"
            "Rode sem a variável:  env -u DATABASE_URL python demo_meishop.py"
        )
    print("\nCarga de demonstração da MEiSHOP concluída:")
    for rotulo, quantidade in total.items():
        print(f"  {quantidade:>3}  {rotulo}")
    print(f"\nBanco: {os.environ['CRM_DB_PATH']}")
    print("Abrir:  CRM_DB_PATH=%s streamlit run crm_app.py" % os.environ["CRM_DB_PATH"])
