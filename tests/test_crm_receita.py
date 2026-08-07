"""Testes da consulta de CNPJ na Receita Federal.

Todos os testes usam HTTP injetado — a suíte não depende de rede nem da
disponibilidade da BrasilAPI. Há um teste de contrato marcado para rodar
apenas sob demanda, que valida o formato real da resposta.
"""

from datetime import date

import pytest

from crm_receita import (
    CompanyLookup,
    apply_lookup_to_form,
    lookup_cnpj,
    parse_company_payload,
)

# Resposta real da BrasilAPI, reduzida aos campos que o CRM usa.
PAYLOAD_REAL = {
    "cnpj": "19131243000197",
    "razao_social": "OPEN KNOWLEDGE BRASIL",
    "nome_fantasia": "REDE PELO CONHECIMENTO LIVRE",
    "descricao_situacao_cadastral": "ATIVA",
    "cnae_fiscal": 9430800,
    "cnae_fiscal_descricao": "Atividades de associações de defesa de direitos sociais",
    "logradouro": "PAULISTA 37",
    "numero": "37",
    "bairro": "BELA VISTA",
    "municipio": "SAO PAULO",
    "uf": "SP",
    "cep": "01311902",
    "ddd_telefone_1": "1123851939",
    "email": None,
    "porte": "DEMAIS",
    "data_inicio_atividade": "2013-10-03",
}

CNPJ_VALIDO = "19131243000197"


def _fetch_ok(url, timeout):
    return 200, PAYLOAD_REAL


def _fetch_status(code, payload=None):
    def _fetch(url, timeout):
        return code, payload or {}
    return _fetch


def _fetch_boom(url, timeout):
    raise TimeoutError("rede indisponível")


class TestTraducaoDaResposta:
    def test_mapeia_os_campos_do_crm(self):
        resultado = parse_company_payload(PAYLOAD_REAL, CNPJ_VALIDO)

        assert resultado.success is True
        assert resultado.razao_social == "OPEN KNOWLEDGE BRASIL"
        assert resultado.nome_fantasia == "REDE PELO CONHECIMENTO LIVRE"
        assert resultado.municipio == "SAO PAULO"
        assert resultado.uf == "SP"
        assert resultado.cnae_descricao.startswith("Atividades de associações")

    def test_formata_documento_telefone_e_cep(self):
        resultado = parse_company_payload(PAYLOAD_REAL, CNPJ_VALIDO)

        assert resultado.cnpj == "19.131.243/0001-97"
        assert resultado.telefone == "(11) 2385-1939"
        assert resultado.cep == "01311-902"

    def test_converte_a_data_de_abertura(self):
        assert parse_company_payload(PAYLOAD_REAL).abertura == date(2013, 10, 3)

    def test_campo_nulo_vira_string_vazia(self):
        # A API devolve None em vários campos; o formulário não pode exibir "None".
        assert parse_company_payload(PAYLOAD_REAL).email == ""

    def test_situacao_ativa(self):
        assert parse_company_payload(PAYLOAD_REAL).is_active is True

        baixada = dict(PAYLOAD_REAL, descricao_situacao_cadastral="BAIXADA")
        assert parse_company_payload(baixada).is_active is False

    def test_nome_preferido_cai_para_razao_social(self):
        sem_fantasia = dict(PAYLOAD_REAL, nome_fantasia="")
        assert parse_company_payload(sem_fantasia).display_name == "OPEN KNOWLEDGE BRASIL"

    def test_endereco_legivel(self):
        endereco = parse_company_payload(PAYLOAD_REAL).endereco
        assert "BELA VISTA" in endereco
        assert "SAO PAULO - SP" in endereco


class TestConsulta:
    def test_consulta_bem_sucedida(self):
        resultado = lookup_cnpj(CNPJ_VALIDO, fetch=_fetch_ok)
        assert resultado.success is True
        assert resultado.razao_social == "OPEN KNOWLEDGE BRASIL"

    def test_aceita_cnpj_com_mascara(self):
        resultado = lookup_cnpj("19.131.243/0001-97", fetch=_fetch_ok)
        assert resultado.success is True

    def test_cnpj_invalido_nao_chama_a_rede(self):
        chamadas = []

        def _espiao(url, timeout):
            chamadas.append(url)
            return 200, PAYLOAD_REAL

        resultado = lookup_cnpj("11222333000182", fetch=_espiao)

        assert resultado.success is False
        assert "inválido" in resultado.message
        assert chamadas == [], "não deve gastar chamada de rede com documento inválido"

    def test_cnpj_inexistente(self):
        resultado = lookup_cnpj(CNPJ_VALIDO, fetch=_fetch_status(404))
        assert resultado.success is False
        assert "não encontrado" in resultado.message

    def test_limite_de_requisicoes(self):
        resultado = lookup_cnpj(CNPJ_VALIDO, fetch=_fetch_status(429))
        assert resultado.success is False
        assert "Aguarde" in resultado.message

    def test_erro_do_servidor(self):
        resultado = lookup_cnpj(CNPJ_VALIDO, fetch=_fetch_status(500))
        assert resultado.success is False
        assert "manualmente" in resultado.message

    def test_resposta_vazia_conta_como_falha(self):
        resultado = lookup_cnpj(CNPJ_VALIDO, fetch=_fetch_status(200, {}))
        assert resultado.success is False

    def test_falha_de_rede_nao_levanta_excecao(self):
        # O cadastro manual precisa continuar possível com a API fora do ar.
        resultado = lookup_cnpj(CNPJ_VALIDO, fetch=_fetch_boom)
        assert isinstance(resultado, CompanyLookup)
        assert resultado.success is False
        assert "manualmente" in resultado.message

    def test_url_recebe_apenas_digitos(self):
        capturado = {}

        def _captura(url, timeout):
            capturado["url"] = url
            return 200, PAYLOAD_REAL

        lookup_cnpj("19.131.243/0001-97", fetch=_captura)
        assert capturado["url"].endswith("/19131243000197")


class TestPreenchimentoDoFormulario:
    def test_preenche_os_campos_do_cadastro(self):
        resultado = lookup_cnpj(CNPJ_VALIDO, fetch=_fetch_ok)
        campos = apply_lookup_to_form(resultado)

        assert campos["name"] == "REDE PELO CONHECIMENTO LIVRE"
        assert campos["document"] == "19.131.243/0001-97"
        assert campos["city"] == "SAO PAULO"

    def test_falha_nao_preenche_nada(self):
        campos = apply_lookup_to_form(lookup_cnpj(CNPJ_VALIDO, fetch=_fetch_boom))
        assert campos == {}

    def test_campo_vazio_da_api_nao_apaga_o_do_usuario(self):
        magro = dict(PAYLOAD_REAL, municipio="", cnae_fiscal_descricao="")
        campos = apply_lookup_to_form(parse_company_payload(magro, CNPJ_VALIDO))

        assert "city" not in campos
        assert "segment" not in campos
        assert campos["name"] == "REDE PELO CONHECIMENTO LIVRE"


@pytest.mark.contract
class TestContratoComAApiReal:
    """Valida que a BrasilAPI ainda devolve o formato esperado.

    Só roda sob demanda: `pytest -m contract`. Fica fora da suíte normal para
    que a CI não quebre por indisponibilidade de um serviço de terceiro.
    """

    def test_resposta_real_tem_os_campos_que_usamos(self):
        resultado = lookup_cnpj(CNPJ_VALIDO)

        if not resultado.success:
            pytest.skip(f"API indisponível: {resultado.message}")

        assert resultado.razao_social
        assert resultado.situacao
        assert resultado.municipio
        assert resultado.uf
