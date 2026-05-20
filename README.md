# Flowly Assistente Mock (Python)

Cópia do `flowly_assistente` que roda **sem backend e sem banco**, usando uma API mockada em memória com dados do arquivo `mock_data.json`.

## Como rodar

```bash
cd flowly_assistente_mock
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python cli.py
```

## Rodar via HTTP (Functions Framework)

Este modo é o indicado para Google Cloud (Cloud Functions Gen2 / Cloud Run).

```bash
cd flowly_assistente_mock
pip install -r requirements.txt
functions-framework --target trigger_http --port 8080
```

## Como funciona
- O assistente usa a mesma lógica de comandos/parsing, mas o arquivo `api_client.py` é mockado.
- Os dados ficam em `mock_data.json` e são atualizados em memória durante a execução.
- Identificação de equipe/tarefa é por **nome/descrição** (o assistente resolve para `_id`).

## Rodar via Docker (HTTP)

Este modo é o mais indicado para subir no Google (Cloud Run / Cloud Functions Gen2), usando o **Functions Framework**.

Build + run:

```bash
cd flowly_assistente_mock
docker build -t flowly-assistente-mock:local .
docker run --rm -p 8080:8080 flowly-assistente-mock:local
```

Teste (exemplo):

```bash
curl -X POST http://localhost:8080/ \
	-H "Content-Type: application/json" \
	-d '{"utterance":"meu perfil"}'
```

Payload aceito (exemplos):

- `{"utterance":"minhas tarefas"}`
- `{"utterance":"mudar status da tarefa Revisar backlog de bugs para concluído"}`
- `{"utterance":"atribuir para mim", "params": {"task_id": "Revisar backlog de bugs"}, "user_type": "user"}`

## Dados
Edite `mock_data.json` para criar seus próprios usuários/equipes/tarefas.
