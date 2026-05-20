from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, Optional, Tuple

from commands import Command, get_commands


OBJ_ID_RE = re.compile(r"\b[a-fA-F0-9]{24}\b")


NEGATION_TOKENS = {
    "não",
    "nao",
    "nega",
    "cancelar",
    "cancela",
    "deixa",
    "esquece",
}


@dataclass
class Match:
    command: Command
    score: int
    params: Dict[str, str]


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[\t\n\r]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


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


def extract_object_id(text: str) -> Optional[str]:
    m = OBJ_ID_RE.search(text or "")
    return m.group(0) if m else None


def extract_status(text: str) -> Optional[str]:
    t = _normalize(text)
    if "em andamento" in t or "andamento" in t:
        return "em_andamento"
    if "conclu" in t or "finaliz" in t or "feito" in t:
        return "concluido"
    if "pendente" in t:
        return "pendente"
    return None


def extract_timer_action(text: str) -> Optional[str]:
    t = _normalize(text)
    if "iniciar" in t or "começar" in t or "comecar" in t or "start" in t:
        return "iniciar"
    if "pausar" in t or "parar" in t or "stop" in t:
        return "pausar"
    return None


def extract_free_text_after(text: str, anchors: Tuple[str, ...]) -> Optional[str]:
    t = _normalize(text)
    for a in anchors:
        if a in t:
            idx = t.find(a)
            frag = t[idx + len(a) :].strip(" :,-")
            frag = OBJ_ID_RE.sub("", frag).strip()
            if len(frag) >= 3:
                return frag
    return None


class CommandParser:
    def __init__(self, threshold: int = 78) -> None:
        self.threshold = threshold
        self.commands = get_commands()

    def match(self, utterance: str) -> Optional[Match]:
        raw = utterance or ""
        text = _normalize(raw)
        if not text:
            return None

        if any(tok in text for tok in ["sair", "encerrar", "parar assistente", "fechar assistente"]):
            cmd = next(c for c in self.commands if c.key == "exit")
            return Match(command=cmd, score=100, params={})

        # Prefer exact phrase matches (avoids fuzzy ties where superset phrases score 100).
        for cmd in self.commands:
            if cmd.key == "exit":
                continue
            for phrase in cmd.phrases:
                if _normalize(phrase) == text:
                    params = self._extract_params(cmd, raw)
                    return Match(command=cmd, score=100, params=params)

        best: Optional[tuple[Command, int, int, int]] = None
        for cmd in self.commands:
            if cmd.key == "exit":
                continue
            for phrase in cmd.phrases:
                phrase_norm = _normalize(phrase)
                score = _token_set_ratio(text, phrase_norm)
                plain = _ratio(text, phrase_norm)
                extra = len(set(phrase_norm.split()) - set(text.split()))
                rank = (score, plain, -extra)
                if best is None or rank > (best[1], best[2], best[3]):
                    best = (cmd, score, plain, -extra)

        if best is None:
            return None

        cmd, score, _plain, _extra_neg = best
        if score < self.threshold:
            return None

        if any(tok in text.split() for tok in NEGATION_TOKENS):
            return None

        params = self._extract_params(cmd, raw)
        return Match(command=cmd, score=score, params=params)

    def _extract_params(self, cmd: Command, raw: str) -> Dict[str, str]:
        text = raw or ""
        params: Dict[str, str] = {}

        if "task_id" in cmd.required_params:
            tid = extract_object_id(text)
            if tid:
                params["task_id"] = tid
            else:
                ref = extract_free_text_after(text, ("tarefa", "task"))
                if ref:
                    params["task_id"] = ref

        if "team_id" in cmd.required_params:
            team_id = extract_object_id(text)
            if team_id:
                params["team_id"] = team_id
            else:
                ref = extract_free_text_after(text, ("equipe", "time", "team"))
                if ref:
                    params["team_id"] = ref

        if cmd.key == "add_comment":
            texto = extract_free_text_after(text, ("dizendo", "texto", "comentário", "comentario"))
            if texto:
                params["texto"] = texto

        if cmd.key == "add_subtask":
            descricao = extract_free_text_after(text, ("subtarefa", "descrição", "descricao"))
            if descricao:
                params["descricao"] = descricao

        if cmd.key == "search_users":
            q = extract_free_text_after(text, ("buscar", "procurar", "usuário", "usuario"))
            if q:
                params["q"] = q

        if cmd.key == "update_status":
            st = extract_status(text)
            if st:
                params["status"] = st

        if cmd.key == "timer":
            acao = extract_timer_action(text)
            if acao:
                params["acao"] = acao

        if cmd.key == "create_team":
            nome = extract_free_text_after(text, ("equipe", "time"))
            if nome:
                params["nome"] = nome

        if cmd.key == "create_task":
            equipe_id = extract_object_id(text)
            if equipe_id:
                params["equipe"] = equipe_id
            else:
                equipe_nome = extract_free_text_after(text, ("equipe", "time"))
                if equipe_nome:
                    params["equipe"] = equipe_nome

            descricao = extract_free_text_after(text, ("tarefa", "criar", "adicionar"))
            if descricao:
                params["descricao"] = descricao

        return params
