# Flowly Assistente Mock (Python)

Cópia do `flowly_assistente` que roda **sem backend e sem banco**, usando uma API mockada em memória com dados do arquivo `mock_data.json`.

## Como rodar

```bash
cd flowly_assistente_mock
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python main.py
```

## Como funciona
- O assistente usa a mesma lógica de comandos/parsing, mas o arquivo `api_client.py` é mockado.
- Os dados ficam em `mock_data.json` e são atualizados em memória durante a execução.
- Identificação de equipe/tarefa é por **nome/descrição** (o assistente resolve para `_id`).

## Dados
Edite `mock_data.json` para criar seus próprios usuários/equipes/tarefas.
