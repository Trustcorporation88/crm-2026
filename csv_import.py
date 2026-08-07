"""Importação de clientes por planilha (CSV).

Sem isso ninguém migra de outro CRM para o Trust — é o primeiro obstáculo de
adoção. O módulo é lógica pura: recebe um DataFrame já lido, adivinha o
mapeamento das colunas, valida linha a linha e devolve um relatório. Quem
grava é o backend, depois de o usuário conferir a prévia.

A regra de ouro: **nada é gravado pela metade**. A validação roda antes,
o usuário vê o que entra e o que foi recusado, e só então confirma.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from crm_ux import describe_document, only_digits

# Campos que a importação preenche. O primeiro sinônimo é o nome canônico.
FIELD_SYNONYMS: dict[str, list[str]] = {
    "name": ["nome", "name", "cliente", "razao social", "razao", "empresa", "conta"],
    "document": ["documento", "document", "cnpj", "cpf", "cpf/cnpj", "cpf cnpj", "doc"],
    "phone": ["telefone", "phone", "celular", "whatsapp", "fone", "contato"],
    "segment": ["segmento", "segment", "setor", "ramo", "industria"],
    "city": ["cidade", "city", "municipio"],
    "country": ["pais", "country", "mercado"],
    "owner": ["responsavel", "owner", "dono", "vendedor", "consultor"],
    "status": ["status", "situacao", "estagio"],
}

REQUIRED_FIELDS = ["name"]
IGNORE = "— ignorar —"


def _normalize_header(text: Any) -> str:
    base = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(base.lower().replace("_", " ").replace("-", " ").split())


def guess_mapping(columns: list[str]) -> dict[str, str]:
    """Adivinha coluna da planilha → campo do CRM, por sinônimo.

    Devolve {campo_do_crm: coluna_da_planilha}. Colunas não reconhecidas ficam
    de fora — o usuário ajusta na tela.
    """
    normalizadas = {col: _normalize_header(col) for col in columns}
    mapa: dict[str, str] = {}
    usadas: set[str] = set()
    for campo, sinonimos in FIELD_SYNONYMS.items():
        for sinonimo in sinonimos:
            for col, norm in normalizadas.items():
                if col in usadas:
                    continue
                if norm == sinonimo:
                    mapa[campo] = col
                    usadas.add(col)
                    break
            if campo in mapa:
                break
    return mapa


@dataclass
class ImportRow:
    """Uma linha analisada: pronta para gravar ou recusada com motivo."""

    line: int
    data: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_of: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ImportReport:
    rows: list[ImportRow]

    @property
    def valid(self) -> list[ImportRow]:
        return [r for r in self.rows if r.ok and not r.duplicate_of]

    @property
    def duplicates(self) -> list[ImportRow]:
        return [r for r in self.rows if r.ok and r.duplicate_of]

    @property
    def invalid(self) -> list[ImportRow]:
        return [r for r in self.rows if not r.ok]

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self.rows),
            "validos": len(self.valid),
            "duplicados": len(self.duplicates),
            "invalidos": len(self.invalid),
        }


def analyze_import(
    frame: pd.DataFrame,
    mapping: dict[str, str],
    existing_customers: pd.DataFrame | None = None,
    defaults: dict[str, Any] | None = None,
) -> ImportReport:
    """Valida a planilha contra as regras do CRM, sem gravar nada.

    Recusa linha sem nome e documento com dígito verificador inválido. Marca
    (sem recusar) quem já existe na base por documento ou nome — duplicado é
    decisão do usuário, não erro.
    """
    defaults = defaults or {}
    rows: list[ImportRow] = []

    docs_existentes: dict[str, str] = {}
    nomes_existentes: dict[str, str] = {}
    if existing_customers is not None and not existing_customers.empty:
        for registro in existing_customers.to_dict("records"):
            doc = only_digits(registro.get("document", ""))
            if doc:
                docs_existentes[doc] = str(registro.get("customer_id", ""))
            nome = _normalize_header(registro.get("name", ""))
            if nome:
                nomes_existentes[nome] = str(registro.get("customer_id", ""))

    vistos_no_arquivo: dict[str, int] = {}

    for indice, registro in enumerate(frame.to_dict("records"), start=2):  # 1 = cabeçalho
        dados: dict[str, Any] = {}
        for campo, coluna in mapping.items():
            if not coluna or coluna == IGNORE or coluna not in frame.columns:
                continue
            valor = registro.get(coluna)
            if valor is None or (isinstance(valor, float) and pd.isna(valor)):
                valor = ""
            dados[campo] = str(valor).strip()

        linha = ImportRow(line=indice, data=dados)

        nome = dados.get("name", "").strip()
        if not nome:
            linha.errors.append("Nome vazio")

        documento = dados.get("document", "").strip()
        if documento:
            valido, mensagem = describe_document(documento)
            if not valido:
                linha.errors.append(mensagem)
            else:
                digitos = only_digits(documento)
                dados["document"] = digitos
                if digitos in vistos_no_arquivo:
                    linha.errors.append(
                        f"Documento repetido na própria planilha (linha {vistos_no_arquivo[digitos]})"
                    )
                else:
                    vistos_no_arquivo[digitos] = indice
                if digitos in docs_existentes:
                    linha.duplicate_of = docs_existentes[digitos]
                    linha.warnings.append("Já existe cliente com este documento")

        if linha.duplicate_of is None and nome:
            chave = _normalize_header(nome)
            if chave in nomes_existentes:
                linha.duplicate_of = nomes_existentes[chave]
                linha.warnings.append("Já existe cliente com este nome")

        # Preenche o que a planilha não trouxe com os padrões da tela.
        for campo, valor_padrao in defaults.items():
            if not dados.get(campo):
                dados[campo] = valor_padrao

        rows.append(linha)

    return ImportReport(rows=rows)


def sample_csv() -> str:
    """Modelo de planilha para download — evita o usuário adivinhar o formato."""
    return (
        "nome,documento,telefone,segmento,cidade,pais,responsavel,status\n"
        "Padaria do Bairro Ltda,11222333000181,(11) 98765-4321,Alimentacao,Sao Paulo,Brasil,Rafael Nogueira,Ativo\n"
        "Clinica Vida Plena,12345678000195,(21) 3344-5566,Saude,Rio de Janeiro,Brasil,Camila Costa,Novo\n"
    )
