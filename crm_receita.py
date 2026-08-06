"""Consulta de CNPJ na base pública da Receita Federal.

Auto-preenchimento por CNPJ é expectativa básica de CRM B2B no Brasil: o
usuário digita o documento e os dados cadastrais chegam prontos, em vez de
serem copiados à mão do site da Receita.

Usa a BrasilAPI (https://brasilapi.com.br), que é gratuita e não exige chave.
Todo o acesso à rede está isolado aqui e é sempre tolerante a falha: uma
indisponibilidade da API **nunca** pode impedir o cadastro manual — degrada
para preenchimento à mão, nunca para tela travada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from crm_ux import format_cpf_cnpj, only_digits, parse_date, validate_cnpj

# Endpoint sobrescrevível para apontar a um provedor próprio ou a um mock.
BRASILAPI_URL = os.getenv(
    "CRM_CNPJ_API_URL",
    "https://brasilapi.com.br/api/cnpj/v1/{cnpj}",
)

# A consulta acontece com o usuário esperando na tela: melhor falhar rápido e
# deixar ele digitar do que segurar o formulário.
REQUEST_TIMEOUT_SECONDS = float(os.getenv("CRM_CNPJ_API_TIMEOUT", "6"))


@dataclass(frozen=True)
class CompanyLookup:
    """Resultado de uma consulta de CNPJ."""

    success: bool
    message: str
    cnpj: str = ""
    razao_social: str = ""
    nome_fantasia: str = ""
    situacao: str = ""
    cnae_codigo: str = ""
    cnae_descricao: str = ""
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    municipio: str = ""
    uf: str = ""
    cep: str = ""
    telefone: str = ""
    email: str = ""
    porte: str = ""
    abertura: date | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Situação cadastral ativa na Receita."""
        return self.situacao.strip().upper() == "ATIVA"

    @property
    def display_name(self) -> str:
        """Nome preferido para o cadastro: fantasia quando existe."""
        return self.nome_fantasia.strip() or self.razao_social.strip()

    @property
    def endereco(self) -> str:
        partes = [self.logradouro, self.numero, self.bairro]
        rua = ", ".join(p for p in partes if p)
        cidade = " - ".join(p for p in [self.municipio, self.uf] if p)
        return " · ".join(p for p in [rua, cidade] if p)


def _clean(value: Any) -> str:
    """Normaliza campo textual da API, que às vezes vem None ou vazio."""
    if value is None:
        return ""
    return str(value).strip()


def _format_phone(raw: Any) -> str:
    """Formata o telefone que a Receita devolve como dígitos colados."""
    digits = only_digits(raw)
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return digits


def _format_cep(raw: Any) -> str:
    digits = only_digits(raw)
    return f"{digits[:5]}-{digits[5:]}" if len(digits) == 8 else digits


def parse_company_payload(payload: dict[str, Any], cnpj: str = "") -> CompanyLookup:
    """Traduz a resposta da API para os campos do CRM.

    Fica separado da chamada HTTP para ser testável sem rede.
    """
    return CompanyLookup(
        success=True,
        message="Dados encontrados na Receita Federal.",
        cnpj=format_cpf_cnpj(cnpj or payload.get("cnpj", "")),
        razao_social=_clean(payload.get("razao_social")),
        nome_fantasia=_clean(payload.get("nome_fantasia")),
        situacao=_clean(payload.get("descricao_situacao_cadastral")),
        cnae_codigo=_clean(payload.get("cnae_fiscal")),
        cnae_descricao=_clean(payload.get("cnae_fiscal_descricao")),
        logradouro=_clean(payload.get("logradouro")),
        numero=_clean(payload.get("numero")),
        bairro=_clean(payload.get("bairro")),
        municipio=_clean(payload.get("municipio")),
        uf=_clean(payload.get("uf")),
        cep=_format_cep(payload.get("cep")),
        telefone=_format_phone(payload.get("ddd_telefone_1")),
        email=_clean(payload.get("email")),
        porte=_clean(payload.get("porte")),
        abertura=parse_date(payload.get("data_inicio_atividade")),
        raw=payload,
    )


def _default_fetch(url: str, timeout: float) -> tuple[int, dict[str, Any]]:
    """Executa o GET. Isolado para permitir injeção nos testes."""
    import json
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "TrustCRM/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def lookup_cnpj(
    cnpj: str,
    fetch: Callable[[str, float], tuple[int, dict[str, Any]]] | None = None,
    timeout: float | None = None,
) -> CompanyLookup:
    """Consulta o CNPJ e devolve os dados cadastrais.

    Nunca levanta exceção: qualquer falha vira um ``CompanyLookup`` com
    ``success=False`` e uma mensagem para o usuário. O cadastro manual precisa
    continuar possível mesmo com a Receita fora do ar.
    """
    digits = only_digits(cnpj)

    # Valida o dígito verificador antes de gastar uma chamada de rede.
    if not validate_cnpj(digits):
        return CompanyLookup(False, "CNPJ inválido — confira os dígitos antes de consultar.")

    fetch = fetch or _default_fetch
    url = BRASILAPI_URL.format(cnpj=digits)

    try:
        status, payload = fetch(url, timeout or REQUEST_TIMEOUT_SECONDS)
    except Exception:
        # Timeout, DNS, TLS, JSON malformado — o usuário só precisa saber que
        # deve preencher à mão.
        return CompanyLookup(
            False,
            "Não foi possível consultar a Receita agora. Preencha os dados manualmente.",
        )

    if status == 404:
        return CompanyLookup(False, "CNPJ não encontrado na base da Receita Federal.")
    if status == 429:
        return CompanyLookup(False, "Muitas consultas seguidas. Aguarde alguns segundos e tente de novo.")
    if status != 200 or not payload:
        return CompanyLookup(
            False,
            "A consulta à Receita falhou. Preencha os dados manualmente.",
        )

    return parse_company_payload(payload, digits)


def apply_lookup_to_form(lookup: CompanyLookup) -> dict[str, str]:
    """Converte o resultado nos campos do formulário de cliente.

    Só devolve o que veio preenchido: sobrescrever campo do usuário com string
    vazia da API seria apagar trabalho dele.
    """
    if not lookup.success:
        return {}

    candidates = {
        "name": lookup.display_name,
        "document": lookup.cnpj,
        "segment": lookup.cnae_descricao,
        "city": lookup.municipio,
    }
    return {key: value for key, value in candidates.items() if value}
