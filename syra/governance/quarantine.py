"""Quarentena de comandos: nenhuma acao destrutiva executa sem analise.

Cada comando recebe uma pontuacao de risco a partir de regras nomeadas. Acima
do limiar de bloqueio o comando nao executa e o motor devolve uma alternativa
segura, em vez de apenas recusar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from syra.contracts import RiskAssessment, RiskLevel
from syra.governance.policy import Policy


@dataclass(frozen=True)
class Rule:
    """Regra de deteccao de risco em comandos de shell."""

    name: str
    pattern: re.Pattern[str]
    score: int
    reason: str
    alternative: str | None = None


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# Regras ordenadas por gravidade. A pontuacao e somada quando varias casam.
RULES: tuple[Rule, ...] = (
    Rule("rm_rf_root", _rx(r"\brm\s+(-[a-z]*[rf][a-z]*\s+)+/(\s|$)"), 100,
         "remocao recursiva a partir da raiz do sistema",
         "delimite o alvo: rm -rf ./caminho/especifico"),
    Rule("rm_rf_home", _rx(r"\brm\s+-[a-z]*[rf][a-z]*\s+(~|\$HOME)(/\s*)?(\s|$)"), 100,
         "remocao recursiva do diretorio do usuario",
         "delimite o alvo dentro de ~: rm -rf ~/projeto/build"),
    Rule("rm_rf_wildcard", _rx(r"\brm\s+-[a-z]*[rf][a-z]*\s+[^\s]*\*"), 75,
         "remocao recursiva com curinga atinge alvos nao previstos",
         "liste antes com: ls <padrao> | head -50"),
    Rule("rm_rf", _rx(r"\brm\s+-[a-z]*[rf][a-z]*r?\b"), 45,
         "remocao recursiva e irreversivel",
         "mova para quarentena: mv <alvo> .syra/trash/"),
    Rule("mkfs", _rx(r"\bmkfs(\.\w+)?\b"), 100,
         "formatacao de sistema de arquivos destroi dados",
         None),
    Rule("dd_device", _rx(r"\bdd\b[^\n]*\bof=/dev/"), 100,
         "escrita bruta em dispositivo de bloco",
         None),
    Rule("git_reset_hard", _rx(r"\bgit\s+reset\s+--hard\b"), 70,
         "descarta alteracoes locais sem recuperacao",
         "preserve o estado: git stash push -u -m backup"),
    Rule("git_clean_fdx", _rx(r"\bgit\s+clean\s+-[a-z]*d[a-z]*[fx]"), 70,
         "apaga arquivos nao rastreados, inclusive ignorados",
         "revise primeiro: git clean -nd"),
    Rule("git_push_force", _rx(r"\bgit\s+push\b[^\n]*(--force|-f)\b(?!\S)"), 60,
         "reescreve historico remoto e quebra clones de terceiros",
         "use trava otimista: git push --force-with-lease"),
    Rule("checkout_dot", _rx(r"\bgit\s+checkout\s+--\s+\.\s*$"), 50,
         "descarta todas as alteracoes do diretorio de trabalho",
         "salve antes: git stash push -u"),
    # Posicao de comando obrigatoria: sem isso, "servidor.shutdown()" num
    # script Python ou um grep pela palavra seriam pontuados como se fossem
    # desligamento de maquina.
    Rule("shutdown", _rx(r"(?:^|[;&|]\s*|\bsudo\s+|\bsystemctl\s+)"
                         r"(shutdown|reboot|halt|poweroff)\b(?!\s*\()"), 80,
         "interrompe a maquina e derruba execucoes em andamento",
         None),
    Rule("kill_dash_nine", _rx(r"\bkill\s+-9\b|\bkillall\s+-9\b"), 40,
         "encerramento forcado impede finalizacao limpa",
         "tente encerramento gracioso: kill -TERM <pid>"),
    Rule("chmod_777_root", _rx(r"\bchmod\s+(-R\s+)?777\s+/(\s|$)"), 95,
         "abre permissoes totais na raiz do sistema",
         "restrinja escopo e permissao: chmod -R 750 ./caminho"),
    Rule("chmod_777", _rx(r"\bchmod\s+(-R\s+)?777\b"), 45,
         "permissao 777 expoe arquivos a qualquer usuario",
         "prefira: chmod -R 750 <alvo>"),
    Rule("curl_pipe_shell", _rx(r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|k)?sh\b"), 85,
         "executa codigo remoto sem inspecao previa",
         "baixe, inspecione e so entao execute o arquivo"),
    Rule("sudo_rm", _rx(r"\bsudo\s+rm\b"), 60,
         "remocao com privilegio administrativo",
         "execute sem sudo dentro do projeto"),
    Rule("history_wipe", _rx(r"\bhistory\s+-c\b|>\s*~/\.bash_history"), 55,
         "apagar historico elimina rastro de auditoria",
         None),
    Rule("drop_database", _rx(r"\bdrop\s+(database|table)\b"), 80,
         "remocao de dados persistentes",
         "faca dump antes e execute dentro de transacao"),
    Rule("truncate_device", _rx(r">\s*/dev/(sd|nvme|hd)\w+"), 100,
         "redirecionamento de saida sobre dispositivo de bloco",
         None),
    Rule("fork_bomb", _rx(r":\(\)\s*\{.*\}\s*;?\s*:"), 100,
         "fork bomb exaure a tabela de processos",
         None),
    Rule("env_secret_echo", _rx(r"\becho\b[^\n]*\$(\w*(TOKEN|SECRET|PASSWORD|KEY))"), 30,
         "imprime segredo em texto claro no terminal e nos logs",
         "verifique apenas a presenca: test -n \"$TOKEN\" && echo definido"),
)


class CommandQuarantine:
    """Classifica comandos em ALLOW, REVIEW ou BLOCK antes da execucao."""

    def __init__(self, policy: Policy | None = None,
                 rules: tuple[Rule, ...] = RULES) -> None:
        self.policy = policy or Policy()
        self.rules = rules

    def assess(self, command: str) -> RiskAssessment:
        """Avalia um comando e devolve nivel, pontuacao e alternativa segura."""
        text = (command or "").strip()
        if not text:
            return RiskAssessment(command=text, level=RiskLevel.ALLOW, score=0,
                                  matched_rules=(), reason="comando vazio")

        matched: list[Rule] = [rule for rule in self.rules if rule.pattern.search(text)]
        score = min(100, sum(rule.score for rule in matched))

        if score >= self.policy.quarantine_block_score:
            level = RiskLevel.BLOCK
        elif score >= self.policy.quarantine_review_score:
            level = RiskLevel.REVIEW
        else:
            level = RiskLevel.ALLOW

        if not matched:
            reason = "nenhum padrao de risco identificado"
            alternative = None
        else:
            reason = "; ".join(rule.reason for rule in matched[:3])
            alternative = next((r.alternative for r in matched if r.alternative), None)

        return RiskAssessment(
            command=text,
            level=level,
            score=score,
            matched_rules=tuple(rule.name for rule in matched),
            reason=reason,
            safe_alternative=alternative,
        )

    def allows(self, command: str) -> bool:
        """Atalho booleano: o comando pode executar sem revisao humana?"""
        return self.assess(command).level is RiskLevel.ALLOW
