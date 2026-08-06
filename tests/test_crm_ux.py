"""Testes da camada de usabilidade (crm_ux)."""

from datetime import date

import pandas as pd
import pytest

from crm_ux import (
    build_day_agenda,
    deal_health,
    describe_document,
    find_duplicates,
    format_brl,
    format_compact_brl,
    format_cpf_cnpj,
    format_date_br,
    global_search,
    last_activity_by_customer,
    onboarding_progress,
    onboarding_steps,
    parse_date,
    pipeline_totals,
    summarize_stage,
    validate_cnpj,
    validate_cpf,
)


class TestFormatacaoBRL:
    @pytest.mark.parametrize(
        "valor,esperado",
        [
            (190000, "R$ 190.000"),
            (0, "R$ 0"),
            (1500, "R$ 1.500"),
            (1234567, "R$ 1.234.567"),
            (-5000, "R$ -5.000"),
        ],
    )
    def test_milhar_usa_ponto(self, valor, esperado):
        assert format_brl(valor) == esperado

    def test_decimal_usa_virgula(self):
        # O ponto-e-vírgula invertidos são o erro clássico de i18n pt-BR.
        assert format_brl(1234.56, decimals=2) == "R$ 1.234,56"

    def test_valor_invalido_nao_quebra(self):
        assert format_brl(None) == "—"
        assert format_brl("abc") == "—"

    @pytest.mark.parametrize(
        "valor,esperado",
        [
            (2_400_000, "R$ 2,4 mi"),
            (340_000, "R$ 340 mil"),
            (900, "R$ 900"),
        ],
    )
    def test_formato_compacto(self, valor, esperado):
        assert format_compact_brl(valor) == esperado


class TestDatas:
    def test_iso_para_formato_br(self):
        assert format_date_br("2026-05-19") == "19/05/2026"

    def test_iso_com_hora(self):
        assert format_date_br("2026-05-19T13:40:00+00:00") == "19/05/2026"

    def test_invalida_vira_travessao(self):
        assert format_date_br("") == "—"
        assert format_date_br(None) == "—"
        assert parse_date("data ruim") is None


class TestDocumentosBrasileiros:
    """Validação de dígito verificador — expectativa básica de CRM no Brasil."""

    @pytest.mark.parametrize("cpf", ["529.982.247-25", "52998224725", "111.444.777-35"])
    def test_cpf_valido(self, cpf):
        assert validate_cpf(cpf) is True

    @pytest.mark.parametrize(
        "cpf",
        [
            "529.982.247-26",   # dígito verificador errado
            "111.111.111-11",   # todos iguais
            "123",              # curto demais
            "",
            None,
        ],
    )
    def test_cpf_invalido(self, cpf):
        assert validate_cpf(cpf) is False

    @pytest.mark.parametrize("cnpj", ["11.222.333/0001-81", "11222333000181"])
    def test_cnpj_valido(self, cnpj):
        assert validate_cnpj(cnpj) is True

    @pytest.mark.parametrize(
        "cnpj",
        [
            "11.222.333/0001-82",  # dígito verificador errado
            "00.000.000/0000-00",  # todos iguais
            "11222333",            # curto demais
            None,
        ],
    )
    def test_cnpj_invalido(self, cnpj):
        assert validate_cnpj(cnpj) is False

    def test_mascara_por_tamanho(self):
        assert format_cpf_cnpj("52998224725") == "529.982.247-25"
        assert format_cpf_cnpj("11222333000181") == "11.222.333/0001-81"

    def test_mensagem_orienta_o_usuario(self):
        ok, msg = describe_document("11222333000181")
        assert ok is True and "válido" in msg

        ok, msg = describe_document("11222333000182")
        assert ok is False and "inválido" in msg

        ok, msg = describe_document("123")
        assert ok is False and "11 dígitos" in msg


class TestSaudeDaNegociacao:
    """Padrão 'rotting' do Pipedrive: sinalizar negociação parada."""

    HOJE = date(2026, 8, 6)

    def test_negociacao_recente_esta_ok(self):
        health = deal_health("Proposta", "2026-08-05", today=self.HOJE)
        assert health.status == "ok"
        assert health.is_stale is False

    def test_ultrapassar_limite_da_etapa_marca_parada(self):
        # Proposta tolera 10 dias; 15 dias sem contato está parada.
        health = deal_health("Proposta", "2026-07-22", today=self.HOJE)
        assert health.status == "parado"
        assert health.days_idle == 15
        assert "15 dias" in health.label

    def test_zona_de_atencao_antes_do_limite(self):
        # 8 dias numa etapa que tolera 10 = 80% do limite.
        health = deal_health("Proposta", "2026-07-29", today=self.HOJE)
        assert health.status == "atencao"

    def test_etapas_avancadas_apodrecem_mais_rapido(self):
        # O mesmo silêncio de 8 dias: tolerável na Descoberta, crítico na Negociação.
        assert deal_health("Descoberta", "2026-07-29", today=self.HOJE).status == "ok"
        assert deal_health("Negociacao", "2026-07-29", today=self.HOJE).status == "parado"

    def test_etapa_fechada_nunca_estagna(self):
        health = deal_health("Fechado ganho", "2020-01-01", today=self.HOJE)
        assert health.status == "fechado"
        assert health.is_stale is False

    def test_sem_interacao_registrada_conta_como_parada(self):
        health = deal_health("Proposta", None, today=self.HOJE)
        assert health.is_stale is True
        assert "Sem interação" in health.label

    def test_data_futura_nao_gera_dias_negativos(self):
        health = deal_health("Proposta", "2026-09-01", today=self.HOJE)
        assert health.days_idle == 0


class TestUltimaInteracao:
    def test_pega_a_interacao_mais_recente_por_cliente(self):
        interactions = pd.DataFrame([
            {"customer_id": "C-1", "event_at": "2026-07-01"},
            {"customer_id": "C-1", "event_at": "2026-08-01"},
            {"customer_id": "C-2", "event_at": "2026-06-15"},
        ])
        latest = last_activity_by_customer(interactions)
        assert latest["C-1"] == date(2026, 8, 1)
        assert latest["C-2"] == date(2026, 6, 15)

    def test_dataframe_vazio(self):
        assert last_activity_by_customer(pd.DataFrame()) == {}


@pytest.fixture
def deals_df():
    return pd.DataFrame([
        {"deal_id": "D-1", "stage": "Proposta", "value": 68000, "probability": 65, "owner": "Rafael", "customer_id": "C-1"},
        {"deal_id": "D-2", "stage": "Proposta", "value": 32000, "probability": 50, "owner": "Camila", "customer_id": "C-2"},
        {"deal_id": "D-3", "stage": "Negociacao", "value": 104000, "probability": 55, "owner": "Camila", "customer_id": "C-3"},
    ])


class TestResumoDeEtapa:
    """Cabeçalho de coluna do funil estilo Pipedrive."""

    def test_soma_valor_e_conta_oportunidades(self, deals_df):
        resumo = summarize_stage(deals_df, "Proposta")
        assert resumo.count == 2
        assert resumo.total_value == 100000

    def test_valor_ponderado_usa_probabilidade(self, deals_df):
        resumo = summarize_stage(deals_df, "Proposta")
        # 68000*0.65 + 32000*0.50 = 44200 + 16000
        assert resumo.weighted_value == pytest.approx(60200)

    def test_conta_negociacoes_paradas(self, deals_df):
        resumo = summarize_stage(deals_df, "Proposta", stale_ids={"D-1"})
        assert resumo.stale_count == 1

    def test_etapa_vazia(self, deals_df):
        resumo = summarize_stage(deals_df, "Descoberta")
        assert resumo.count == 0
        assert resumo.headline == "Nenhuma oportunidade"

    def test_headline_singular_e_plural(self, deals_df):
        assert "1 oportunidade ·" in summarize_stage(deals_df, "Negociacao").headline
        assert "2 oportunidades ·" in summarize_stage(deals_df, "Proposta").headline

    def test_valor_nao_numerico_nao_quebra(self):
        sujo = pd.DataFrame([{"deal_id": "D-9", "stage": "Proposta", "value": "n/d", "probability": None}])
        resumo = summarize_stage(sujo, "Proposta")
        assert resumo.count == 1
        assert resumo.total_value == 0.0


class TestTotaisDoFunil:
    def test_totais_e_ticket_medio(self, deals_df):
        totais = pipeline_totals(deals_df)
        assert totais["count"] == 3
        assert totais["total"] == 204000
        assert totais["average"] == pytest.approx(68000)

    def test_filtra_por_etapas_abertas(self, deals_df):
        totais = pipeline_totals(deals_df, open_stages=["Proposta"])
        assert totais["count"] == 2

    def test_sem_dados(self):
        assert pipeline_totals(pd.DataFrame())["total"] == 0.0


class TestDeteccaoDeDuplicados:
    @pytest.fixture
    def customers(self):
        return pd.DataFrame([
            {"customer_id": "C-1", "name": "Ecoplus Engenharia", "document": "11.222.333/0001-81", "email": "contato@ecoplus.com.br"},
            {"customer_id": "C-2", "name": "Northwind Labs", "document": "52998224725", "email": "hello@northwind.com"},
        ])

    def test_documento_igual_com_mascara_diferente(self, customers):
        # Mesmo CNPJ digitado sem pontuação deve ser detectado.
        dups = find_duplicates(customers, document="11222333000181")
        assert len(dups) == 1
        assert dups[0]["customer_id"] == "C-1"
        assert "mesmo CPF/CNPJ" in dups[0]["reasons"]

    def test_nome_ignora_acento_caixa_e_sufixo(self, customers):
        dups = find_duplicates(customers, name="ECOPLUS ENGENHARIA LTDA")
        assert len(dups) == 1
        assert "mesmo nome" in dups[0]["reasons"]

    def test_email_duplicado(self, customers):
        dups = find_duplicates(customers, email="CONTATO@ecoplus.com.br")
        assert dups and "mesmo e-mail" in dups[0]["reasons"]

    def test_cliente_novo_nao_gera_falso_positivo(self, customers):
        assert find_duplicates(customers, name="Empresa Inédita", document="11444777000199") == []

    def test_base_vazia(self):
        assert find_duplicates(pd.DataFrame(), name="Qualquer") == []


class TestAgendaDoDia:
    HOJE = date(2026, 8, 6)

    @pytest.fixture
    def dados(self):
        tasks = pd.DataFrame([
            {"task": "Ligar para Ecoplus", "owner": "Camila Costa", "due_date": "2026-08-01", "priority": "Alta"},
            {"task": "Enviar proposta", "owner": "Camila Costa", "due_date": "2026-08-06", "priority": "Media"},
            {"task": "Tarefa de outro", "owner": "Rafael Nogueira", "due_date": "2026-08-01", "priority": "Alta"},
            {"task": "Futura", "owner": "Camila Costa", "due_date": "2026-09-01", "priority": "Baixa"},
        ])
        deals = pd.DataFrame([
            {"deal_id": "D-1", "name": "Expansao", "stage": "Negociacao", "owner": "Camila Costa", "customer_id": "C-1", "value": 104000, "probability": 55},
        ])
        tickets = pd.DataFrame([
            {"ticket_id": "T-1", "subject": "Erro no portal", "owner": "Camila Costa", "status": "Aberto", "sla_hours": 10, "age_hours": 9},
            {"ticket_id": "T-2", "subject": "Dúvida", "owner": "Camila Costa", "status": "Aberto", "sla_hours": 10, "age_hours": 2},
            {"ticket_id": "T-3", "subject": "Já resolvido", "owner": "Camila Costa", "status": "Resolvido", "sla_hours": 10, "age_hours": 50},
        ])
        interactions = pd.DataFrame([
            {"customer_id": "C-1", "event_at": "2026-07-01"},
        ])
        return tasks, deals, tickets, interactions

    def test_separa_vencidas_de_hoje(self, dados):
        tasks, deals, tickets, interactions = dados
        agenda = build_day_agenda(tasks, deals, tickets, interactions, owner="Camila Costa", today=self.HOJE)
        assert [t["task"] for t in agenda.overdue_tasks] == ["Ligar para Ecoplus"]
        assert [t["task"] for t in agenda.today_tasks] == ["Enviar proposta"]

    def test_ignora_tarefa_de_outro_responsavel(self, dados):
        tasks, deals, tickets, interactions = dados
        agenda = build_day_agenda(tasks, deals, tickets, interactions, owner="Camila Costa", today=self.HOJE)
        assert all("outro" not in t["task"] for t in agenda.overdue_tasks)

    def test_negociacao_parada_entra_na_agenda(self, dados):
        tasks, deals, tickets, interactions = dados
        agenda = build_day_agenda(tasks, deals, tickets, interactions, owner="Camila Costa", today=self.HOJE)
        assert len(agenda.stale_deals) == 1
        assert agenda.stale_deals[0]["deal_id"] == "D-1"

    def test_ticket_perto_do_sla_entra_e_resolvido_fica_fora(self, dados):
        tasks, deals, tickets, interactions = dados
        agenda = build_day_agenda(tasks, deals, tickets, interactions, owner="Camila Costa", today=self.HOJE)
        ids = [t["ticket_id"] for t in agenda.sla_risk_tickets]
        assert ids == ["T-1"]  # T-2 confortável, T-3 já resolvido

    def test_contagem_total_de_acoes(self, dados):
        tasks, deals, tickets, interactions = dados
        agenda = build_day_agenda(tasks, deals, tickets, interactions, owner="Camila Costa", today=self.HOJE)
        assert agenda.total_actions == 4
        assert agenda.is_empty is False

    def test_dia_sem_pendencia(self):
        agenda = build_day_agenda(None, None, None, None, owner="Alguem", today=self.HOJE)
        assert agenda.is_empty is True

    def test_mais_atrasada_primeiro(self):
        tasks = pd.DataFrame([
            {"task": "Atraso pequeno", "owner": "A", "due_date": "2026-08-05", "priority": "Alta"},
            {"task": "Atraso grande", "owner": "A", "due_date": "2026-07-01", "priority": "Alta"},
        ])
        agenda = build_day_agenda(tasks, None, None, None, owner="A", today=self.HOJE)
        assert agenda.overdue_tasks[0]["task"] == "Atraso grande"


class TestBuscaGlobal:
    @pytest.fixture
    def bases(self):
        customers = pd.DataFrame([
            {"customer_id": "C-1", "name": "Ecoplus Engenharia", "segment": "Industria"},
        ])
        deals = pd.DataFrame([
            {"deal_id": "D-1", "name": "Plano Growth + onboarding", "stage": "Proposta"},
        ])
        tickets = pd.DataFrame([
            {"ticket_id": "T-1", "subject": "Integração travando", "status": "Aberto"},
        ])
        return customers, deals, tickets

    def test_encontra_cliente_por_prefixo(self, bases):
        resultados = global_search("eco", *bases)
        assert any(r["kind"] == "Cliente" and r["id"] == "C-1" for r in resultados)

    def test_busca_ignora_acento(self, bases):
        resultados = global_search("integracao", *bases)
        assert any(r["kind"] == "Chamado" for r in resultados)

    def test_atravessa_os_tres_modulos(self, bases):
        customers, deals, tickets = bases
        tipos = {r["kind"] for r in global_search("o", customers, deals, tickets)}
        # termo curto demais não busca
        assert tipos == set()

        resultados = global_search("plano", customers, deals, tickets)
        assert resultados[0]["section"] == "Funil Comercial"

    def test_termo_sem_resultado(self, bases):
        assert global_search("xyzabc", *bases) == []

    def test_prefixo_vem_antes_de_substring(self):
        customers = pd.DataFrame([
            {"customer_id": "C-1", "name": "Alfa Nortec", "segment": "X"},
            {"customer_id": "C-2", "name": "Nortec Brasil", "segment": "X"},
        ])
        resultados = global_search("nortec", customers)
        assert resultados[0]["id"] == "C-2"


class TestOnboarding:
    def test_marca_passos_concluidos_pelos_dados(self):
        customers = pd.DataFrame([{"customer_id": "C-1"}])
        steps = onboarding_steps(customers, None, None, templates_count=0)
        por_chave = {s["key"]: s["done"] for s in steps}
        assert por_chave["cliente"] is True
        assert por_chave["oportunidade"] is False

    def test_progresso(self):
        customers = pd.DataFrame([{"customer_id": "C-1"}])
        deals = pd.DataFrame([{"deal_id": "D-1"}])
        steps = onboarding_steps(customers, deals, None, templates_count=2)
        assert onboarding_progress(steps) == (3, 4)
