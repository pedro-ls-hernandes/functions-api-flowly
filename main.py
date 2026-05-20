"""Google Cloud Functions / Functions Framework entrypoint.

O runtime do Cloud Functions (Python) carrega o módulo `main` por padrão.
Aqui nós expomos a função HTTP `trigger_http`.

Para rodar local via Functions Framework:
    functions-framework --target trigger_http --port 8080
"""

from function import flowly_mock, trigger_http  # noqa: F401
