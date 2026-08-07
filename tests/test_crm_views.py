"""Testes de visões salvas e de campos obrigatórios por etapa."""

import json

import pytest

from crm_ux import can_advance_to_stage, missing_fields_for_stage
from crm_views import (
    MAX_VIEWS_PER_MODULE,
    SavedView,
    SavedViewError,
    apply_view_to_state,
    capture_filters,
    delete_view,
    get_view,
    load_views,
    normalize_name,
    save_view,
)


@pytest.fixture
def store():
    """Preferências em memória, com a mesma interface do backend real."""
    data: dict[str, str] = {}

    def reader(key: str) -> str:
        return data.get(key, "")

    def writer(key: str, value: str) -> None:
        data[key] = value

    return data, reader, writer


class TestNomeDaVisao:
    def test_normaliza_espacos(self):
        assert normalize_name("  Minhas   propostas  ") == "Minhas propostas"

    def test_nome_vazio_e_rejeitado(self):
        with pytest.raises(SavedViewError, match="nome"):
            normalize_name("   ")

    def test_nome_longo_demais_e_rejeitado(self):
        with pytest.raises(SavedViewError, match="caracteres"):
            normalize_name("x" * 41)


class TestCicloDeVida:
    def test_salvar_e_recarregar(self, store):
        _, reader, writer = store
        save_view(reader, writer, "funil", "Minhas propostas", {"owner": "Camila"})

        views = load_views(reader, "funil")
        assert len(views) == 1
        assert views[0].name == "Minhas propostas"
        assert views[0].filters == {"owner": "Camila"}

    def test_persiste_como_json_valido(self, store):
        data, reader, writer = store
        save_view(reader, writer, "funil", "Teste", {"owner": "X"})

        bruto = data["saved_views::funil"]
        assert isinstance(json.loads(bruto), list)

    def test_mesmo_nome_substitui_em_vez_de_duplicar(self, store):
        _, reader, writer = store
        save_view(reader, writer, "funil", "Semana", {"owner": "Camila"})
        save_view(reader, writer, "funil", "semana", {"owner": "Rafael"})

        views = load_views(reader, "funil")
        assert len(views) == 1, "salvar com nome existente deve sobrescrever"
        assert views[0].filters == {"owner": "Rafael"}

    def test_modulos_sao_independentes(self, store):
        _, reader, writer = store
        save_view(reader, writer, "funil", "A", {"owner": "X"})
        save_view(reader, writer, "clientes", "B", {"country": "Brasil"})

        assert [v.name for v in load_views(reader, "funil")] == ["A"]
        assert [v.name for v in load_views(reader, "clientes")] == ["B"]

    def test_remover_visao(self, store):
        _, reader, writer = store
        save_view(reader, writer, "funil", "A", {})
        save_view(reader, writer, "funil", "B", {})

        delete_view(reader, writer, "funil", "a")  # case-insensitive
        assert [v.name for v in load_views(reader, "funil")] == ["B"]

    def test_remover_inexistente_nao_quebra(self, store):
        _, reader, writer = store
        save_view(reader, writer, "funil", "A", {})
        assert len(delete_view(reader, writer, "funil", "fantasma")) == 1

    def test_busca_por_nome(self, store):
        _, reader, writer = store
        save_view(reader, writer, "funil", "Fechamento do mês", {"stage": "Proposta"})

        assert get_view(reader, "funil", "fechamento do mês").filters == {"stage": "Proposta"}
        assert get_view(reader, "funil", "não existe") is None

    def test_lista_ordenada_por_nome(self, store):
        _, reader, writer = store
        for nome in ["Zulu", "alfa", "Meio"]:
            save_view(reader, writer, "funil", nome, {})

        assert [v.name for v in load_views(reader, "funil")] == ["alfa", "Meio", "Zulu"]

    def test_limite_por_modulo(self, store):
        _, reader, writer = store
        for i in range(MAX_VIEWS_PER_MODULE):
            save_view(reader, writer, "funil", f"Visao {i:02d}", {})

        with pytest.raises(SavedViewError, match="Limite"):
            save_view(reader, writer, "funil", "Uma a mais", {})


class TestResilienciaDoArmazenamento:
    """Preferência corrompida não pode derrubar a tela."""

    def test_json_invalido_vira_lista_vazia(self):
        assert load_views(lambda key: "{isso não é json", "funil") == []

    def test_json_de_tipo_errado_vira_lista_vazia(self):
        assert load_views(lambda key: '{"nao":"e-lista"}', "funil") == []

    def test_item_sem_nome_e_descartado(self):
        bruto = json.dumps([{"filters": {"a": 1}}, {"name": "Boa", "filters": {}}])
        views = load_views(lambda key: bruto, "funil")
        assert [v.name for v in views] == ["Boa"]

    def test_preferencia_ausente(self):
        assert load_views(lambda key: "", "funil") == []


class TestAplicacaoNoEstado:
    def test_aplica_apenas_chaves_permitidas(self):
        view = SavedView(name="V", filters={"filter_owner": "Camila", "chave_maliciosa": "x"})
        estado = {"filter_owner": "Todos"}

        apply_view_to_state(view, estado, allowed_keys=["filter_owner", "filter_country"])

        assert estado["filter_owner"] == "Camila"
        assert "chave_maliciosa" not in estado, "chave fora da lista de permissão não entra no estado"

    def test_captura_somente_os_filtros_declarados(self):
        estado = {"filter_owner": "Camila", "filter_country": "Brasil", "irrelevante": 1}
        assert capture_filters(estado, ["filter_owner", "filter_country"]) == {
            "filter_owner": "Camila",
            "filter_country": "Brasil",
        }

    def test_resumo_legivel(self):
        assert SavedView("V", {"owner": "Camila", "country": "Todos"}).summary == "owner: Camila"
        assert SavedView("V", {"owner": "Todos"}).summary == "sem filtros"


class TestPortaoDeEtapa:
    """Campos obrigatórios cobrados no avanço da negociação."""

    NEGOCIACAO_COMPLETA = {
        "value": 68000,
        "close_date": "2026-09-30",
        "probability": 65,
        "owner": "Camila Costa",
    }

    def test_negociacao_completa_avanca(self):
        ok, msg = can_advance_to_stage(self.NEGOCIACAO_COMPLETA, "Negociacao")
        assert ok is True
        assert msg == ""

    def test_campo_faltando_bloqueia(self):
        incompleta = dict(self.NEGOCIACAO_COMPLETA, close_date="")
        ok, msg = can_advance_to_stage(incompleta, "Proposta")

        assert ok is False
        assert "Fechamento previsto" in msg

    def test_valor_zero_conta_como_ausente(self):
        # Proposta de R$ 0 é dado faltando, não valor legítimo.
        incompleta = dict(self.NEGOCIACAO_COMPLETA, value=0)
        assert missing_fields_for_stage(incompleta, "Proposta") == ["value"]

    def test_mensagem_lista_varios_campos_em_portugues(self):
        vazia = {"value": None, "close_date": "", "probability": 0}
        ok, msg = can_advance_to_stage(vazia, "Negociacao")

        assert ok is False
        assert "Valor" in msg and "Fechamento previsto" in msg and "Probabilidade" in msg
        assert " e " in msg, "a mensagem deve ler como frase, não como lista técnica"

    def test_etapa_inicial_nao_exige_nada(self):
        assert can_advance_to_stage({}, "Descoberta") == (True, "")

    def test_etapa_desconhecida_nao_bloqueia(self):
        assert can_advance_to_stage({}, "Etapa Personalizada")[0] is True

    def test_exigencias_configuraveis(self):
        regras = {"Descoberta": ["owner"]}
        ok, msg = can_advance_to_stage({}, "Descoberta", requirements=regras)
        assert ok is False
        assert "Responsável" in msg
