"""Visões salvas por usuário.

Uma "visão" é um conjunto nomeado de filtros e ordenação — "Minhas propostas
paradas", "Fechamento deste mês" — que o usuário reaplica em um clique. É o
padrão central de navegação do Attio e do HubSpot pós-2026: sem ele, o operador
refaz o mesmo filtro toda sessão.

A persistência entra por injeção (``reader``/``writer``), o que mantém este
módulo testável sem banco e reaproveitável para qualquer backend de
preferências.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Sequence

# Chave usada em user_preferences, por módulo.
PREF_KEY_TEMPLATE = "saved_views::{module}"

# Guarda contra um usuário encher a barra lateral (e a linha do banco).
MAX_VIEWS_PER_MODULE = 20
MAX_NAME_LENGTH = 40

Reader = Callable[[str], str]
Writer = Callable[[str, str], None]


class SavedViewError(ValueError):
    """Erro de uso previsível, com mensagem pronta para o usuário."""


@dataclass(frozen=True)
class SavedView:
    name: str
    filters: dict[str, Any] = field(default_factory=dict)
    sort_column: str = ""
    sort_ascending: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "SavedView":
        return SavedView(
            name=str(data.get("name", "")).strip(),
            filters=dict(data.get("filters") or {}),
            sort_column=str(data.get("sort_column", "")),
            sort_ascending=bool(data.get("sort_ascending", True)),
        )

    @property
    def summary(self) -> str:
        """Descrição curta dos filtros, para exibir ao lado do nome."""
        active = {k: v for k, v in self.filters.items() if v not in (None, "", "Todos", [])}
        if not active:
            return "sem filtros"
        return " · ".join(f"{key}: {value}" for key, value in sorted(active.items()))


def normalize_name(name: str) -> str:
    """Normaliza o nome da visão e rejeita o que não dá para salvar."""
    cleaned = " ".join(str(name or "").split())
    if not cleaned:
        raise SavedViewError("Dê um nome à visão antes de salvar.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise SavedViewError(f"O nome da visão deve ter até {MAX_NAME_LENGTH} caracteres.")
    return cleaned


def _pref_key(module: str) -> str:
    return PREF_KEY_TEMPLATE.format(module=module)


def load_views(reader: Reader, module: str) -> list[SavedView]:
    """Lê as visões do módulo.

    Preferência corrompida ou em formato antigo não pode derrubar a tela:
    nesse caso trata como lista vazia.
    """
    raw = reader(_pref_key(module))
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(payload, list):
        return []

    views: list[SavedView] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        view = SavedView.from_dict(item)
        if view.name:
            views.append(view)
    return views


def _persist(writer: Writer, module: str, views: Sequence[SavedView]) -> None:
    writer(
        _pref_key(module),
        json.dumps([view.to_dict() for view in views], ensure_ascii=False),
    )


def save_view(
    reader: Reader,
    writer: Writer,
    module: str,
    name: str,
    filters: dict[str, Any],
    sort_column: str = "",
    sort_ascending: bool = True,
) -> list[SavedView]:
    """Cria ou substitui uma visão. Devolve a lista atualizada.

    Salvar com um nome existente sobrescreve — é o que o usuário espera de
    "salvar" e evita duas visões homônimas na lista.
    """
    clean_name = normalize_name(name)
    views = [v for v in load_views(reader, module) if v.name.lower() != clean_name.lower()]

    if len(views) >= MAX_VIEWS_PER_MODULE:
        raise SavedViewError(
            f"Limite de {MAX_VIEWS_PER_MODULE} visões por módulo. Apague uma antes de criar outra."
        )

    views.append(
        SavedView(
            name=clean_name,
            filters=dict(filters or {}),
            sort_column=sort_column,
            sort_ascending=sort_ascending,
        )
    )
    views.sort(key=lambda v: v.name.lower())
    _persist(writer, module, views)
    return views


def delete_view(reader: Reader, writer: Writer, module: str, name: str) -> list[SavedView]:
    """Remove uma visão pelo nome (case-insensitive)."""
    target = str(name or "").strip().lower()
    views = [v for v in load_views(reader, module) if v.name.lower() != target]
    _persist(writer, module, views)
    return views


def get_view(reader: Reader, module: str, name: str) -> SavedView | None:
    target = str(name or "").strip().lower()
    for view in load_views(reader, module):
        if view.name.lower() == target:
            return view
    return None


def apply_view_to_state(view: SavedView, state: dict[str, Any], allowed_keys: Sequence[str]) -> dict[str, Any]:
    """Aplica os filtros da visão ao estado da sessão.

    ``allowed_keys`` age como lista de permissão: uma preferência antiga com
    chaves que não existem mais não pode injetar lixo no estado da aplicação.
    """
    for key in allowed_keys:
        if key in view.filters:
            state[key] = view.filters[key]
    return state


def capture_filters(state: dict[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    """Extrai do estado só os filtros que compõem uma visão."""
    return {key: state[key] for key in keys if key in state}
