"""Claim Registry: nenhuma alegacao comercial publica sem lastro.

Principio 6 do CLAUDE.md: prova, depoimento, preco, garantia, escassez e
comparacao vem de registry aprovado. Este modulo torna isso executavel em
duas metades que se completam:

1. **Deteccao.** Varre um texto e encontra os trechos que FAZEM uma alegacao —
   numero, garantia, depoimento, comparacao ou escassez. Sem esta metade, o
   registry so protege quem ja lembrou de registrar.
2. **Verificacao.** Cada trecho detectado precisa casar com um Claim APROVADO,
   dentro da validade e do escopo (funil e locale). Qualquer trecho sem lastro
   bloqueia a publicacao.

Fail-closed: na duvida, bloqueia. Texto sem alegacao alguma passa; texto com
alegacao nao lastreada nao passa, mesmo que o autor jure que e verdade.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from syra.vfos import contracts, ids, policy

TIPOS = ("FACTUAL", "TESTIMONIAL", "CASE", "COMPARISON", "GUARANTEE")


@dataclass(frozen=True)
class Deteccao:
    """Um trecho de texto que faz uma alegacao verificavel."""

    trecho: str
    tipo: str
    regra: str
    inicio: int

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.trecho, "type": self.tipo, "rule": self.regra,
                "offset": self.inicio}


# Cada regra aponta para o tipo de claim que o trecho passa a exigir.
_REGRAS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("percentual", "FACTUAL",
     re.compile(r"[^.!?\n]*\b\d{1,3}(?:[.,]\d+)?\s*%[^.!?\n]*", re.I)),
    ("valor_monetario", "FACTUAL",
     re.compile(r"[^.!?\n]*R\$\s?\d[\d.,]*[^.!?\n]*", re.I)),
    ("multiplicador", "COMPARISON",
     re.compile(r"[^.!?\n]*\b\d+(?:[.,]\d+)?\s*(?:x|vezes)\s+(?:mais|menos|"
                r"mais\s+rapido|maior|melhor)[^.!?\n]*", re.I)),
    ("quantidade_de_pessoas", "CASE",
     re.compile(r"[^.!?\n]*\b\d[\d.,]*\s*(?:mil\s+)?(?:alunos?|clientes?|"
                r"empresas?|usuarios?|pessoas?|devs?)\b[^.!?\n]*", re.I)),
    ("prazo_prometido", "FACTUAL",
     re.compile(r"[^.!?\n]*\bem\s+(?:apenas\s+)?\d+\s*(?:dias?|semanas?|horas?|"
                r"minutos?)\b[^.!?\n]*", re.I)),
    ("garantia", "GUARANTEE",
     re.compile(r"[^.!?\n]*\b(?:garanti[ad]|garantimos|devolvemos|reembolso|"
                r"dinheiro\s+de\s+volta|sem\s+risco)\b[^.!?\n]*", re.I)),
    ("depoimento", "TESTIMONIAL",
     re.compile(r"[“\"][^”\"\n]{20,}[”\"]\s*[—\-–]\s*\w+", re.M)),
    ("superlativo", "COMPARISON",
     re.compile(r"[^.!?\n]*\b(?:o\s+melhor|a\s+melhor|numero\s+1|n[ºo°]\s*1|"
                r"lider\s+de\s+mercado|unico\s+no\s+mercado|"
                r"melhor\s+do\s+(?:mundo|brasil|mercado))\b[^.!?\n]*", re.I)),
    ("escassez", "FACTUAL",
     re.compile(r"[^.!?\n]*\b(?:ultimas?\s+vagas?|restam?\s+\d+|so\s+hoje|"
                r"ultimo\s+dia|vagas?\s+limitadas?)\b[^.!?\n]*", re.I)),
)


def detectar(texto: str) -> list[Deteccao]:
    """Encontra trechos que fazem alegacao verificavel.

    Args:
        texto: copy a inspecionar.

    Returns:
        Deteccoes ordenadas pela posicao no texto. Trechos sobrepostos sao
        mantidos: o mesmo periodo pode fazer duas alegacoes distintas.
    """
    achados: list[Deteccao] = []
    for regra, tipo, padrao in _REGRAS:
        for casamento in padrao.finditer(texto or ""):
            trecho = casamento.group(0).strip()
            if trecho:
                achados.append(Deteccao(trecho=trecho, tipo=tipo, regra=regra,
                                        inicio=casamento.start()))
    return sorted(achados, key=lambda d: (d.inicio, d.regra))


@dataclass
class ResultadoGate:
    """Veredito de publicacao para um texto."""

    pode_publicar: bool
    deteccoes: list[Deteccao] = field(default_factory=list)
    lastreadas: list[dict[str, Any]] = field(default_factory=list)
    bloqueios: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_publish": self.pode_publicar,
            "detections": [d.to_dict() for d in self.deteccoes],
            "backed": self.lastreadas,
            "blockers": self.bloqueios,
        }


def _normalizar(texto: str) -> str:
    """Forma comparavel: minusculas, espacos colapsados, sem pontuacao de borda."""
    return re.sub(r"\s+", " ", (texto or "").strip().lower()).strip(" .,;:!?\"'“”")


class ClaimRegistry:
    """Registro de alegacoes aprovadas, com gate de publicacao."""

    def __init__(self, caminho: Path | None = None) -> None:
        self.caminho = caminho
        self._claims: dict[str, dict[str, Any]] = {}
        if caminho and Path(caminho).exists():
            self._carregar()

    def _carregar(self) -> None:
        try:
            dados = json.loads(Path(self.caminho).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Registry ilegivel nao libera publicacao: fica vazio e tudo bloqueia.
            return
        for claim in dados.get("claims", []):
            self._claims[claim["claim_id"]] = claim

    def salvar(self) -> None:
        """Persiste o registry de forma atomica."""
        if not self.caminho:
            return
        alvo = Path(self.caminho)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        tmp = alvo.with_suffix(".tmp")
        tmp.write_text(json.dumps({"claims": list(self._claims.values())},
                                  indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(alvo)

    def registrar(self, *, tenant_id: str, exact_text: str, claim_type: str,
                  risk_class: str, funnel_ids: list[str], locales: list[str],
                  evidence_ids: list[str],
                  valid_until: str | None = None) -> dict[str, Any]:
        """Registra uma alegacao em DRAFT. Aprovacao e passo separado.

        Raises:
            ViolacaoDeContrato: payload fora de ``claim.schema.json``.
        """
        agora = policy.agora_iso()
        claim = {
            "claim_id": ids.novo_id("claim"),
            "tenant_id": tenant_id,
            "exact_text": exact_text,
            "claim_type": claim_type,
            "risk_class": risk_class,
            "scope": {"funnel_ids": list(funnel_ids), "locales": list(locales)},
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "status": "DRAFT",
            "approved_by": None,
            "valid_from": agora,
            "valid_until": valid_until,
            "created_at": agora,
            "updated_at": agora,
        }
        contracts.get("claim").exigir(claim)
        self._claims[claim["claim_id"]] = claim
        self.salvar()
        return claim

    def aprovar(self, claim_id: str, aprovador: str) -> dict[str, Any]:
        """Aprova uma alegacao.

        Segregacao de funcoes: quem aprova precisa ser nomeado, e o nome fica
        no registro. Alegacao de risco HIGH ou CRITICAL nao pode ser aprovada
        sem evidencia — o contrato ja exige ao menos uma.

        Raises:
            KeyError: alegacao inexistente.
            ValueError: aprovador vazio ou alegacao em estado nao aprovavel.
        """
        claim = self._claims.get(claim_id)
        if claim is None:
            raise KeyError(f"claim desconhecida: {claim_id}")
        if not aprovador or len(aprovador) < 3:
            raise ValueError("aprovacao exige identificar quem aprova")
        if claim["status"] in ("REVOKED", "REJECTED"):
            raise ValueError(f"claim em {claim['status']} nao pode ser aprovada")

        claim = dict(claim)
        claim.update({"status": "APPROVED", "approved_by": aprovador,
                      "updated_at": policy.agora_iso()})
        contracts.get("claim").exigir(claim)
        self._claims[claim_id] = claim
        self.salvar()
        return claim

    def revogar(self, claim_id: str, motivo: str) -> dict[str, Any]:
        """Revoga uma alegacao; o efeito e imediato no gate."""
        claim = dict(self._claims[claim_id])
        claim.update({"status": "REVOKED", "updated_at": policy.agora_iso()})
        contracts.get("claim").exigir(claim)
        self._claims[claim_id] = claim
        self.salvar()
        return claim

    def vigentes(self, funnel_id: str, locale: str,
                 em: str | None = None) -> list[dict[str, Any]]:
        """Alegacoes aprovadas, dentro da validade e do escopo pedido."""
        instante = em or policy.agora_iso()
        vigentes = []
        for claim in self._claims.values():
            if claim["status"] != "APPROVED":
                continue
            escopo = claim["scope"]
            if funnel_id not in escopo["funnel_ids"]:
                continue
            if locale not in escopo["locales"]:
                continue
            if claim["valid_from"] > instante:
                continue
            if claim.get("valid_until") and claim["valid_until"] < instante:
                continue
            vigentes.append(claim)
        return vigentes

    def avaliar_publicacao(self, texto: str, *, funnel_id: str,
                           locale: str = "pt-BR",
                           em: str | None = None) -> ResultadoGate:
        """Decide se um texto pode ser publicado.

        Cada trecho detectado precisa casar com o ``exact_text`` de uma
        alegacao vigente. O casamento e por conteudo normalizado: a alegacao
        aprovada precisa aparecer no trecho, o que impede aprovar "40%" e
        publicar "400%".

        Returns:
            O veredito, com o que foi detectado, o que tem lastro e o que bloqueia.
        """
        deteccoes = detectar(texto)
        if not deteccoes:
            return ResultadoGate(pode_publicar=True)

        aprovadas = self.vigentes(funnel_id, locale, em)
        indice = [(_normalizar(c["exact_text"]), c) for c in aprovadas]

        lastreadas: list[dict[str, Any]] = []
        bloqueios: list[str] = []

        for deteccao in deteccoes:
            alvo = _normalizar(deteccao.trecho)
            casada = next((c for texto_claim, c in indice
                           if texto_claim and texto_claim in alvo), None)
            if casada is None:
                bloqueios.append(
                    f"[{deteccao.regra}] alegacao sem lastro aprovado: "
                    f"\"{deteccao.trecho[:110]}\"")
                continue
            if casada["claim_type"] != deteccao.tipo:
                bloqueios.append(
                    f"[{deteccao.regra}] alegacao lastreada como "
                    f"{casada['claim_type']}, mas o texto faz alegacao "
                    f"{deteccao.tipo}: \"{deteccao.trecho[:80]}\"")
                continue
            lastreadas.append({"detection": deteccao.to_dict(),
                               "claim_id": casada["claim_id"]})

        return ResultadoGate(pode_publicar=not bloqueios, deteccoes=deteccoes,
                             lastreadas=lastreadas, bloqueios=bloqueios)
