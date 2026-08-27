"""Constantes de domínio do funil, compartilhadas por todos os módulos.

Fonte única para os nomes das etapas terminais. Antes deste módulo existir,
``forecast``, ``lead_scoring``, ``health_score`` e ``ai_insights`` filtravam
por ``'Perdido'`` enquanto o backend grava ``'Fechado perdido'`` — nenhum
negócio jamais casava com o filtro, então o win rate saía sempre 100%, o
pipeline incluía negócios perdidos e os scores pontuavam contas já esfriadas.

Qualquer módulo que precise comparar etapa de negócio deve importar daqui,
nunca repetir o literal.
"""

from __future__ import annotations

WON_STAGE = "Fechado ganho"
LOST_STAGE = "Fechado perdido"
CLOSED_STAGES = (WON_STAGE, LOST_STAGE)
