"""Agente de pesquisa de lead: só grava fato confirmado, com fonte.

Inspirado no princípio do trycompai/crm ("um fato confiante e errado sobre
um cliente é pior que um campo vazio"): dado um lead, pesquisa na web
(Serper.dev) e pede à IA para extrair *apenas* o que está claramente escrito
nos resultados, cada afirmação com a fonte que a sustenta. Se nada for
confirmável, o resultado é "não encontrado" — nunca um palpite disfarçado
de fato.

Não decide nada sozinho: quem chama (webhook ou botão na UI) decide quando
rodar e o que fazer com o resultado. Este módulo só pesquisa e registra.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from deepseek_assistant import chat_completion, deepseek_configured

SERPER_API_URL = "https://google.serper.dev/search"
SERPER_TIMEOUT = 20.0
MAX_RESULTS = 8


def serper_configured() -> bool:
    return bool(os.getenv("SERPER_API_KEY", "").strip())


def build_search_query(name: str, instagram_handle: str | None, extra_context: str | None) -> str:
    parts = [name.strip()] if name.strip() else []
    if instagram_handle:
        parts.append(f"instagram {instagram_handle.lstrip('@')}")
    if extra_context:
        parts.append(extra_context.strip())
    return " ".join(p for p in parts if p).strip()


def serper_search(query: str, num: int = MAX_RESULTS) -> tuple[list[dict[str, str]], str | None]:
    """Busca na web via Serper.dev. Retorna (resultados, erro)."""
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        return [], "SERPER_API_KEY não configurada."
    try:
        response = httpx.post(
            SERPER_API_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": num, "gl": "br", "hl": "pt-br"},
            timeout=SERPER_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:200] if exc.response is not None else str(exc)
        return [], f"Erro HTTP Serper ({exc.response.status_code}): {detail}"
    except Exception as exc:
        return [], f"Falha ao consultar Serper: {exc}"

    resultados: list[dict[str, str]] = []
    for item in (data.get("organic") or [])[:num]:
        title = str(item.get("title", "")).strip()
        link = str(item.get("link", "")).strip()
        snippet = str(item.get("snippet", "")).strip()
        if title and link:
            resultados.append({"title": title, "link": link, "snippet": snippet})
    return resultados, None


def _build_extraction_prompt(name: str, search_results: list[dict[str, str]]) -> tuple[str, str]:
    numbered = "\n\n".join(
        f"[{i}] {r['title']}\nURL: {r['link']}\nTrecho: {r['snippet'] or '(sem trecho)'}"
        for i, r in enumerate(search_results, start=1)
    )
    system_prompt = (
        "Você é um pesquisador que só registra fato confirmado, nunca palpite. "
        "Vai receber resultados de busca sobre uma pessoa e deve extrair só o que está "
        "EXPLICITAMENTE escrito nos trechos, nunca inferir, combinar ou completar "
        "informação parcial. Se um trecho só sugere algo sem confirmar, isso NÃO é fato. "
        "Se nada nos resultados for confiável ou relevante sobre essa pessoa específica, "
        "devolva a lista vazia — não force uma resposta.\n\n"
        "Responda em JSON puro, neste formato exato:\n"
        '{"facts": [{"fact": "frase curta e objetiva em português", "source_index": 1}]}\n\n'
        "source_index é o número entre colchetes do resultado que sustenta o fato. "
        "Cada fato precisa de exatamente uma fonte. Não invente números de fonte."
    )
    user_prompt = (
        f"Pessoa/perfil pesquisado: {name}\n\n"
        f"Resultados da busca:\n\n{numbered}\n\n"
        "Extraia os fatos confirmados, no formato JSON pedido."
    )
    return system_prompt, user_prompt


def research_lead(
    customer_id: str,
    name: str,
    instagram_handle: str | None = None,
    extra_context: str | None = None,
) -> dict[str, Any]:
    """Pesquisa um lead e grava o resultado (fatos ou "nada encontrado").

    Retorna um dict pronto para a UI: status, query usada, fatos e erro (se
    houver). A gravação em banco acontece aqui dentro — quem chama não
    precisa saber de crm_backend.
    """
    # Import tardio: evita ciclo entre lead_research e crm_backend em módulos
    # que importam os dois na ordem inversa.
    from crm_backend import save_lead_research_run

    query = build_search_query(name, instagram_handle, extra_context)
    if not query:
        return {"status": "erro", "query": "", "facts": [], "error": "Nome do lead vazio."}

    if not serper_configured():
        error = "SERPER_API_KEY não configurada — o agente não tem como pesquisar a web."
        save_lead_research_run(customer_id, query, [], error_message=error)
        return {"status": "erro", "query": query, "facts": [], "error": error}

    if not deepseek_configured():
        error = "DEEPSEEK_API_KEY não configurada — sem IA para interpretar os resultados."
        save_lead_research_run(customer_id, query, [], error_message=error)
        return {"status": "erro", "query": query, "facts": [], "error": error}

    search_results, search_error = serper_search(query)
    if search_error:
        save_lead_research_run(customer_id, query, [], error_message=search_error)
        return {"status": "erro", "query": query, "facts": [], "error": search_error}

    if not search_results:
        save_lead_research_run(customer_id, query, [])
        return {"status": "sem_fatos", "query": query, "facts": [], "error": None}

    system_prompt, user_prompt = _build_extraction_prompt(name, search_results)
    raw_response, ai_error = chat_completion(
        [{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.0,
        json_mode=True,
    )
    if ai_error:
        save_lead_research_run(customer_id, query, [], error_message=ai_error)
        return {"status": "erro", "query": query, "facts": [], "error": ai_error}

    try:
        parsed = json.loads(raw_response or "{}")
        raw_facts = parsed.get("facts", [])
        if not isinstance(raw_facts, list):
            raise ValueError("campo 'facts' não é uma lista")
    except Exception as exc:
        error = f"Resposta da IA não veio no formato esperado: {exc}"
        save_lead_research_run(customer_id, query, [], error_message=error)
        return {"status": "erro", "query": query, "facts": [], "error": error}

    facts: list[dict[str, str]] = []
    for item in raw_facts:
        if not isinstance(item, dict):
            continue
        fact_text = str(item.get("fact", "")).strip()
        source_index = item.get("source_index")
        if not fact_text or not isinstance(source_index, int):
            continue
        if not (1 <= source_index <= len(search_results)):
            continue
        source = search_results[source_index - 1]
        facts.append(
            {
                "fact": fact_text,
                "source_url": source["link"],
                "source_title": source["title"],
            }
        )

    save_lead_research_run(customer_id, query, facts)
    status = "com_fatos" if facts else "sem_fatos"
    return {"status": status, "query": query, "facts": facts, "error": None}
