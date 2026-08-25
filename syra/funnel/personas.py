"""Mapa de audiencia do nicho de vibe code.

Copy que converte nasce de dor especifica, nao de adjetivo. Cada persona aqui
carrega a dor na linguagem que a propria pessoa usa, a objecao que ela levanta
antes de comprar e o resultado que ela consegue descrever para um amigo. Os
geradores de copy consomem exatamente esses campos, o que impede texto generico.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class Dor:
    """Uma dor concreta, com o custo que ela impoe hoje."""

    id: str
    titulo: str
    fala_do_cliente: str
    custo: str
    intensidade: int  # 1 a 10, calibra a agitacao da copy
    frequencia: int   # 1 a 10, quantas pessoas do nicho sentem

    @property
    def prioridade(self) -> int:
        """Peso combinado usado para ranquear qual dor vira funil."""
        return self.intensidade * self.frequencia

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["prioridade"] = self.prioridade
        return data


@dataclass(frozen=True)
class Persona:
    """Segmento de audiencia com dores, objecoes e vocabulario proprios."""

    id: str
    nome: str
    nivel: str
    contexto: str
    dores: tuple[Dor, ...]
    objecoes: tuple[str, ...]
    resultado_desejado: str
    registro: str          # como a pessoa fala: direto, tecnico, cauteloso
    prova_que_convence: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["dores"] = [d.to_dict() for d in self.dores]
        return data


INICIANTE = Persona(
    id="iniciante",
    nome="Quem construiu a primeira coisa com IA e travou",
    nivel="iniciante",
    contexto=(
        "Descobriu que consegue construir software conversando com uma IA. "
        "Fez um app que funciona na propria maquina e agora quer que outras "
        "pessoas usem. Nao tem formacao em engenharia de software."
    ),
    dores=(
        Dor(
            id="demo_quebra",
            titulo="Funciona na demo, quebra com gente de verdade",
            fala_do_cliente=(
                "Na minha tela funciona. Mandei pra tres amigos testarem e "
                "quebrou em todos, cada um de um jeito diferente."
            ),
            custo="Nao consegue mostrar o que construiu sem passar vergonha.",
            intensidade=9,
            frequencia=9,
        ),
        Dor(
            id="loop_de_erro",
            titulo="A IA entra em loop e cada correcao quebra outra coisa",
            fala_do_cliente=(
                "Peco pra consertar, ela conserta, e ai quebra outra parte. "
                "Fico duas horas girando e volto pro mesmo erro do comeco."
            ),
            custo="Horas e creditos queimados sem avancar um passo.",
            intensidade=10,
            frequencia=8,
        ),
        Dor(
            id="nao_sabe_publicar",
            titulo="Nao sabe colocar no ar",
            fala_do_cliente=(
                "Eu tenho o codigo. Nao faco ideia de como transformar isso "
                "num link que eu mando pra alguem."
            ),
            custo="O projeto morre no computador, sem nunca virar produto.",
            intensidade=8,
            frequencia=9,
        ),
        Dor(
            id="medo_seguranca",
            titulo="Medo de ter deixado algo exposto",
            fala_do_cliente=(
                "Coloquei minha chave de API no codigo porque foi o que "
                "funcionou. Sei que ta errado, mas nao sei o certo."
            ),
            custo="Risco real de vazar chave, dado de cliente e conta.",
            intensidade=8,
            frequencia=7,
        ),
    ),
    objecoes=(
        "Vou precisar aprender a programar do zero pra isso funcionar?",
        "Ja comprei curso que era so teoria. Como sei que aqui e diferente?",
        "E se eu travar no meio? Fico sozinho de novo?",
        "Nao tenho tempo. Quanto isso vai me tomar por dia?",
    ),
    resultado_desejado=(
        "Ter um link que funciona, que aguenta outras pessoas usando, e saber "
        "o que fazer quando quebrar."
    ),
    registro="direto, sem jargao, com exemplo concreto antes da explicacao",
    prova_que_convence=(
        "Ver alguem no mesmo ponto que ele saindo do zero ao ar em poucos dias, "
        "com o passo a passo visivel."
    ),
)

INTERMEDIARIO = Persona(
    id="intermediario",
    nome="Quem ja entrega com IA e sofre com o que volta",
    nivel="intermediario",
    contexto=(
        "Ja usa IA para produzir codigo no dia a dia e entrega funcionalidade "
        "de verdade. O problema deixou de ser escrever e passou a ser confiar "
        "no que foi escrito."
    ),
    dores=(
        Dor(
            id="regressao_silenciosa",
            titulo="Nova funcionalidade quebra a antiga sem ninguem perceber",
            fala_do_cliente=(
                "Entrego uma coisa nova e uma semana depois descubro que "
                "quebrei outra que ja funcionava. Sempre pelo cliente."
            ),
            custo="Retrabalho constante e credibilidade corroida a cada entrega.",
            intensidade=9,
            frequencia=8,
        ),
        Dor(
            id="codigo_que_nao_entende",
            titulo="Mantem codigo que nao consegue explicar",
            fala_do_cliente=(
                "Funciona, mas se me perguntarem por que esta assim eu nao "
                "sei responder. Mexer da medo."
            ),
            custo="Cada mudanca vira aposta, e o medo trava a evolucao.",
            intensidade=8,
            frequencia=9,
        ),
        Dor(
            id="contexto_perdido",
            titulo="Projeto grande demais para o contexto da IA",
            fala_do_cliente=(
                "Passou de certo tamanho, a IA esquece metade do projeto e "
                "comeca a reescrever coisa que ja existia."
            ),
            custo="Duplicacao, inconsistencia e arquitetura que apodrece.",
            intensidade=8,
            frequencia=8,
        ),
    ),
    objecoes=(
        "Ja tenho meu jeito de trabalhar. Isso vai me atrasar?",
        "Preciso trocar de ferramenta ou funciona com o que ja uso?",
        "Escrever teste nao vai dobrar meu tempo de entrega?",
    ),
    resultado_desejado=(
        "Entregar rapido como hoje, mas com a certeza de que nada que ja "
        "funcionava quebrou."
    ),
    registro="tecnico e pratico, aceita nuance, rejeita promessa exagerada",
    prova_que_convence=(
        "Numero antes e depois: regressoes por entrega, tempo de revisao, "
        "cobertura real de teste."
    ),
)

AVANCADO = Persona(
    id="avancado",
    nome="Quem responde pelo que o time gera com IA",
    nivel="avancado",
    contexto=(
        "Lidera time ou produto. O time inteiro passou a gerar codigo com IA e "
        "o volume de codigo cresceu mais rapido que a capacidade de revisar."
    ),
    dores=(
        Dor(
            id="revisao_nao_escala",
            titulo="Revisao humana virou o gargalo",
            fala_do_cliente=(
                "O time gera em um dia o que eu levo uma semana pra revisar. "
                "Ou eu viro o gargalo, ou passa coisa sem revisao."
            ),
            custo="Ou a entrega para, ou a qualidade sai sem ninguem olhar.",
            intensidade=10,
            frequencia=7,
        ),
        Dor(
            id="sem_auditoria",
            titulo="Nao sabe dizer quem aprovou o que a IA escreveu",
            fala_do_cliente=(
                "Se cair uma auditoria e perguntarem qual criterio aprovou "
                "esse codigo, eu nao tenho resposta."
            ),
            custo="Exposicao regulatoria e risco que ninguem consegue medir.",
            intensidade=9,
            frequencia=6,
        ),
        Dor(
            id="qualidade_irregular",
            titulo="Qualidade varia por pessoa e por dia",
            fala_do_cliente=(
                "Duas pessoas do time usam a mesma ferramenta e entregam "
                "padroes completamente diferentes."
            ),
            custo="Base de codigo sem padrao, onboarding caro, bug recorrente.",
            intensidade=8,
            frequencia=8,
        ),
    ),
    objecoes=(
        "Isso vira mais um processo que o time vai ignorar?",
        "Como integra com o CI e o fluxo de revisao que ja temos?",
        "Qual o custo real de adocao para um time que ja esta atrasado?",
        "Que garantia existe de que a propria automacao nao vai afrouxar?",
    ),
    resultado_desejado=(
        "Volume de entrega da IA com criterio de aprovacao explicito, "
        "rastreavel e igual para todo mundo."
    ),
    registro="executivo e cetico, quer criterio, evidencia e custo de adocao",
    prova_que_convence=(
        "Politica de aprovacao versionada, trilha de auditoria e metrica de "
        "regressao antes e depois."
    ),
)

PERSONAS: tuple[Persona, ...] = (INICIANTE, INTERMEDIARIO, AVANCADO)


def por_id(persona_id: str) -> Persona | None:
    """Busca uma persona pelo identificador."""
    return next((p for p in PERSONAS if p.id == persona_id), None)


def dores_por_nivel(nivel: str | None = None) -> list[Dor]:
    """Lista as dores ordenadas por prioridade, opcionalmente filtrando o nivel.

    Args:
        nivel: ``iniciante``, ``intermediario``, ``avancado`` ou ``None`` para todos.

    Returns:
        Dores ordenadas da mais prioritaria para a menos prioritaria.
    """
    alvo = [p for p in PERSONAS if nivel is None or p.nivel == nivel]
    dores = [d for p in alvo for d in p.dores]
    return sorted(dores, key=lambda d: -d.prioridade)
