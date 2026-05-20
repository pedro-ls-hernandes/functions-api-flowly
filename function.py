from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, is_dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, Optional, Tuple

from api_client import APIError, FlowlyAPIClient
from command_parser import CommandParser, Match


OBJ_ID_LEN = 24


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    return " ".join(text.split())


def _ratio(a: str, b: str) -> int:
    return int(round(SequenceMatcher(None, a, b).ratio() * 100))


def _token_set_ratio(a: str, b: str) -> int:
    a = _normalize(a)
    b = _normalize(b)
    if not a or not b:
        return 0

    tokens_a = set(a.split())
    tokens_b = set(b.split())
    intersection = tokens_a & tokens_b
    diff_a = tokens_a - intersection
    diff_b = tokens_b - intersection

    sect = " ".join(sorted(intersection))
    combo_a = " ".join(sorted(intersection | diff_a))
    combo_b = " ".join(sorted(intersection | diff_b))

    return max(_ratio(sect, combo_a), _ratio(sect, combo_b), _ratio(combo_a, combo_b))


def _is_object_id(value: str) -> bool:
    v = (value or "").strip()
    if len(v) != OBJ_ID_LEN:
        return False
    try:
        int(v, 16)
        return True
    except Exception:
        return False


def _json_response(payload: Dict[str, Any], status: int = 200) -> tuple[str, int, Dict[str, str]]:
    return (json.dumps(payload, ensure_ascii=False), status, {"Content-Type": "application/json"})


def _has_permission(user_type: Optional[str], required: str) -> bool:
    if required == "any":
        return True
    if user_type not in {"admin", "user"}:
        return required != "admin"
    if required == "admin":
        return user_type == "admin"
    if required == "user":
        return user_type == "user"
    return False


def _coerce_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _coerce_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce_jsonable(v) for v in value]
    return str(value)


def _default_data_paths() -> Tuple[str, str]:
    here = os.path.dirname(__file__)
    packaged = os.path.join(here, "mock_data.json")
    runtime = os.getenv("FLOWLY_MOCK_DATA_PATH", "/tmp/mock_data.json").strip() or "/tmp/mock_data.json"
    return packaged, runtime


def _ensure_runtime_data_file() -> str:
    packaged, runtime = _default_data_paths()

    # If the user points to a custom absolute path, respect it.
    if os.path.isabs(runtime):
        target = runtime
    else:
        target = os.path.join(os.path.dirname(__file__), runtime)

    if os.path.exists(target):
        return target

    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.exists(packaged):
        shutil.copyfile(packaged, target)
    else:
        # If repository data is missing, start empty; api_client will create the file.
        pass

    return target


def _resolve_team_ref(api: FlowlyAPIClient, ref: str) -> Tuple[str, str]:
    if _is_object_id(ref):
        return ref, ref

    query = _normalize(ref)
    if len(query) < 2:
        raise APIError("Nome da equipe inválido")

    equipes = api.list_my_teams()
    if not isinstance(equipes, list) or not equipes:
        raise APIError("Nenhuma equipe encontrada")

    scored: list[tuple[int, str, str]] = []
    for e in equipes:
        if not isinstance(e, dict):
            continue
        eid = str(e.get("_id") or "").strip()
        nome = str(e.get("nome") or "").strip()
        if not eid or not nome:
            continue
        scored.append((_token_set_ratio(query, nome), eid, nome))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < 65:
        raise APIError("Não consegui encontrar essa equipe pelo nome")

    _score, team_id, label = scored[0]
    return team_id, label


def _candidate_tasks(api: FlowlyAPIClient, user_type: str) -> list[dict]:
    tasks: list[dict] = []
    if user_type == "admin":
        res = api.list_tasks()
        if isinstance(res, list):
            tasks.extend([t for t in res if isinstance(t, dict)])
    else:
        for getter in (api.my_tasks, api.backlog):
            res = getter()
            if isinstance(res, list):
                tasks.extend([t for t in res if isinstance(t, dict)])
    return tasks


def _resolve_task_ref(api: FlowlyAPIClient, user_type: str, ref: str) -> Tuple[str, str]:
    if _is_object_id(ref):
        return ref, ref

    query = _normalize(ref)
    if len(query) < 2:
        raise APIError("Descrição da tarefa inválida")

    tasks = _candidate_tasks(api, user_type)
    if not tasks:
        raise APIError("Nenhuma tarefa disponível para buscar pelo nome")

    seen: set[str] = set()
    scored: list[tuple[int, str, str]] = []
    for t in tasks:
        tid = str(t.get("_id") or "").strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)

        desc = str(t.get("descricao") or "").strip()
        if not desc:
            continue

        equipe = t.get("equipe")
        equipe_nome = ""
        if isinstance(equipe, dict):
            equipe_nome = str(equipe.get("nome") or "").strip()

        label = f"{desc} (equipe {equipe_nome})" if equipe_nome else desc
        scored.append((_token_set_ratio(query, desc), tid, label))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < 62:
        raise APIError("Não consegui encontrar essa tarefa pelo nome/descrição")

    _score, task_id, label = scored[0]
    return task_id, label


def _execute(match: Match, api: FlowlyAPIClient, params: Dict[str, str]) -> Any:
    key = match.command.key

    if key == "me":
        return api.me()
    if key == "list_users":
        return api.list_users()
    if key == "search_users":
        return api.search_users(params["q"])

    if key == "my_teams":
        return api.list_my_teams()
    if key == "list_teams":
        return api.list_teams()
    if key == "team_members":
        return api.team_members(params["team_id"])
    if key == "team_messages":
        return api.team_messages(params["team_id"])
    if key == "create_team":
        return api.create_team(params["nome"])

    if key == "task_details":
        return api.task_details(params["task_id"])
    if key == "add_comment":
        return api.add_comment(params["task_id"], params["texto"])
    if key == "add_subtask":
        return api.add_subtask(params["task_id"], params["descricao"])

    if key == "my_tasks":
        return api.my_tasks()
    if key == "backlog":
        return api.backlog()
    if key == "assign_to_me":
        return api.assign_to_me(params["task_id"])
    if key == "update_status":
        return api.update_status(params["task_id"], params["status"])
    if key == "timer":
        return api.timer(params["task_id"], params["acao"])

    if key == "create_task":
        return api.create_task(descricao=params["descricao"], equipe=params["equipe"])
    if key == "list_tasks":
        return api.list_tasks()
    if key == "delete_task":
        return api.delete_task(params["task_id"])

    raise APIError(f"Comando não implementado: {key}")


def flowly_mock(request):
    """Google Functions / Cloud Run entrypoint.

    POST JSON:
      {"utterance": "minhas tarefas", "params": {..}, "user_type": "admin|user", "me_user_id": "..."}

    Returns JSON with match + result.
    """

    if request.method == "GET":
        return _json_response({"ok": True, "service": "flowly_assistente_mock", "message": "POST JSON em /"})

    try:
        body = request.get_json(silent=True) or {}
    except Exception:
        body = {}

    utterance = str(body.get("utterance") or body.get("text") or "").strip()
    if not utterance:
        return _json_response({"ok": False, "error": "missing_utterance"}, 400)

    user_type = str(body.get("user_type") or os.getenv("FLOWLY_USER_TYPE", "admin") or "admin").strip().lower()
    me_user_id = str(body.get("me_user_id") or os.getenv("FLOWLY_ME_USER_ID", "") or "").strip()

    data_path = _ensure_runtime_data_file()
    api = FlowlyAPIClient(data_path=data_path, me_tipo=user_type or "admin", me_user_id=me_user_id)

    # Prefer the type from mock_data.json/me() when available.
    try:
        me = api.me()
        tipo = (me or {}).get("tipo")
        if isinstance(tipo, str) and tipo.strip().lower() in {"admin", "user"}:
            user_type = tipo.strip().lower()
    except Exception:
        pass

    parser = CommandParser(threshold=int(os.getenv("FLOWLY_MATCH_THRESHOLD", "78")))
    match = parser.match(utterance)
    if match is None:
        return _json_response({"ok": False, "error": "unrecognized_command"}, 400)

    if match.command.key == "exit":
        return _json_response({"ok": True, "command": {"key": "exit"}, "message": "noop"})

    if not _has_permission(user_type, match.command.role_required):
        return _json_response({"ok": False, "error": "forbidden"}, 403)

    params: Dict[str, str] = {}
    raw_params = body.get("params")
    if isinstance(raw_params, dict):
        params.update({str(k): str(v) for k, v in raw_params.items() if v is not None})

    # Params extracted from the utterance override provided ones.
    params.update(match.params)

    missing = [p for p in match.command.required_params if not params.get(p)]
    if missing:
        return _json_response({"ok": False, "error": "missing_params", "missing": missing}, 400)

    # Resolve team/task refs for non-objectId strings.
    try:
        if params.get("team_id") and not _is_object_id(params["team_id"]):
            tid, label = _resolve_team_ref(api, params["team_id"])
            params["team_id"] = tid
            params.setdefault("_team_label", label)

        if params.get("equipe") and not _is_object_id(params["equipe"]):
            tid, label = _resolve_team_ref(api, params["equipe"])
            params["equipe"] = tid
            params.setdefault("_team_label", label)

        if params.get("task_id") and not _is_object_id(params["task_id"]):
            tid, label = _resolve_task_ref(api, user_type, params["task_id"])
            params["task_id"] = tid
            params.setdefault("_task_label", label)
    except APIError as e:
        return _json_response({"ok": False, "error": "resolve_failed", "message": str(e)}, 400)

    try:
        result = _execute(match, api, params)
        return _json_response(
            {
                "ok": True,
                "command": {
                    "key": match.command.key,
                    "title": match.command.title,
                    "method": match.command.method,
                    "route": match.command.route,
                    "controller_method": match.command.controller_method,
                    "role_required": match.command.role_required,
                    "score": match.score,
                },
                "user_type": user_type,
                "params": params,
                "result": _coerce_jsonable(result),
            }
        )
    except APIError as e:
        return _json_response({"ok": False, "error": "api_error", "message": str(e)}, 400)
    except Exception as e:
        return _json_response({"ok": False, "error": "internal_error", "message": str(e)}, 500)


def trigger_http(request):
    """HTTP Trigger entrypoint (Google Cloud Functions).

    Alias para `flowly_mock`.
    """

    return flowly_mock(request)
