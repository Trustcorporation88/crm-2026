"""Assistente de dúvidas via DeepSeek API."""
from __future__ import annotations

import os
from typing import Any

import httpx

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def deepseek_configured() -> bool:
    return bool(os.getenv("DEEPSEEK_API_KEY", "").strip())


def _api_key() -> str:
    return os.getenv("DEEPSEEK_API_KEY", "").strip()


def build_service_system_prompt(service: dict[str, Any]) -> str:
    dados = ", ".join(service.get("dados_input") or service.get("inputs") or [])
    passos = "; ".join(service.get("como_usar") or service.get("steps") or [])
    return (
        "Você é o assistente do CRM Mr.Holmes (Trust Corporation). "
        f"Responda apenas sobre o serviço «{service.get('title', 'CRM')}».\n\n"
        f"Categoria: {service.get('category', '')}\n"
        f"Objetivo: {service.get('objetivo') or service.get('tagline', '')}\n"
        f"Resumo geral: {service.get('resumo_geral') or service.get('description', '')}\n"
        f"Resultado esperado: {service.get('resultado_esperado') or service.get('outcome', '')}\n"
        f"Dados de entrada: {dados}\n"
        f"Como usar: {passos}\n\n"
        "Responda em português do Brasil, com passos práticos. "
        "Se não souber algo fora deste serviço, diga e sugira o módulo correto do CRM."
    )


def build_general_system_prompt() -> str:
    return (
        "Você é o assistente do CRM Mr.Holmes (Trust Corporation). "
        "Ajude com navegação, conceitos de CRM, atendimento, vendas e marketing. "
        "Os módulos principais são: Atendimento, Clientes 360, Funil Comercial, Canais, "
        "Cadências, Saúde da Conta, Modelos de Mensagem, Marketing, Qualificação de Leads e Administração. "
        "Responda em português do Brasil de forma clara e objetiva."
    )


def chat_completion(
    messages: list[dict[str, str]],
    *,
    system_prompt: str | None = None,
    temperature: float = 0.4,
) -> tuple[str | None, str | None]:
    """
    Retorna (texto_resposta, erro).
    erro é None em sucesso.
    """
    key = _api_key()
    if not key:
        return None, (
            "API DeepSeek não configurada. Defina DEEPSEEK_API_KEY nas variáveis de ambiente do Render."
        )

    payload_messages: list[dict[str, str]] = []
    if system_prompt:
        payload_messages.append({"role": "system", "content": system_prompt})
    payload_messages.extend(messages)

    try:
        response = httpx.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": payload_messages,
                "temperature": temperature,
                "max_tokens": 1200,
            },
            timeout=90.0,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return str(content).strip(), None
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300] if exc.response is not None else str(exc)
        return None, f"Erro HTTP DeepSeek ({exc.response.status_code}): {detail}"
    except Exception as exc:
        return None, f"Falha ao chamar DeepSeek: {exc}"
