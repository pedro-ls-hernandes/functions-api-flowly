from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class APIError(RuntimeError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_object_id() -> str:
    # Mongo-like 24 hex chars (not guaranteed unique, but good enough for mock)
    return uuid.uuid4().hex[:24]


def _abs_data_path(path: str) -> str:
    path = (path or "").strip() or "mock_data.json"
    if os.path.isabs(path):
        return path
    return os.path.join(os.path.dirname(__file__), path)


class _MockStore:
    def __init__(self, path: str) -> None:
        self.path = _abs_data_path(path)
        self._lock = threading.RLock()
        self.data: Dict[str, Any] = {
            "users": [],
            "equipes": [],
            "tarefas": [],
            "comentarios": [],
            "logs": [],
            "messages": [],
        }
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not os.path.exists(self.path):
                self._save()
                return
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if isinstance(payload, dict):
                    self.data.update(payload)
            except Exception as e:
                raise APIError(f"Falha ao ler mock_data.json: {e}") from e

    def _save(self) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                raise APIError(f"Falha ao salvar mock_data.json: {e}") from e

    def save(self) -> None:
        self._save()


@dataclass
class FlowlyAPIClient:
    data_path: str
    me_tipo: str = "admin"  # admin|user
    me_user_id: str = ""  # se definido, força o "usuário logado" no mock

    def __post_init__(self) -> None:
        self._store = _MockStore(self.data_path)
        self.me_tipo = (self.me_tipo or "admin").strip().lower()

        forced_id = (self.me_user_id or "").strip()
        if forced_id:
            self._me_user_id = forced_id
            u = self._find_user(self._me_user_id)
            if not u:
                # Se o id veio do .env mas não existe no mock_data.json, cria um usuário mínimo.
                if self.me_tipo not in {"admin", "user"}:
                    raise APIError("FLOWLY_USER_TYPE inválido (use admin ou user)")
                u = {
                    "_id": self._me_user_id,
                    "nome": "Mock User",
                    "email": "mock@local",
                    "tipo": self.me_tipo,
                }
                self._store.data.setdefault("users", []).append(u)
                self._store.save()

            tipo = str((u or {}).get("tipo") or "").strip().lower()
            if tipo in {"admin", "user"}:
                self.me_tipo = tipo
            elif self.me_tipo not in {"admin", "user"}:
                raise APIError("Tipo de usuário inválido no mock_data.json (use admin ou user)")
        else:
            self._me_user_id = self._pick_me_user_id(self.me_tipo)

    def _my_team_ids(self) -> set[str]:
        my_id = str(self._me_user_id)
        ids: set[str] = set()
        for e in self._store.data.get("equipes") or []:
            if not isinstance(e, dict):
                continue
            membros = [str(x) for x in (e.get("membros") or [])]
            if my_id in membros:
                tid = str(e.get("_id") or "").strip()
                if tid:
                    ids.add(tid)
        return ids

    # -----------------
    # Helpers
    # -----------------
    def _pick_me_user_id(self, tipo: str) -> str:
        users = self._store.data.get("users") or []
        for u in users:
            if isinstance(u, dict) and str(u.get("tipo") or "").lower() == tipo:
                uid = str(u.get("_id") or "").strip()
                if uid:
                    return uid
        # fallback: first user
        for u in users:
            if isinstance(u, dict):
                uid = str(u.get("_id") or "").strip()
                if uid:
                    return uid
        # create minimal user if none
        uid = _new_object_id()
        self._store.data["users"] = [
            {"_id": uid, "nome": "Mock User", "email": "mock@local", "tipo": tipo or "admin"}
        ]
        self._store.save()
        return uid

    def _find_user(self, user_id: str) -> Optional[dict]:
        for u in self._store.data.get("users") or []:
            if isinstance(u, dict) and str(u.get("_id")) == str(user_id):
                return u
        return None

    def _user_public(self, user_id: Optional[str]) -> Optional[dict]:
        if not user_id:
            return None
        u = self._find_user(user_id)
        if not u:
            return None
        return {"_id": u.get("_id"), "nome": u.get("nome"), "email": u.get("email"), "tipo": u.get("tipo")}

    def _find_team(self, team_id: str) -> Optional[dict]:
        for e in self._store.data.get("equipes") or []:
            if isinstance(e, dict) and str(e.get("_id")) == str(team_id):
                return e
        return None

    def _team_public(self, team_id: Optional[str]) -> Optional[dict]:
        if not team_id:
            return None
        e = self._find_team(team_id)
        if not e:
            return None
        return {"_id": e.get("_id"), "nome": e.get("nome")}

    def _find_task(self, task_id: str) -> Optional[dict]:
        for t in self._store.data.get("tarefas") or []:
            if isinstance(t, dict) and str(t.get("_id")) == str(task_id):
                return t
        return None

    def _populate_task(self, task: dict) -> dict:
        task_out = dict(task)
        task_out["user"] = self._user_public(task.get("user")) if task.get("user") else None
        task_out["equipe"] = self._team_public(task.get("equipe"))
        return task_out

    # -----------------
    # API-like methods
    # -----------------
    def me(self) -> Any:
        u = self._find_user(self._me_user_id) or {}
        team_ids = self._my_team_ids() if self.me_tipo == "user" else {
            str(e.get("_id"))
            for e in (self._store.data.get("equipes") or [])
            if isinstance(e, dict) and str(e.get("_id") or "").strip()
        }
        equipes = [self._team_public(tid) for tid in sorted(team_ids) if self._team_public(tid)]
        return {
            "_id": u.get("_id") or self._me_user_id,
            "nome": u.get("nome") or "Mock",
            "email": u.get("email") or "mock@local",
            "tipo": (u.get("tipo") or self.me_tipo or "admin"),
            "equipes": equipes,
        }

    def list_users(self) -> Any:
        out = []
        for u in (self._store.data.get("users") or []):
            if not isinstance(u, dict):
                continue
            out.append({"nome": u.get("nome"), "tipo": u.get("tipo")})
        return out

    def search_users(self, q: str) -> Any:
        qn = (q or "").strip().lower()
        if not qn:
            return []
        out = []
        for u in self._store.data.get("users") or []:
            if not isinstance(u, dict):
                continue
            nome = str(u.get("nome") or "").lower()
            email = str(u.get("email") or "").lower()
            if qn in nome or qn in email:
                out.append({"nome": u.get("nome"), "tipo": u.get("tipo")})
        return out

    def list_teams(self) -> Any:
        equipes = []
        for e in self._store.data.get("equipes") or []:
            if not isinstance(e, dict):
                continue
            membros_ids = e.get("membros") or []
            membros = [self._user_public(uid) for uid in membros_ids if self._user_public(uid)]
            equipes.append({"_id": e.get("_id"), "nome": e.get("nome"), "membros": membros})
        return equipes

    def list_my_teams(self) -> Any:
        if self.me_tipo == "admin":
            return self.list_teams()

        allowed = self._my_team_ids()
        equipes = []
        for e in self._store.data.get("equipes") or []:
            if not isinstance(e, dict):
                continue
            eid = str(e.get("_id") or "").strip()
            if not eid or eid not in allowed:
                continue
            membros_ids = e.get("membros") or []
            membros = [self._user_public(uid) for uid in membros_ids if self._user_public(uid)]
            equipes.append({"_id": e.get("_id"), "nome": e.get("nome"), "membros": membros})
        return equipes

    def team_members(self, team_id: str) -> Any:
        team = self._find_team(team_id)
        if not team:
            # MOCK (GET): não bloquear; retorna vazio.
            return []
        membros_ids = team.get("membros") or []
        return [
            {"_id": u.get("_id"), "nome": u.get("nome")}
            for u in (self._user_public(uid) for uid in membros_ids)
            if u
        ]

    def team_messages(self, team_id: str) -> Any:
        if not self._find_team(team_id):
            # MOCK (GET): não bloquear; retorna vazio.
            return []
        msgs = []
        for m in self._store.data.get("messages") or []:
            if not isinstance(m, dict):
                continue
            if str(m.get("equipe")) != str(team_id):
                continue
            out = dict(m)
            out["user"] = {"_id": (self._user_public(m.get("user")) or {}).get("_id"), "nome": (self._user_public(m.get("user")) or {}).get("nome")}
            msgs.append(out)
        msgs.sort(key=lambda x: str(x.get("createdAt") or ""))
        return msgs

    def create_team(self, nome: str, membros: Optional[list[str]] = None) -> Any:
        nome = (nome or "").strip()
        if not nome:
            raise APIError("O nome da equipe é obrigatório")

        team_id = _new_object_id()
        membros_ids = [str(x).strip() for x in (membros or []) if str(x).strip()]
        team = {"_id": team_id, "nome": nome, "membros": membros_ids}
        self._store.data.setdefault("equipes", []).append(team)
        self._store.save()
        return {"_id": team_id, "nome": nome, "membros": [self._user_public(uid) for uid in membros_ids if self._user_public(uid)]}

    def task_details(self, task_id: str) -> Any:
        task = self._find_task(task_id)
        if not task:
            # MOCK (GET): não bloquear; retorna estrutura vazia.
            return {"tarefa": None, "comentarios": [], "logs": []}

        tarefa = self._populate_task(task)

        comentarios = []
        for c in self._store.data.get("comentarios") or []:
            if not isinstance(c, dict):
                continue
            if str(c.get("tarefa")) != str(task_id):
                continue
            out = dict(c)
            out["user"] = {"_id": (self._user_public(c.get("user")) or {}).get("_id"), "nome": (self._user_public(c.get("user")) or {}).get("nome")}
            comentarios.append(out)
        comentarios.sort(key=lambda x: str(x.get("createdAt") or ""))

        logs = []
        for l in self._store.data.get("logs") or []:
            if not isinstance(l, dict):
                continue
            if str(l.get("tarefa")) != str(task_id):
                continue
            out = dict(l)
            out["user"] = {"_id": (self._user_public(l.get("user")) or {}).get("_id"), "nome": (self._user_public(l.get("user")) or {}).get("nome")}
            logs.append(out)
        logs.sort(key=lambda x: str(x.get("createdAt") or ""), reverse=True)

        return {"tarefa": tarefa, "comentarios": comentarios, "logs": logs}

    def add_comment(self, task_id: str, texto: str) -> Any:
        task = self._find_task(task_id)
        if not task:
            raise APIError("Tarefa não encontrada")
        texto = (texto or "").strip()
        if not texto:
            raise APIError("Texto do comentário vazio")

        comment = {
            "_id": _new_object_id(),
            "tarefa": str(task_id),
            "user": self._me_user_id,
            "texto": texto,
            "createdAt": _utc_now_iso(),
        }
        self._store.data.setdefault("comentarios", []).append(comment)
        self._store.data.setdefault("logs", []).append(
            {
                "_id": _new_object_id(),
                "tarefa": str(task_id),
                "user": self._me_user_id,
                "acao": "comentario",
                "descricao": "Comentário adicionado (mock)",
                "createdAt": _utc_now_iso(),
            }
        )
        self._store.save()

        out = dict(comment)
        out["user"] = {"_id": (self._user_public(self._me_user_id) or {}).get("_id"), "nome": (self._user_public(self._me_user_id) or {}).get("nome")}
        return out

    def add_subtask(self, task_id: str, descricao: str) -> Any:
        task = self._find_task(task_id)
        if not task:
            raise APIError("Tarefa não encontrada")
        descricao = (descricao or "").strip()
        if not descricao:
            raise APIError("Obrigatório fornecer descrição")

        sub = {"_id": _new_object_id(), "descricao": descricao, "concluida": False}
        task.setdefault("subtarefas", []).append(sub)
        self._store.data.setdefault("logs", []).append(
            {
                "_id": _new_object_id(),
                "tarefa": str(task_id),
                "user": self._me_user_id,
                "acao": "nova_subtarefa",
                "descricao": f"Subtarefa '{descricao}' adicionada (mock)",
                "createdAt": _utc_now_iso(),
            }
        )
        self._store.save()
        return self._populate_task(task)

    def my_tasks(self) -> Any:
        my_id = self._me_user_id
        out = []
        for t in self._store.data.get("tarefas") or []:
            if not isinstance(t, dict):
                continue
            if str(t.get("user") or "") != str(my_id):
                continue
            out.append(self._populate_task(t))
        return out

    def backlog(self) -> Any:
        # backlog: tarefas sem responsável apenas nas equipes do usuário (se user)
        if self.me_tipo == "admin":
            equipes_ids = {
                str(e.get("_id"))
                for e in (self._store.data.get("equipes") or [])
                if isinstance(e, dict) and str(e.get("_id") or "").strip()
            }
        else:
            equipes_ids = self._my_team_ids()

        out = []
        for t in self._store.data.get("tarefas") or []:
            if not isinstance(t, dict):
                continue
            if t.get("user") not in (None, ""):
                continue
            if str(t.get("equipe")) not in equipes_ids:
                continue
            out.append(self._populate_task(t))
        return out

    def assign_to_me(self, task_id: str) -> Any:
        task = self._find_task(task_id)
        if not task:
            raise APIError("Tarefa não encontrada")
        if task.get("user"):
            raise APIError("Esta tarefa já possui responsável")

        task["user"] = self._me_user_id
        self._store.data.setdefault("logs", []).append(
            {
                "_id": _new_object_id(),
                "tarefa": str(task_id),
                "user": self._me_user_id,
                "acao": "atribuir_para_mim",
                "descricao": "Tarefa atribuída ao usuário (mock)",
                "createdAt": _utc_now_iso(),
            }
        )
        self._store.save()
        return self._populate_task(task)

    def update_status(self, task_id: str, status: str) -> Any:
        task = self._find_task(task_id)
        if not task:
            raise APIError("Tarefa não encontrada")

        st = (status or "").strip()
        if st not in {"pendente", "em_andamento", "concluido"}:
            raise APIError("Status inválido")

        task["status"] = st
        self._store.data.setdefault("logs", []).append(
            {
                "_id": _new_object_id(),
                "tarefa": str(task_id),
                "user": self._me_user_id,
                "acao": "status",
                "descricao": f"Status atualizado para {st} (mock)",
                "createdAt": _utc_now_iso(),
            }
        )
        self._store.save()
        return self._populate_task(task)

    def timer(self, task_id: str, acao: str) -> Any:
        task = self._find_task(task_id)
        if not task:
            raise APIError("Tarefa não encontrada")

        acao = (acao or "").strip().lower()
        if acao not in {"iniciar", "pausar"}:
            raise APIError("Ação inválida")

        task["cronometroAtivo"] = acao == "iniciar"
        task["ultimaAtualizacaoCronometro"] = _utc_now_iso()
        self._store.save()
        return self._populate_task(task)

    def create_task(self, *, descricao: str, equipe: str, detalhes: Optional[str] = None, user: Optional[str] = None) -> Any:
        descricao = (descricao or "").strip()
        if not descricao:
            raise APIError("Descrição é obrigatória")

        if not self._find_team(equipe):
            raise APIError("Equipe inválida")

        task_id = _new_object_id()
        task = {
            "_id": task_id,
            "descricao": descricao,
            "detalhes": (detalhes or "").strip() or None,
            "status": "pendente",
            "user": str(user).strip() if user else None,
            "equipe": str(equipe),
            "subtarefas": [],
            "createdAt": _utc_now_iso(),
        }
        self._store.data.setdefault("tarefas", []).append(task)
        self._store.data.setdefault("logs", []).append(
            {
                "_id": _new_object_id(),
                "tarefa": str(task_id),
                "user": self._me_user_id,
                "acao": "criacao",
                "descricao": "Tarefa criada (mock)",
                "createdAt": _utc_now_iso(),
            }
        )
        self._store.save()
        return self._populate_task(task)

    def list_tasks(self, *, user: Optional[str] = None, equipe: Optional[str] = None) -> Any:
        out = []
        for t in self._store.data.get("tarefas") or []:
            if not isinstance(t, dict):
                continue
            if user and str(t.get("user") or "") != str(user):
                continue
            if equipe and str(t.get("equipe") or "") != str(equipe):
                continue
            out.append(self._populate_task(t))
        return out

    def delete_task(self, task_id: str) -> Any:
        tasks = [t for t in (self._store.data.get("tarefas") or []) if isinstance(t, dict)]
        before = len(tasks)
        tasks = [t for t in tasks if str(t.get("_id")) != str(task_id)]
        if len(tasks) == before:
            raise APIError("Tarefa não encontrada")
        self._store.data["tarefas"] = tasks
        self._store.save()
        return {"msg": "Tarefa excluída (mock)"}
