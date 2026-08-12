# Módulos não integrados

Os arquivos deste diretório **não são importados por nenhuma parte do sistema**.
Foram escritos, ficaram prontos no sentido de "compilam e passam no lint", mas
nunca chegaram a ser ligados ao produto.

Estavam na raiz do repositório, ao lado do código em uso, e a documentação os
descrevia como funcionalidades entregues. Essa combinação é pior do que não
tê-los: alguém lendo `IMPLEMENTATION-STATUS-V2.md` conclui que o CRM tem SSO,
tradução e reenvio de webhook — e nenhuma das três coisas acontece em execução.

Foram movidos para cá em vez de apagados porque o trabalho tem valor e serve de
ponto de partida. Mas quem for integrá-los precisa ler os avisos abaixo antes.

## `sso_auth.py` — leia antes de ligar

Implementa Azure AD, Google e Okta. **Não está pronto para uso.** Dois problemas
de segurança precisam ser resolvidos primeiro:

1. **Nenhum provedor gera ou valida o parâmetro `state` do OAuth.** Sem ele o
   fluxo aceita CSRF e injeção de código de autorização (RFC 6749 §10.12). Um
   atacante consegue associar a sessão da vítima a uma identidade que ele
   controla.
2. **O `id_token` não é validado.** Google e Okta devolvem um JWT assinado, e o
   código o repassa sem verificar assinatura, emissor (`iss`), destinatário
   (`aud`) ou expiração. Quem interceptar ou repetir esse token se passa por
   qualquer usuário.

Hoje isso é inofensivo justamente porque nada importa o módulo. Ligá-lo como
está transforma dois defeitos dormentes em duas vulnerabilidades ativas.

Vale notar que o fluxo OAuth do ACI, em `crm_backend.py`, **faz** a validação de
`state` corretamente — use-o como referência.

## `i18n.py`

Estrutura de tradução para quatro idiomas. Nenhuma chamada a função de tradução
existe no código; a interface é inteiramente em português. Integrar significa
percorrer as telas trocando os textos literais, o que é trabalho de produto, não
de infraestrutura.

## `webhook_utils.py`

Fila de reenvio com backoff exponencial. Hoje `crm_api.py` grava o payload numa
chave do Redis e não há processo que a consuma — não existe reenvio de webhook
no sistema, apesar de a documentação afirmar que sim.
