"""Testes das automações e da importação de planilha.

Automação que duplica tarefa vira ruído e o time desliga; importação que grava
lixo contamina a base para sempre. Os dois riscos estão cobertos aqui.
"""

from datetime import date

import pandas as pd
import pytest

import crm_backend
from automation_rules import RULES_CATALOG, evaluate_rules, summarize_proposals
from csv_import import IGNORE, analyze_import, guess_mapping, sample_csv

HOJE = date(2026, 8, 7)
ADMIN = {"username": "admin", "role": "admin", "full_name": "Admin Teste"}
MARKETING = {"username": "marketing", "role": "marketing", "full_name": "Mkt Teste"}


# ---------------------------------------------------------------------------
# Automações
# ---------------------------------------------------------------------------

class TestRegrasDeAutomacao:
    def test_negocio_parado_alem_do_limite_da_etapa_vira_tarefa(self):
        deals = pd.DataFrame([
            {"deal_id": "D-1", "customer_id": "C1", "name": "Alpha", "stage": "Proposta",
             "value": 50_000, "owner": "Rafael"},
        ])
        # Proposta tolera 10 dias; 30 dias de silêncio estoura.
        propostas = evaluate_rules(
            deals=deals, last_activity={"C1": "2026-07-08"}, today=HOJE,
            enabled={"negocio_parado"},
        )
        assert len(propostas) == 1
        assert propostas[0].task == "Retomar negociação parada — D-1"
        assert propostas[0].owner == "Rafael"
        assert "R$ 50 mil" in propostas[0].reason

    def test_negocio_dentro_do_limite_nao_gera_tarefa(self):
        deals = pd.DataFrame([
            {"deal_id": "D-1", "customer_id": "C1", "name": "Alpha", "stage": "Descoberta",
             "value": 10_000, "owner": "Rafael"},
        ])
        # Descoberta tolera 21 dias; 5 dias está saudável.
        propostas = evaluate_rules(
            deals=deals, last_activity={"C1": "2026-08-02"}, today=HOJE,
            enabled={"negocio_parado"},
        )
        assert propostas == []

    def test_negocio_ja_fechado_nunca_gera_tarefa(self):
        deals = pd.DataFrame([
            {"deal_id": "D-1", "customer_id": "C1", "name": "Alpha", "stage": "Fechado perdido",
             "value": 10_000, "owner": "Rafael"},
            {"deal_id": "D-2", "customer_id": "C1", "name": "Beta", "stage": "Fechado ganho",
             "value": 10_000, "owner": "Rafael"},
        ])
        propostas = evaluate_rules(
            deals=deals, last_activity={"C1": "2025-01-01"}, today=HOJE,
            enabled={"negocio_parado"},
        )
        assert propostas == []

    def test_ticket_fora_do_sla_vira_tarefa_critica(self):
        tickets = pd.DataFrame([
            {"ticket_id": "T-1", "subject": "Erro no portal", "status": "Em progresso",
             "age_hours": 9, "sla_hours": 4, "owner": "Amanda"},
            {"ticket_id": "T-2", "subject": "Dúvida", "status": "Novo",
             "age_hours": 1, "sla_hours": 8, "owner": "Amanda"},
        ])
        propostas = evaluate_rules(tickets=tickets, today=HOJE, enabled={"sla_em_risco"})
        assert len(propostas) == 1
        assert propostas[0].entity == "T-1"
        assert propostas[0].priority == "Critica"

    def test_ticket_resolvido_e_ignorado(self):
        tickets = pd.DataFrame([
            {"ticket_id": "T-1", "subject": "x", "status": "Resolvido",
             "age_hours": 99, "sla_hours": 4, "owner": "Amanda"},
        ])
        assert evaluate_rules(tickets=tickets, today=HOJE, enabled={"sla_em_risco"}) == []

    def test_conta_com_saude_baixa_vira_tarefa_de_retencao(self):
        customers = pd.DataFrame([
            {"customer_id": "C1", "name": "Ecoplus", "health_score": 42, "owner": "Camila", "status": "Ativo"},
            {"customer_id": "C2", "name": "Northwind", "health_score": 80, "owner": "Camila", "status": "Ativo"},
        ])
        propostas = evaluate_rules(customers=customers, today=HOJE, enabled={"conta_em_risco"})
        assert [p.entity for p in propostas] == ["C1"]

    def test_cliente_em_silencio_vira_tarefa_de_reativacao(self):
        customers = pd.DataFrame([
            {"customer_id": "C1", "name": "Ecoplus", "health_score": 80, "owner": "Camila", "status": "Ativo"},
        ])
        propostas = evaluate_rules(
            customers=customers, last_activity={"C1": "2026-01-01"}, today=HOJE,
            enabled={"cliente_sem_contato"},
        )
        assert len(propostas) == 1 and "Reativar" in propostas[0].task

    def test_regra_desligada_nao_roda(self):
        customers = pd.DataFrame([
            {"customer_id": "C1", "name": "X", "health_score": 10, "owner": "Camila", "status": "Ativo"},
        ])
        assert evaluate_rules(customers=customers, today=HOJE, enabled=set()) == []

    def test_sem_dados_nao_quebra(self):
        assert evaluate_rules() == []
        assert evaluate_rules(deals=pd.DataFrame(), tickets=None, customers=pd.DataFrame()) == []

    def test_resumo_conta_por_regra(self):
        customers = pd.DataFrame([
            {"customer_id": f"C{i}", "name": f"Conta {i}", "health_score": 10,
             "owner": "Camila", "status": "Ativo"}
            for i in range(3)
        ])
        propostas = evaluate_rules(customers=customers, today=HOJE, enabled={"conta_em_risco"})
        assert summarize_proposals(propostas) == {"conta_em_risco": 3}

    def test_catalogo_de_regras_esta_documentado(self):
        for regra in RULES_CATALOG:
            assert regra["id"] and regra["name"] and regra["description"]


class TestExecucaoDasAutomacoes:
    @pytest.fixture()
    def base(self):
        crm_backend.init_database()
        return crm_backend.get_data()

    def _propostas(self):
        customers = pd.DataFrame([
            {"customer_id": "C001", "name": "Conta Teste", "health_score": 20,
             "owner": "Camila Costa", "status": "Ativo"},
        ])
        return evaluate_rules(customers=customers, today=HOJE, enabled={"conta_em_risco"})

    def test_executar_cria_tarefa_de_verdade(self, base):
        resultado = crm_backend.run_automations(self._propostas(), actor=ADMIN)
        assert len(resultado["created"]) == 1

        tarefas = crm_backend.get_data()["tasks"]
        assert "Plano de retenção — C001" in set(tarefas["task"])

    def test_rodar_duas_vezes_nao_duplica(self, base):
        crm_backend.run_automations(self._propostas(), actor=ADMIN)
        segunda = crm_backend.run_automations(self._propostas(), actor=ADMIN)
        assert segunda["created"] == []
        assert len(segunda["skipped"]) == 1

        tarefas = crm_backend.get_data()["tasks"]
        iguais = [t for t in tarefas["task"] if t == "Plano de retenção — C001"]
        assert len(iguais) == 1, "automação duplicou tarefa"

    def test_perfil_sem_permissao_nao_executa(self, base):
        with pytest.raises(PermissionError):
            crm_backend.run_automations(self._propostas(), actor=MARKETING)

    def test_execucao_fica_na_auditoria(self, base):
        crm_backend.run_automations(self._propostas(), actor=ADMIN)
        auditoria = crm_backend.get_data()["audit_log"]
        assert (auditoria["action"] == "automation.run").any()


# ---------------------------------------------------------------------------
# Importação de planilha
# ---------------------------------------------------------------------------

class TestMapeamentoDeColunas:
    def test_reconhece_cabecalhos_comuns_em_portugues(self):
        mapa = guess_mapping(["Nome", "CNPJ", "Telefone", "Cidade", "Responsável"])
        assert mapa["name"] == "Nome"
        assert mapa["document"] == "CNPJ"
        assert mapa["phone"] == "Telefone"
        assert mapa["city"] == "Cidade"
        assert mapa["owner"] == "Responsável"

    def test_reconhece_cabecalhos_em_ingles_e_com_acento_ou_underscore(self):
        mapa = guess_mapping(["company", "cpf_cnpj", "owner"])
        assert mapa["document"] == "cpf_cnpj"
        assert mapa["owner"] == "owner"

    def test_coluna_desconhecida_fica_de_fora(self):
        mapa = guess_mapping(["Nome", "Coluna Estranha XYZ"])
        assert "Coluna Estranha XYZ" not in mapa.values()


class TestAnaliseDaPlanilha:
    def _frame(self):
        return pd.DataFrame([
            {"nome": "Padaria Boa", "documento": "11222333000181", "cidade": "Sao Paulo"},
            {"nome": "", "documento": "11222333000181", "cidade": "Rio"},          # sem nome
            {"nome": "Doc Ruim", "documento": "12345678000100", "cidade": "BH"},   # dígito inválido
            {"nome": "Sem Documento", "documento": "", "cidade": "Curitiba"},
        ])

    def _mapa(self):
        return {"name": "nome", "document": "documento", "city": "cidade"}

    def test_separa_validos_e_invalidos(self):
        rel = analyze_import(self._frame(), self._mapa())
        resumo = rel.summary()
        assert resumo["total"] == 4
        assert resumo["invalidos"] == 2   # sem nome + documento inválido
        assert resumo["validos"] == 2

    def test_linha_sem_nome_e_recusada_com_motivo(self):
        rel = analyze_import(self._frame(), self._mapa())
        motivos = " ".join(m for r in rel.invalid for m in r.errors)
        assert "Nome vazio" in motivos

    def test_documento_com_digito_invalido_e_recusado(self):
        rel = analyze_import(self._frame(), self._mapa())
        motivos = " ".join(m for r in rel.invalid for m in r.errors)
        assert "CNPJ inválido" in motivos

    def test_numero_da_linha_considera_o_cabecalho(self):
        rel = analyze_import(self._frame(), self._mapa())
        # primeira linha de dados é a linha 2 da planilha
        assert rel.rows[0].line == 2

    def test_cliente_ja_existente_e_marcado_e_nao_reimportado(self):
        existentes = pd.DataFrame([
            {"customer_id": "C001", "name": "Padaria Boa", "document": "11222333000181"},
        ])
        rel = analyze_import(self._frame(), self._mapa(), existing_customers=existentes)
        assert rel.summary()["duplicados"] == 1
        assert rel.duplicates[0].duplicate_of == "C001"
        # duplicado não entra na lista do que será criado
        assert all(r.duplicate_of is None for r in rel.valid)

    def test_documento_repetido_na_propria_planilha_e_barrado(self):
        frame = pd.DataFrame([
            {"nome": "Empresa A", "documento": "11222333000181"},
            {"nome": "Empresa B", "documento": "11.222.333/0001-81"},  # mesmo doc com máscara
        ])
        rel = analyze_import(frame, {"name": "nome", "document": "documento"})
        motivos = " ".join(m for r in rel.invalid for m in r.errors)
        assert "repetido na própria planilha" in motivos

    def test_documento_e_normalizado_para_digitos(self):
        frame = pd.DataFrame([{"nome": "Empresa A", "documento": "11.222.333/0001-81"}])
        rel = analyze_import(frame, {"name": "nome", "document": "documento"})
        assert rel.valid[0].data["document"] == "11222333000181"

    def test_padroes_preenchem_campos_ausentes(self):
        frame = pd.DataFrame([{"nome": "Só o Nome"}])
        rel = analyze_import(frame, {"name": "nome"}, defaults={"owner": "Camila", "country": "Brasil"})
        assert rel.valid[0].data["owner"] == "Camila"
        assert rel.valid[0].data["country"] == "Brasil"

    def test_coluna_marcada_para_ignorar_nao_e_lida(self):
        frame = pd.DataFrame([{"nome": "Empresa", "lixo": "não importa"}])
        rel = analyze_import(frame, {"name": "nome", "phone": IGNORE})
        assert "phone" not in rel.valid[0].data

    def test_planilha_modelo_e_valida_para_a_propria_importacao(self):
        import io

        frame = pd.read_csv(io.StringIO(sample_csv()), dtype=str, keep_default_na=False)
        rel = analyze_import(frame, guess_mapping(list(frame.columns)))
        assert rel.summary()["invalidos"] == 0, "o modelo que entregamos precisa passar na validação"
        assert rel.summary()["validos"] == 2


class TestGravacaoDaImportacao:
    def test_importa_em_lote_e_registra_auditoria(self):
        crm_backend.init_database()
        antes = len(crm_backend.get_data()["customers"])
        resultado = crm_backend.bulk_import_customers(
            [
                {"name": "Importado Um", "document": "11222333000181", "city": "Sao Paulo"},
                {"name": "Importado Dois", "phone": "11987654321"},
            ],
            actor=ADMIN,
        )
        assert len(resultado["created"]) == 2
        assert resultado["failed"] == []

        depois = crm_backend.get_data()
        assert len(depois["customers"]) == antes + 2
        assert (depois["audit_log"]["action"] == "customer.bulk_import").any()

    def test_campos_ausentes_recebem_padrao_seguro(self):
        crm_backend.init_database()
        crm_backend.bulk_import_customers([{"name": "Só Nome"}], actor=ADMIN)
        clientes = crm_backend.get_data()["customers"]
        criado = clientes[clientes["name"] == "Só Nome"].iloc[0]
        assert criado["country"] == "Brasil"
        assert criado["source"] == "Importacao CSV"
        assert criado["owner"]  # nunca vazio

    def test_perfil_sem_permissao_nao_importa(self):
        crm_backend.init_database()
        with pytest.raises(PermissionError):
            crm_backend.bulk_import_customers([{"name": "X"}], actor=MARKETING)
