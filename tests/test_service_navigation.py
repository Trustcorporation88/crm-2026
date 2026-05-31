"""Garante que cada serviço do catálogo aponta para uma seção implementada no app."""

from services_catalog import SERVICE_CATALOG, resolve_service_section

IMPLEMENTED_SECTIONS = {
    "Serviços",
    "Visao Executiva",
    "Atendimento",
    "Canais",
    "Cadencias",
    "Clientes 360",
    "Health Score",
    "Templates",
    "Pipeline",
    "Forecast",
    "Produtividade",
    "Marketing",
    "Lead Scoring",
    "Segmentacao",
    "AI Insights",
    "Benchmark",
    "Admin",
}


def test_every_catalog_service_maps_to_implemented_section() -> None:
    missing = []
    for service in SERVICE_CATALOG:
        section = resolve_service_section(service["id"])
        if section not in IMPLEMENTED_SECTIONS:
            missing.append((service["id"], section))
    assert not missing, f"Serviços sem tela: {missing}"


def test_catalog_has_expected_service_count() -> None:
    assert len(SERVICE_CATALOG) == 17


def test_each_service_has_guide_fields() -> None:
    from services_catalog import service_guide_payload

    for service in SERVICE_CATALOG:
        guide = service_guide_payload(service)
        assert guide["objetivo"]
        assert guide["resultado_esperado"]
        assert guide["resumo_geral"]
        assert isinstance(guide["dados_input"], list) and guide["dados_input"]
        assert isinstance(guide["como_usar"], list) and guide["como_usar"]
