"""Testes do WhatsApp por link (wa.me) e da fila de execução de tarefas."""

from datetime import date

import pandas as pd
import pytest

from crm_ux import (
    DayAgenda,
    account_summary_text,
    build_day_agenda,
    build_task_queue,
    fill_message_template,
    normalize_phone_br,
    queue_position_label,
    whatsapp_link,
)

HOJE = date(2026, 8, 7)


class TestTelefoneBrasileiro:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("(11) 98765-4321", "5511987654321"),
            ("11987654321", "5511987654321"),
            ("+55 11 98765-4321", "5511987654321"),
            ("55 11 98765 4321", "5511987654321"),
            ("011 98765-4321", "5511987654321"),   # zero de discagem
            ("(11) 3456-7890", "551134567890"),    # fixo
        ],
    )
    def test_normaliza_formatos_comuns(self, entrada, esperado):
        assert normalize_phone_br(entrada) == esperado

    @pytest.mark.parametrize("invalido", ["123", "", None, "9 8765"])
    def test_numero_inutilizavel_vira_vazio(self, invalido):
        # Número errado abriria conversa com um desconhecido.
        assert normalize_phone_br(invalido) == ""


class TestLinkWhatsApp:
    def test_link_com_mensagem_codificada(self):
        link = whatsapp_link("(11) 98765-4321", "Olá João!")
        assert link == "https://wa.me/5511987654321?text=Ol%C3%A1%20Jo%C3%A3o%21"

    def test_link_sem_mensagem(self):
        assert whatsapp_link("11987654321") == "https://wa.me/5511987654321"

    def test_telefone_invalido_nao_gera_link(self):
        assert whatsapp_link("123", "Oi") == ""


class TestModeloDeMensagem:
    def test_preenche_os_campos(self):
        cliente = {"name": "Ecoplus", "owner": "Camila", "city": "SP"}
        texto = fill_message_template("Olá, {nome}! Sou {responsavel}.", cliente)
        assert texto == "Olá, Ecoplus! Sou Camila."

    def test_remetente_explicito_vence_o_owner(self):
        cliente = {"name": "Ecoplus", "owner": "Camila"}
        texto = fill_message_template("{responsavel}", cliente, sender="Rafael")
        assert texto == "Rafael"


class TestResumoDaConta:
    def test_resumo_traz_conta_negociacoes_e_chamados(self):
        cliente = {
            "name": "Açaí & Cia", "segment": "Alimentação", "city": "São Paulo",
            "country": "Brasil", "owner": "Camila", "health_score": 82,
            "document": "11222333000181",
        }
        deals = pd.DataFrame([
            {"name": "Expansão", "value": 104000, "stage": "Negociacao", "close_date": "2026-09-30"},
        ])
        tickets = pd.DataFrame([{"subject": "Portal", "status": "Aberto"}])

        texto = account_summary_text(cliente, deals, tickets, (), today=HOJE)

        assert "Açaí & Cia" in texto
        assert "R$ 104.000" in texto            # moeda pt-BR
        assert "30/09/2026" in texto            # data pt-BR
        assert "11.222.333/0001-81" in texto    # documento mascarado
        assert "Portal" in texto
        assert "07/08/2026" in texto            # data de geração

    def test_conta_vazia_nao_quebra(self):
        texto = account_summary_text({"name": "Nova"}, None, None, (), today=HOJE)
        assert "Nenhuma negociação" in texto
        assert "Nenhum chamado" in texto


class TestFilaDeExecucao:
    def _agenda(self):
        tasks = pd.DataFrame([
            {"task": "Muito atrasada", "owner": "A", "due_date": "2026-07-01", "priority": "Alta", "status": "aberta"},
            {"task": "Pouco atrasada", "owner": "A", "due_date": "2026-08-05", "priority": "Media", "status": "aberta"},
            {"task": "De hoje", "owner": "A", "due_date": "2026-08-07", "priority": "Alta", "status": "aberta"},
        ])
        return build_day_agenda(tasks, None, None, None, owner="A", today=HOJE)

    def test_fila_ordena_atrasadas_primeiro(self):
        fila = build_task_queue(self._agenda())
        assert [t["task"] for t in fila] == ["Muito atrasada", "Pouco atrasada", "De hoje"]

    def test_fila_marca_a_origem(self):
        fila = build_task_queue(self._agenda())
        assert fila[0]["_origem"] == "atrasada"
        assert fila[-1]["_origem"] == "hoje"

    def test_tarefa_concluida_sai_da_agenda(self):
        tasks = pd.DataFrame([
            {"task": "Feita", "owner": "A", "due_date": "2026-07-01", "priority": "Alta", "status": "concluida"},
            {"task": "Pendente", "owner": "A", "due_date": "2026-07-01", "priority": "Alta", "status": "aberta"},
        ])
        agenda = build_day_agenda(tasks, None, None, None, owner="A", today=HOJE)
        assert [t["task"] for t in build_task_queue(agenda)] == ["Pendente"]

    def test_rotulo_de_progresso(self):
        assert queue_position_label(0, 3) == "Tarefa 1 de 3"
        assert queue_position_label(2, 3) == "Tarefa 3 de 3"
        assert queue_position_label(9, 3) == "Tarefa 3 de 3"  # à prova de estouro
        assert queue_position_label(0, 0) == "Fila vazia"

    def test_fila_vazia(self):
        assert build_task_queue(DayAgenda()) == []


class TestConclusaoNoBanco:
    def test_concluir_tarefa_persiste(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("CRM_DATA_DIR", str(tmp_path))

        import importlib
        import crm_backend

        importlib.reload(crm_backend)
        crm_backend.init_database()

        nome = crm_backend.get_data()["tasks"].iloc[0]["task"]
        assert crm_backend.complete_task(nome, actor={"username": "admin", "role": "admin"}) is True

        tasks = crm_backend.get_data()["tasks"]
        linha = tasks[tasks["task"] == nome].iloc[0]
        assert linha["status"] == "concluida"

    def test_concluir_inexistente_devolve_false(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("CRM_DATA_DIR", str(tmp_path))

        import importlib
        import crm_backend

        importlib.reload(crm_backend)
        crm_backend.init_database()
        assert crm_backend.complete_task("tarefa-fantasma") is False
