from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, Optional

from api_client import APIError, FlowlyAPIClient
from command_parser import CommandParser, Match
from settings import Settings, get_settings
from speech_service import SpeechService
from tts_service import TTSService


OBJ_ID_RE = re.compile(r"\b[a-fA-F0-9]{24}\b")


YES = {"sim", "confirmo", "isso", "pode", "correto", "ok"}
NO = {"não", "nao", "negativo", "cancela", "cancelar"}


class FlowlyAssistant:
    def __init__(self) -> None:
        self.settings: Settings = get_settings()
        self.tts = TTSService(
            rate=self.settings.tts_rate,
            volume=self.settings.tts_volume,
            enabled=self.settings.tts_enabled,
        )
        self.speech = SpeechService(
            language=self.settings.language,
            listen_timeout=self.settings.listen_timeout,
            phrase_time_limit=self.settings.phrase_time_limit,
            sr_energy_threshold=self.settings.sr_energy_threshold,
            sr_dynamic_energy=self.settings.sr_dynamic_energy,
            sr_pause_threshold=self.settings.sr_pause_threshold,
            sr_non_speaking_duration=self.settings.sr_non_speaking_duration,
        )
        self.parser = CommandParser(threshold=self.settings.match_threshold)
        self.api = FlowlyAPIClient(
            data_path=self.settings.mock_data_path,
            me_tipo=self.settings.user_type or "admin",
            me_user_id=self.settings.me_user_id,
        )

        self.user_type: Optional[str] = self.settings.user_type or None

    def run(self) -> None:
        self._say("Assistente Flowly (MOCK) iniciado. Diga um comando.")
        self._warmup_user_type()

        while True:
            utterance = self._listen_command()
            if utterance is None:
                continue

            match = self.parser.match(utterance)
            if match is None:
                self._say("Não consegui identificar o comando. Pode repetir?")
                continue

            if match.command.key == "exit":
                self._say("Encerrando. Até mais!")
                return

            if not self._has_permission(match.command.role_required):
                self._say("Você não tem permissão para esse comando.")
                self._print_route(match)
                continue

            params = dict(match.params)
            missing = [p for p in match.command.required_params if p not in params or not params[p]]
            if missing:
                ok = self._fill_missing_params(match.command.key, missing, params)
                if not ok:
                    self._say("Ok, vamos tentar novamente.")
                    continue

            method = (match.command.method or "").upper()
            # No mock: em comandos GET/POST, não fazer resolução/validação por API.
            if method not in {"GET", "POST"}:
                ok = self._resolve_param_ids(match.command.key, params)
                if not ok:
                    self._say("Ok, vamos tentar novamente.")
                    continue

            # No mock: em GET/POST, não pedir confirmação.
            if method not in {"GET", "POST"}:
                if not self._confirm(match, params):
                    self._say("Tudo bem. Vou ouvir novamente.")
                    continue

            try:
                self._print_route(match)
                result = self._execute(match, params)
                self._respond_success(match.command.key, result)
            except APIError as e:
                self._say("Ocorreu um erro ao chamar a API (mock).")
                print(f"[API ERROR] {e}")
            except Exception as e:
                self._say("Ocorreu um erro inesperado.")
                print(f"[ERROR] {e}")

    def _warmup_user_type(self) -> None:
        if self.user_type in {"admin", "user"}:
            return
        try:
            me = self.api.me()
            tipo = (me or {}).get("tipo")
            if isinstance(tipo, str) and tipo.lower() in {"admin", "user"}:
                self.user_type = tipo.lower()
        except Exception:
            pass

    def _has_permission(self, required: str) -> bool:
        if required == "any":
            return True
        if self.user_type not in {"admin", "user"}:
            return required != "admin"
        if required == "admin":
            return self.user_type == "admin"
        if required == "user":
            return self.user_type == "user"
        return False

    def _listen_command(self) -> Optional[str]:
        if self.settings.text_only:
            try:
                res = self.speech.listen_text_fallback("(Texto) Digite o comando: ")
                return res.text
            except Exception:
                return None
        try:
            res = self.speech.listen_once()
            self._say(f"Você disse: {res.text}")
            return res.text
        except Exception as e:
            self._say(str(e))
            try:
                res = self.speech.listen_text_fallback("(Fallback) Digite o comando: ")
                return res.text
            except Exception:
                return None

    def _confirm(self, match: Match, params: Dict[str, str]) -> bool:
        action = self._confirmation_text(match, params)
        self._ask(f"Confirma a ação: {action}? Diga sim ou não.")

        if self.settings.text_only:
            try:
                res = input("\nConfirma? (sim/nao): ").strip().lower()
            except Exception:
                return False
        else:
            try:
                res = self.speech.listen_once().text.strip().lower()
            except Exception:
                # fallback para texto quando voz falhar/expirar
                try:
                    res = self.speech.listen_text_fallback("\nConfirma? (sim/nao): ").text.strip().lower()
                except Exception:
                    return False

        if res in YES or res.startswith("s"):
            return True
        if res in NO or res.startswith("n"):
            return False

        self._ask("Não entendi. Responda sim ou não.")

        return False

    def _confirmation_text(self, match: Match, params: Dict[str, str]) -> str:
        c = match.command
        task_label = params.get("_task_label") or params.get("task_id")
        team_label = params.get("_team_label") or params.get("team_id")

        if c.key == "task_details":
            return f"mostrar detalhes da tarefa {task_label}"
        if c.key == "add_comment":
            return f"adicionar comentário na tarefa {task_label}"
        if c.key == "update_status":
            return f"alterar status da tarefa {task_label} para {params.get('status')}"
        if c.key == "timer":
            return f"{params.get('acao')} o cronômetro da tarefa {task_label}"
        if c.key == "assign_to_me":
            return f"atribuir a tarefa {task_label} para você"
        if c.key == "team_members":
            return f"listar membros da equipe {team_label}"
        if c.key == "team_messages":
            return f"mostrar mensagens da equipe {team_label}"
        if c.key == "search_users":
            return f"buscar usuário por {params.get('q')}"
        return c.title

    def _fill_missing_params(self, command_key: str, missing: list[str], params: Dict[str, str]) -> bool:
        for name in missing:
            if name in {"task_id", "team_id"}:
                self._ask(
                    "Qual é o nome/descrição da tarefa?" if name == "task_id" else "Qual é o nome da equipe?"
                )
                ans = self._ask_value("Nome: ")
                if not ans:
                    return False
                params[name] = ans
            elif name == "texto":
                self._ask("Qual é o texto do comentário?")
                ans = self._ask_value("Comentário: ")
                if not ans:
                    return False
                params[name] = ans
            elif name == "descricao":
                self._ask("Qual é a descrição?")
                ans = self._ask_value("Descrição: ")
                if not ans:
                    return False
                params[name] = ans
            elif name == "status":
                self._ask("Qual status? pendente, em andamento, ou concluído.")
                ans = self._ask_value("Status: ")
                if not ans:
                    return False
                if "andamento" in ans:
                    params[name] = "em_andamento"
                elif "conclu" in ans or "final" in ans:
                    params[name] = "concluido"
                else:
                    params[name] = "pendente"
            elif name == "acao":
                self._ask("Você quer iniciar ou pausar?")
                ans = self._ask_value("Ação: ")
                if not ans:
                    return False
                params[name] = "iniciar" if ans.startswith("i") else "pausar"
            elif name == "q":
                self._ask("Qual termo de busca?")
                ans = self._ask_value("Busca: ")
                if not ans:
                    return False
                params[name] = ans
            elif name == "nome":
                self._ask("Qual o nome da equipe?")
                ans = self._ask_value("Nome da equipe: ")
                if not ans:
                    return False
                params[name] = ans
            elif name == "equipe":
                self._ask("Qual o nome da equipe?")
                ans = self._ask_value("Equipe (nome): ")
                if not ans:
                    return False
                params[name] = ans
            else:
                self._ask(f"Preciso do parâmetro {name}.")
                ans = self._ask_value(f"{name}: ")
                if not ans:
                    return False
                params[name] = ans

        return True

    def _resolve_param_ids(self, command_key: str, params: Dict[str, str]) -> bool:
        try:
            if "team_id" in params and params.get("team_id"):
                team_id, team_label = self._resolve_team_ref(params["team_id"])
                params["team_id"] = team_id
                params.setdefault("_team_label", team_label)

            if "equipe" in params and params.get("equipe"):
                team_id, team_label = self._resolve_team_ref(params["equipe"])
                params["equipe"] = team_id
                params.setdefault("_team_label", team_label)

            if "task_id" in params and params.get("task_id"):
                task_id, task_label = self._resolve_task_ref(params["task_id"])
                params["task_id"] = task_id
                params.setdefault("_task_label", task_label)

            return True
        except Exception as e:
            self._say(str(e))
            return False

    def _normalize(self, text: str) -> str:
        text = (text or "").strip().lower()
        text = re.sub(r"[\t\n\r]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def _ratio(self, a: str, b: str) -> int:
        return int(round(SequenceMatcher(None, a, b).ratio() * 100))

    def _token_set_ratio(self, a: str, b: str) -> int:
        a = self._normalize(a)
        b = self._normalize(b)
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

        return max(self._ratio(sect, combo_a), self._ratio(sect, combo_b), self._ratio(combo_a, combo_b))

    def _extract_object_id(self, text: str) -> Optional[str]:
        m = OBJ_ID_RE.search(text or "")
        return m.group(0) if m else None

    def _parse_choice(self, text: str, max_choice: int) -> Optional[int]:
        t = self._normalize(text)
        m = re.search(r"\b([1-9])\b", t)
        if m:
            n = int(m.group(1))
            return n if 1 <= n <= max_choice else None

        words = {
            "um": 1,
            "uma": 1,
            "primeiro": 1,
            "primeira": 1,
            "dois": 2,
            "duas": 2,
            "segundo": 2,
            "segunda": 2,
            "tres": 3,
            "três": 3,
            "terceiro": 3,
            "terceira": 3,
            "quatro": 4,
            "quarto": 4,
            "quarta": 4,
            "cinco": 5,
            "quinto": 5,
            "quinta": 5,
        }
        for w, n in words.items():
            if w in t.split():
                return n if 1 <= n <= max_choice else None
        return None

    def _choose_from_matches(self, kind: str, matches: list[tuple[int, str, str]]) -> tuple[str, str]:
        top = matches[:5]
        self._ask(f"Encontrei várias opções de {kind}. Escolha pelo número.")
        for idx, (_score, _id, label) in enumerate(top, start=1):
            self._say(f"{idx}. {label}")

        for _ in range(2):
            ans = self._ask_value("Escolha (1-5): ")
            choice = self._parse_choice(ans, max_choice=len(top))
            if choice is not None:
                _score, _id, label = top[choice - 1]
                return _id, label
            self._ask("Não entendi. Diga um número como 1, 2 ou 3.")

        raise RuntimeError(f"Não consegui selecionar a {kind}. Tente novamente dizendo o nome.")

    def _resolve_team_ref(self, ref: str) -> tuple[str, str]:
        oid = self._extract_object_id(ref)
        if oid:
            return oid, oid

        query = self._normalize(ref)
        if len(query) < 2:
            raise RuntimeError("Nome da equipe inválido.")

        equipes = self.api.list_my_teams()
        if not isinstance(equipes, list) or not equipes:
            raise RuntimeError("Não encontrei equipes disponíveis para sua conta.")

        scored: list[tuple[int, str, str]] = []
        for e in equipes:
            if not isinstance(e, dict):
                continue
            eid = str(e.get("_id") or "").strip()
            nome = str(e.get("nome") or "").strip()
            if not eid or not nome:
                continue
            score = self._token_set_ratio(query, nome)
            scored.append((score, eid, nome))

        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored or scored[0][0] < 65:
            raise RuntimeError("Não consegui encontrar essa equipe pelo nome. Tente dizer o nome completo.")

        if len(scored) > 1 and scored[1][0] >= scored[0][0] - 3 and scored[1][0] >= 65:
            return self._choose_from_matches("equipe", scored)

        _score, eid, nome = scored[0]
        return eid, nome

    def _resolve_task_ref(self, ref: str) -> tuple[str, str]:
        oid = self._extract_object_id(ref)
        if oid:
            return oid, oid

        query = self._normalize(ref)
        if len(query) < 2:
            raise RuntimeError("Descrição da tarefa inválida.")

        tasks: list[dict] = []
        if self.user_type == "admin":
            res = self.api.list_tasks()
            if isinstance(res, list):
                tasks.extend([t for t in res if isinstance(t, dict)])
        else:
            for getter in (self.api.my_tasks, self.api.backlog):
                res = getter()
                if isinstance(res, list):
                    tasks.extend([t for t in res if isinstance(t, dict)])

        if not tasks:
            raise RuntimeError("Não encontrei tarefas para buscar pelo nome. Tente listar suas tarefas/backlog primeiro.")

        seen: set[str] = set()
        scored: list[tuple[int, str, str]] = []
        for t in tasks:
            tid = str(t.get("_id") or "").strip()
            if not tid or tid in seen:
                continue
            seen.add(tid)

            desc = str(t.get("descricao") or "").strip()
            equipe = t.get("equipe")
            equipe_nome = ""
            if isinstance(equipe, dict):
                equipe_nome = str(equipe.get("nome") or "").strip()

            label = desc
            if equipe_nome:
                label = f"{desc} (equipe {equipe_nome})"

            score = self._token_set_ratio(query, desc)
            scored.append((score, tid, label))

        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored or scored[0][0] < 62:
            raise RuntimeError(
                "Não consegui encontrar essa tarefa pelo nome/descrição. Tente falar uma parte mais específica da descrição."
            )

        if len(scored) > 1 and scored[1][0] >= scored[0][0] - 3 and scored[1][0] >= 62:
            return self._choose_from_matches("tarefa", scored)

        _score, tid, label = scored[0]
        return tid, label

    def _ask_value(self, prompt: str) -> str:
        try:
            if self.settings.text_only:
                return input(prompt).strip()
            return self.speech.listen_once().text.strip()
        except Exception:
            return input(prompt).strip()

    def _execute(self, match: Match, params: Dict[str, str]) -> Any:
        key = match.command.key

        if key == "me":
            return self.api.me()
        if key == "list_users":
            return self.api.list_users()
        if key == "search_users":
            return self.api.search_users(params["q"])

        if key == "my_teams":
            return self.api.list_my_teams()
        if key == "list_teams":
            return self.api.list_teams()
        if key == "team_members":
            return self.api.team_members(params["team_id"])
        if key == "team_messages":
            return self.api.team_messages(params["team_id"])
        if key == "create_team":
            return self.api.create_team(params["nome"])

        if key == "task_details":
            return self.api.task_details(params["task_id"])
        if key == "add_comment":
            return self.api.add_comment(params["task_id"], params["texto"])
        if key == "add_subtask":
            return self.api.add_subtask(params["task_id"], params["descricao"])

        if key == "my_tasks":
            return self.api.my_tasks()
        if key == "backlog":
            return self.api.backlog()
        if key == "assign_to_me":
            return self.api.assign_to_me(params["task_id"])
        if key == "update_status":
            return self.api.update_status(params["task_id"], params["status"])
        if key == "timer":
            return self.api.timer(params["task_id"], params["acao"])

        if key == "create_task":
            return self.api.create_task(descricao=params["descricao"], equipe=params["equipe"])
        if key == "list_tasks":
            return self.api.list_tasks()
        if key == "delete_task":
            return self.api.delete_task(params["task_id"])

        raise RuntimeError(f"Comando não implementado: {key}")

    def _respond_success(self, key: str, result: Any) -> None:
        if key in {"my_tasks", "backlog", "list_teams", "my_teams", "list_users"}:
            n = len(result) if isinstance(result, list) else 0
            self._say(f"Ok. Encontrei {n} itens.")
            print(result)
            return

        if key == "task_details":
            tarefa = (result or {}).get("tarefa")
            desc = (tarefa or {}).get("descricao") if isinstance(tarefa, dict) else None
            self._say("Detalhes carregados.")
            if desc:
                self._say(f"Tarefa: {desc}")
            print(result)
            return

        self._say("Ação concluída com sucesso.")
        print(result)

    def _print_route(self, match: Match) -> None:
        c = match.command
        if c.route:
            print(f"[ROTA] {c.route} -> {c.controller_method}")

    def _say(self, text: str) -> None:
        print(f"[ASSISTENTE] {text}")
        try:
            self.tts.speak_async(text)
        except Exception:
            pass

    def _ask(self, text: str) -> None:
        print(f"[ASSISTENTE] {text}")
        try:
            # Não bloquear o fluxo enquanto o TTS fala; evita "congelar" aguardando lock/runAndWait.
            self.tts.speak_async(text)
        except Exception:
            pass
