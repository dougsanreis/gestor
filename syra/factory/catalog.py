"""Catalogo de capacidades: implementacoes reais, nunca esqueletos.

Cada entrada carrega o codigo da funcao, os testes que a exercitam e exemplos
executaveis. Isso e o piso deterministico da fabrica: mesmo sem nenhum modelo
de linguagem disponivel, o pipeline entrega software que roda, com testes que
falham de verdade quando a implementacao esta errada.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    """Uma funcao pronta para producao com testes e exemplos associados."""

    name: str
    summary: str
    signature: str
    returns: str
    keywords: tuple[str, ...]
    module: str
    source: str
    tests: str
    examples: tuple[tuple[str, str], ...] = ()


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        name="validar_cpf",
        summary="Valida um CPF brasileiro conferindo os dois digitos verificadores.",
        signature="validar_cpf(cpf: str) -> bool",
        returns="True quando o CPF e estruturalmente valido.",
        keywords=("cpf", "documento", "cadastro", "matricula", "aluno", "escolar",
                  "validacao", "identidade"),
        module="validacao",
        source='''def validar_cpf(cpf: str) -> bool:
    """Valida um CPF brasileiro conferindo os dois digitos verificadores.

    A validacao e puramente estrutural: confirma o algoritmo de modulo 11 e
    rejeita sequencias repetidas. Nao consulta nenhuma base externa.

    Args:
        cpf: CPF com ou sem pontuacao.

    Returns:
        True quando os digitos verificadores conferem.
    """
    digitos = [int(c) for c in str(cpf) if c.isdigit()]
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False

    for corte in (9, 10):
        peso_inicial = corte + 1
        soma = sum(d * (peso_inicial - i) for i, d in enumerate(digitos[:corte]))
        verificador = (soma * 10) % 11
        if verificador == 10:
            verificador = 0
        if verificador != digitos[corte]:
            return False
    return True
''',
        tests='''def test_validar_cpf_aceita_cpf_valido():
    assert validar_cpf("529.982.247-25") is True


def test_validar_cpf_aceita_sem_pontuacao():
    assert validar_cpf("52998224725") is True


def test_validar_cpf_rejeita_digito_verificador_errado():
    assert validar_cpf("529.982.247-26") is False


def test_validar_cpf_rejeita_sequencia_repetida():
    assert validar_cpf("111.111.111-11") is False


def test_validar_cpf_rejeita_tamanho_invalido():
    assert validar_cpf("1234") is False
    assert validar_cpf("") is False
''',
        examples=(("validar_cpf('529.982.247-25')", "True"),
                  ("validar_cpf('111.111.111-11')", "False")),
    ),
    Capability(
        name="validar_email",
        summary="Valida o formato de um endereco de e-mail.",
        signature="validar_email(email: str) -> bool",
        returns="True quando o formato do endereco e aceitavel.",
        keywords=("email", "contato", "cadastro", "responsavel", "usuario", "login",
                  "validacao"),
        module="validacao",
        source='''def validar_email(email: str) -> bool:
    """Valida o formato de um endereco de e-mail.

    Aplica uma verificacao estrutural conservadora: parte local nao vazia,
    dominio com ao menos um ponto e sufixo alfabetico de dois ou mais caracteres.

    Args:
        email: endereco a verificar.

    Returns:
        True quando o formato e aceitavel.
    """
    texto = str(email).strip()
    if not texto or texto.count("@") != 1 or " " in texto:
        return False

    local, _, dominio = texto.partition("@")
    if not local or local.startswith(".") or local.endswith("."):
        return False
    if ".." in texto or "." not in dominio:
        return False

    rotulos = dominio.split(".")
    if any(not rotulo for rotulo in rotulos):
        return False
    return len(rotulos[-1]) >= 2 and rotulos[-1].isalpha()
''',
        tests='''def test_validar_email_aceita_endereco_comum():
    assert validar_email("aluno@escola.com.br") is True


def test_validar_email_rejeita_sem_arroba():
    assert validar_email("alunoescola.com") is False


def test_validar_email_rejeita_dominio_sem_ponto():
    assert validar_email("aluno@escola") is False


def test_validar_email_rejeita_espacos_e_vazio():
    assert validar_email("alu no@escola.com") is False
    assert validar_email("") is False
''',
        examples=(("validar_email('aluno@escola.com.br')", "True"),
                  ("validar_email('aluno@escola')", "False")),
    ),
    Capability(
        name="normalizar_nome",
        summary="Normaliza nomes proprios respeitando particulas em minusculas.",
        signature="normalizar_nome(nome: str) -> str",
        returns="Nome com capitalizacao consistente e espacos colapsados.",
        keywords=("nome", "aluno", "professor", "cadastro", "texto", "normalizacao",
                  "pessoa"),
        module="texto",
        source='''_PARTICULAS = {"da", "de", "do", "das", "dos", "e", "di", "du", "van", "von"}


def normalizar_nome(nome: str) -> str:
    """Normaliza nomes proprios respeitando particulas em minusculas.

    Colapsa espacos, capitaliza cada palavra e mantem particulas como "de" e
    "da" em minuscula, exceto quando iniciam o nome.

    Args:
        nome: nome bruto informado pelo usuario.

    Returns:
        Nome normalizado; string vazia quando a entrada nao tem conteudo.
    """
    palavras = str(nome).split()
    if not palavras:
        return ""

    resultado = []
    for indice, palavra in enumerate(palavras):
        minuscula = palavra.lower()
        if indice > 0 and minuscula in _PARTICULAS:
            resultado.append(minuscula)
        else:
            resultado.append(minuscula[:1].upper() + minuscula[1:])
    return " ".join(resultado)
''',
        tests='''def test_normalizar_nome_capitaliza_palavras():
    assert normalizar_nome("maria silva") == "Maria Silva"


def test_normalizar_nome_mantem_particulas_minusculas():
    assert normalizar_nome("JOAO DA SILVA DOS SANTOS") == "Joao da Silva dos Santos"


def test_normalizar_nome_colapsa_espacos():
    assert normalizar_nome("  ana   paula  ") == "Ana Paula"


def test_normalizar_nome_vazio_retorna_vazio():
    assert normalizar_nome("   ") == ""
''',
        examples=(("normalizar_nome('JOAO DA SILVA')", "'Joao da Silva'"),),
    ),
    Capability(
        name="media_ponderada",
        summary="Calcula a media ponderada de notas a partir de pesos.",
        signature="media_ponderada(notas: Sequence[float], pesos: Sequence[float]) -> float",
        returns="Media ponderada arredondada em duas casas.",
        keywords=("nota", "media", "boletim", "avaliacao", "escolar", "calculo",
                  "ponderada", "desempenho"),
        module="notas",
        source='''def media_ponderada(notas, pesos):
    """Calcula a media ponderada de notas a partir de pesos.

    Args:
        notas: sequencia de notas obtidas.
        pesos: sequencia de pesos, do mesmo tamanho de ``notas``.

    Returns:
        Media ponderada arredondada em duas casas decimais.

    Raises:
        ValueError: quando as sequencias tem tamanhos diferentes, estao vazias
            ou a soma dos pesos e zero.
    """
    notas = list(notas)
    pesos = list(pesos)
    if not notas or len(notas) != len(pesos):
        raise ValueError("notas e pesos devem ter o mesmo tamanho e nao ser vazios")

    total_pesos = sum(pesos)
    if total_pesos == 0:
        raise ValueError("a soma dos pesos nao pode ser zero")

    acumulado = sum(nota * peso for nota, peso in zip(notas, pesos))
    return round(acumulado / total_pesos, 2)
''',
        tests='''import pytest


def test_media_ponderada_calcula_valor_esperado():
    assert media_ponderada([8.0, 6.0], [2, 1]) == 7.33


def test_media_ponderada_com_pesos_iguais_equivale_a_media_simples():
    assert media_ponderada([10.0, 5.0], [1, 1]) == 7.5


def test_media_ponderada_rejeita_tamanhos_diferentes():
    with pytest.raises(ValueError):
        media_ponderada([8.0, 6.0], [1])


def test_media_ponderada_rejeita_soma_de_pesos_zero():
    with pytest.raises(ValueError):
        media_ponderada([8.0], [0])
''',
        examples=(("media_ponderada([8.0, 6.0], [2, 1])", "7.33"),),
    ),
    Capability(
        name="situacao_do_aluno",
        summary="Classifica a situacao do aluno a partir da media e da frequencia.",
        signature="situacao_do_aluno(media: float, frequencia: float) -> str",
        returns="APROVADO, RECUPERACAO, REPROVADO_POR_FALTA ou REPROVADO.",
        keywords=("aluno", "aprovacao", "situacao", "boletim", "escolar", "frequencia",
                  "reprovacao", "recuperacao"),
        module="notas",
        source='''MEDIA_APROVACAO = 7.0
MEDIA_RECUPERACAO = 5.0
FREQUENCIA_MINIMA = 75.0


def situacao_do_aluno(media: float, frequencia: float) -> str:
    """Classifica a situacao do aluno a partir da media e da frequencia.

    A reprovacao por falta tem precedencia sobre a nota: um aluno abaixo da
    frequencia minima reprova mesmo com media alta.

    Args:
        media: media final do aluno, de 0 a 10.
        frequencia: percentual de presenca, de 0 a 100.

    Returns:
        Uma das situacoes: ``APROVADO``, ``RECUPERACAO``,
        ``REPROVADO_POR_FALTA`` ou ``REPROVADO``.

    Raises:
        ValueError: quando media ou frequencia estao fora do intervalo valido.
    """
    if not 0 <= media <= 10:
        raise ValueError("media deve estar entre 0 e 10")
    if not 0 <= frequencia <= 100:
        raise ValueError("frequencia deve estar entre 0 e 100")

    if frequencia < FREQUENCIA_MINIMA:
        return "REPROVADO_POR_FALTA"
    if media >= MEDIA_APROVACAO:
        return "APROVADO"
    if media >= MEDIA_RECUPERACAO:
        return "RECUPERACAO"
    return "REPROVADO"
''',
        tests='''import pytest


def test_situacao_aprovado():
    assert situacao_do_aluno(8.0, 90.0) == "APROVADO"


def test_situacao_recuperacao():
    assert situacao_do_aluno(6.0, 90.0) == "RECUPERACAO"


def test_situacao_reprovado_por_nota():
    assert situacao_do_aluno(3.0, 95.0) == "REPROVADO"


def test_falta_tem_precedencia_sobre_nota_alta():
    assert situacao_do_aluno(9.5, 50.0) == "REPROVADO_POR_FALTA"


def test_situacao_rejeita_valores_fora_do_intervalo():
    with pytest.raises(ValueError):
        situacao_do_aluno(11.0, 90.0)
    with pytest.raises(ValueError):
        situacao_do_aluno(7.0, 120.0)
''',
        examples=(("situacao_do_aluno(9.5, 50.0)", "'REPROVADO_POR_FALTA'"),),
    ),
    Capability(
        name="taxa_de_frequencia",
        summary="Calcula o percentual de presenca a partir de aulas dadas e faltas.",
        signature="taxa_de_frequencia(aulas: int, faltas: int) -> float",
        returns="Percentual de presenca de 0 a 100, com duas casas.",
        keywords=("frequencia", "presenca", "falta", "chamada", "escolar", "aula",
                  "percentual"),
        module="frequencia",
        source='''def taxa_de_frequencia(aulas: int, faltas: int) -> float:
    """Calcula o percentual de presenca a partir de aulas dadas e faltas.

    Args:
        aulas: total de aulas ministradas no periodo.
        faltas: total de ausencias registradas.

    Returns:
        Percentual de presenca de 0 a 100, arredondado em duas casas.

    Raises:
        ValueError: quando os valores sao negativos ou as faltas superam as aulas.
    """
    if aulas < 0 or faltas < 0:
        raise ValueError("aulas e faltas nao podem ser negativas")
    if faltas > aulas:
        raise ValueError("faltas nao podem exceder o total de aulas")
    if aulas == 0:
        return 0.0
    return round(100.0 * (aulas - faltas) / aulas, 2)
''',
        tests='''import pytest


def test_taxa_de_frequencia_sem_faltas():
    assert taxa_de_frequencia(20, 0) == 100.0


def test_taxa_de_frequencia_com_faltas():
    assert taxa_de_frequencia(40, 10) == 75.0


def test_taxa_de_frequencia_sem_aulas_retorna_zero():
    assert taxa_de_frequencia(0, 0) == 0.0


def test_taxa_de_frequencia_rejeita_faltas_maiores_que_aulas():
    with pytest.raises(ValueError):
        taxa_de_frequencia(10, 11)


def test_taxa_de_frequencia_rejeita_negativos():
    with pytest.raises(ValueError):
        taxa_de_frequencia(-1, 0)
''',
        examples=(("taxa_de_frequencia(40, 10)", "75.0"),),
    ),
    Capability(
        name="gerar_slug",
        summary="Converte um titulo em identificador seguro para URLs.",
        signature="gerar_slug(texto: str, limite: int = 60) -> str",
        returns="Slug em minusculas, sem acentos e separado por hifens.",
        keywords=("slug", "url", "titulo", "texto", "identificador", "link", "seo"),
        module="texto",
        source='''import unicodedata


def gerar_slug(texto: str, limite: int = 60) -> str:
    """Converte um titulo em identificador seguro para URLs.

    Remove acentos, troca separadores por hifen e colapsa repeticoes.

    Args:
        texto: titulo de origem.
        limite: numero maximo de caracteres do slug.

    Returns:
        Slug em minusculas; string vazia quando nao sobra nenhum caractere util.
    """
    normalizado = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in normalizado if not unicodedata.combining(c))

    partes = []
    for caractere in sem_acento.lower():
        if caractere.isalnum():
            partes.append(caractere)
        elif partes and partes[-1] != "-":
            partes.append("-")

    slug = "".join(partes).strip("-")
    if limite > 0:
        slug = slug[:limite].strip("-")
    return slug
''',
        tests='''def test_gerar_slug_remove_acentos_e_espacos():
    assert gerar_slug("Gestao Escolar Basica") == "gestao-escolar-basica"


def test_gerar_slug_colapsa_separadores():
    assert gerar_slug("turma --- 2026 / A") == "turma-2026-a"


def test_gerar_slug_respeita_limite():
    assert gerar_slug("abcdefghij", limite=4) == "abcd"


def test_gerar_slug_vazio():
    assert gerar_slug("!!!") == ""
''',
        examples=(("gerar_slug('Gestao Escolar Basica')", "'gestao-escolar-basica'"),),
    ),
    Capability(
        name="mascarar_dado_sensivel",
        summary="Mascara um dado sensivel preservando apenas os ultimos digitos.",
        signature="mascarar_dado_sensivel(valor: str, visiveis: int = 4) -> str",
        returns="Valor mascarado, seguro para log e para tela.",
        keywords=("lgpd", "privacidade", "seguranca", "mascara", "dado", "sensivel",
                  "log", "protecao"),
        module="seguranca",
        source='''def mascarar_dado_sensivel(valor: str, visiveis: int = 4) -> str:
    """Mascara um dado sensivel preservando apenas os ultimos digitos.

    Util para exibir documentos e telefones em tela ou em log sem expor o
    valor completo.

    Args:
        valor: dado original.
        visiveis: quantos caracteres finais permanecem legiveis.

    Returns:
        Valor mascarado; totalmente mascarado quando e curto demais para
        revelar qualquer parte com seguranca.
    """
    texto = str(valor)
    if visiveis < 0:
        raise ValueError("visiveis nao pode ser negativo")
    if not texto:
        return ""
    if visiveis == 0 or len(texto) <= visiveis:
        return "*" * len(texto)
    return "*" * (len(texto) - visiveis) + texto[-visiveis:]
''',
        tests='''import pytest


def test_mascarar_preserva_ultimos_digitos():
    assert mascarar_dado_sensivel("52998224725") == "*******4725"


def test_mascarar_valor_curto_fica_totalmente_oculto():
    assert mascarar_dado_sensivel("123", visiveis=4) == "***"


def test_mascarar_com_zero_visiveis():
    assert mascarar_dado_sensivel("abcd", visiveis=0) == "****"


def test_mascarar_vazio():
    assert mascarar_dado_sensivel("") == ""


def test_mascarar_rejeita_visiveis_negativo():
    with pytest.raises(ValueError):
        mascarar_dado_sensivel("abcd", visiveis=-1)
''',
        examples=(("mascarar_dado_sensivel('52998224725')", "'*******4725'"),),
    ),
    Capability(
        name="paginar",
        summary="Divide uma colecao em paginas e descreve a navegacao.",
        signature="paginar(itens: Sequence, pagina: int = 1, tamanho: int = 20) -> dict",
        returns="Dicionario com itens da pagina e metadados de navegacao.",
        keywords=("paginacao", "listagem", "api", "consulta", "relatorio", "dashboard",
                  "pagina"),
        module="consulta",
        source='''def paginar(itens, pagina: int = 1, tamanho: int = 20) -> dict:
    """Divide uma colecao em paginas e descreve a navegacao.

    Args:
        itens: sequencia completa de registros.
        pagina: numero da pagina desejada, comecando em 1.
        tamanho: quantidade de itens por pagina.

    Returns:
        Dicionario com ``itens``, ``pagina``, ``tamanho``, ``total``,
        ``total_paginas``, ``tem_proxima`` e ``tem_anterior``.

    Raises:
        ValueError: quando pagina ou tamanho sao menores que 1.
    """
    if pagina < 1:
        raise ValueError("pagina deve ser maior ou igual a 1")
    if tamanho < 1:
        raise ValueError("tamanho deve ser maior ou igual a 1")

    dados = list(itens)
    total = len(dados)
    total_paginas = max(1, -(-total // tamanho))
    inicio = (pagina - 1) * tamanho
    recorte = dados[inicio:inicio + tamanho]

    return {
        "itens": recorte,
        "pagina": pagina,
        "tamanho": tamanho,
        "total": total,
        "total_paginas": total_paginas,
        "tem_proxima": pagina < total_paginas,
        "tem_anterior": pagina > 1,
    }
''',
        tests='''import pytest


def test_paginar_primeira_pagina():
    resultado = paginar(list(range(10)), pagina=1, tamanho=4)
    assert resultado["itens"] == [0, 1, 2, 3]
    assert resultado["total_paginas"] == 3
    assert resultado["tem_proxima"] is True
    assert resultado["tem_anterior"] is False


def test_paginar_ultima_pagina_parcial():
    resultado = paginar(list(range(10)), pagina=3, tamanho=4)
    assert resultado["itens"] == [8, 9]
    assert resultado["tem_proxima"] is False


def test_paginar_colecao_vazia():
    resultado = paginar([], pagina=1, tamanho=5)
    assert resultado["itens"] == []
    assert resultado["total_paginas"] == 1


def test_paginar_rejeita_parametros_invalidos():
    with pytest.raises(ValueError):
        paginar([1, 2], pagina=0)
    with pytest.raises(ValueError):
        paginar([1, 2], tamanho=0)
''',
        examples=(("paginar([1, 2, 3], pagina=1, tamanho=2)['itens']", "[1, 2]"),),
    ),
    Capability(
        name="filtrar_registros",
        summary="Filtra registros por busca textual em campos escolhidos.",
        signature="filtrar_registros(registros: Iterable[dict], termo: str, campos: Sequence[str]) -> list[dict]",
        returns="Lista dos registros cujo termo aparece em algum campo.",
        keywords=("busca", "filtro", "pesquisa", "registro", "consulta", "listagem",
                  "dashboard"),
        module="consulta",
        source='''def filtrar_registros(registros, termo: str, campos):
    """Filtra registros por busca textual em campos escolhidos.

    A comparacao ignora maiusculas e espacos nas bordas. Termo vazio devolve
    todos os registros, o que mantem o comportamento previsivel em telas de
    busca incremental.

    Args:
        registros: colecao de dicionarios.
        termo: texto procurado.
        campos: nomes dos campos a inspecionar.

    Returns:
        Lista de registros correspondentes, na ordem original.
    """
    alvo = str(termo).strip().lower()
    lista = list(registros)
    if not alvo:
        return lista

    campos = list(campos)
    encontrados = []
    for registro in lista:
        for campo in campos:
            valor = registro.get(campo)
            if valor is not None and alvo in str(valor).lower():
                encontrados.append(registro)
                break
    return encontrados
''',
        tests='''ALUNOS = [
    {"nome": "Maria Silva", "turma": "3A"},
    {"nome": "Joao Souza", "turma": "3B"},
    {"nome": "Ana Silveira", "turma": "2A"},
]


def test_filtrar_registros_encontra_por_nome():
    achados = filtrar_registros(ALUNOS, "silv", ["nome"])
    assert [a["nome"] for a in achados] == ["Maria Silva", "Ana Silveira"]


def test_filtrar_registros_termo_vazio_devolve_tudo():
    assert filtrar_registros(ALUNOS, "  ", ["nome"]) == ALUNOS


def test_filtrar_registros_busca_em_multiplos_campos():
    achados = filtrar_registros(ALUNOS, "3b", ["nome", "turma"])
    assert len(achados) == 1
    assert achados[0]["turma"] == "3B"


def test_filtrar_registros_sem_correspondencia():
    assert filtrar_registros(ALUNOS, "inexistente", ["nome"]) == []


def test_filtrar_registros_ignora_campo_ausente():
    assert filtrar_registros([{"nome": "X"}], "y", ["email"]) == []
''',
        examples=(("len(filtrar_registros([{'n': 'ana'}], 'an', ['n']))", "1"),),
    ),
    Capability(
        name="resumir_indicadores",
        summary="Resume uma serie numerica em indicadores de dashboard.",
        signature="resumir_indicadores(valores: Sequence[float]) -> dict",
        returns="Dicionario com total, media, minimo, maximo e mediana.",
        keywords=("dashboard", "indicador", "metrica", "relatorio", "estatistica",
                  "resumo", "analise", "kpi"),
        module="indicadores",
        source='''import statistics


def resumir_indicadores(valores) -> dict:
    """Resume uma serie numerica em indicadores de dashboard.

    Args:
        valores: sequencia de numeros observados.

    Returns:
        Dicionario com ``quantidade``, ``total``, ``media``, ``minimo``,
        ``maximo`` e ``mediana``. Series vazias devolvem zeros, evitando que a
        camada de apresentacao precise tratar ausencia de dados.
    """
    dados = [float(v) for v in valores]
    if not dados:
        return {"quantidade": 0, "total": 0.0, "media": 0.0,
                "minimo": 0.0, "maximo": 0.0, "mediana": 0.0}

    return {
        "quantidade": len(dados),
        "total": round(sum(dados), 2),
        "media": round(sum(dados) / len(dados), 2),
        "minimo": round(min(dados), 2),
        "maximo": round(max(dados), 2),
        "mediana": round(statistics.median(dados), 2),
    }
''',
        tests='''def test_resumir_indicadores_calcula_metricas():
    resumo = resumir_indicadores([10, 20, 30])
    assert resumo["quantidade"] == 3
    assert resumo["total"] == 60.0
    assert resumo["media"] == 20.0
    assert resumo["mediana"] == 20.0


def test_resumir_indicadores_minimo_e_maximo():
    resumo = resumir_indicadores([5.5, 1.25, 9.75])
    assert resumo["minimo"] == 1.25
    assert resumo["maximo"] == 9.75


def test_resumir_indicadores_serie_vazia():
    resumo = resumir_indicadores([])
    assert resumo["quantidade"] == 0
    assert resumo["media"] == 0.0
''',
        examples=(("resumir_indicadores([10, 20, 30])['media']", "20.0"),),
    ),
    Capability(
        name="formatar_moeda_brl",
        summary="Formata um valor numerico como moeda brasileira.",
        signature="formatar_moeda_brl(valor: float) -> str",
        returns="Texto no formato R$ 1.234,56.",
        keywords=("moeda", "financeiro", "mensalidade", "pagamento", "cobranca",
                  "real", "formatacao", "preco"),
        module="financeiro",
        source='''def formatar_moeda_brl(valor: float) -> str:
    """Formata um valor numerico como moeda brasileira.

    Nao depende de locale do sistema, o que mantem a saida identica em
    qualquer maquina ou container.

    Args:
        valor: quantia a formatar.

    Returns:
        Texto no formato ``R$ 1.234,56``, com sinal negativo antes do simbolo.
    """
    numero = float(valor)
    negativo = numero < 0
    inteiro, _, centavos = f"{abs(numero):.2f}".partition(".")

    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)

    texto = f"R$ {'.'.join(grupos)},{centavos}"
    return f"-{texto}" if negativo else texto
''',
        tests='''def test_formatar_moeda_brl_com_milhar():
    assert formatar_moeda_brl(1234.56) == "R$ 1.234,56"


def test_formatar_moeda_brl_valor_pequeno():
    assert formatar_moeda_brl(9.5) == "R$ 9,50"


def test_formatar_moeda_brl_zero():
    assert formatar_moeda_brl(0) == "R$ 0,00"


def test_formatar_moeda_brl_negativo():
    assert formatar_moeda_brl(-1500) == "-R$ 1.500,00"


def test_formatar_moeda_brl_milhao():
    assert formatar_moeda_brl(1234567.89) == "R$ 1.234.567,89"
''',
        examples=(("formatar_moeda_brl(1234.56)", "'R$ 1.234,56'"),),
    ),
    Capability(
        name="dividir_em_lotes",
        summary="Divide uma colecao em lotes de tamanho fixo.",
        signature="dividir_em_lotes(itens: Iterable, tamanho: int) -> list[list]",
        returns="Lista de lotes; o ultimo pode ser menor.",
        keywords=("lote", "batch", "processamento", "importacao", "fila", "divisao",
                  "chunk"),
        module="processamento",
        source='''def dividir_em_lotes(itens, tamanho: int):
    """Divide uma colecao em lotes de tamanho fixo.

    Args:
        itens: colecao de origem.
        tamanho: quantidade maxima de elementos por lote.

    Returns:
        Lista de lotes preservando a ordem; o ultimo lote pode ser menor.

    Raises:
        ValueError: quando ``tamanho`` e menor que 1.
    """
    if tamanho < 1:
        raise ValueError("tamanho do lote deve ser maior ou igual a 1")
    dados = list(itens)
    return [dados[i:i + tamanho] for i in range(0, len(dados), tamanho)]
''',
        tests='''import pytest


def test_dividir_em_lotes_exatos():
    assert dividir_em_lotes([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_dividir_em_lotes_ultimo_menor():
    assert dividir_em_lotes([1, 2, 3], 2) == [[1, 2], [3]]


def test_dividir_em_lotes_colecao_vazia():
    assert dividir_em_lotes([], 3) == []


def test_dividir_em_lotes_rejeita_tamanho_invalido():
    with pytest.raises(ValueError):
        dividir_em_lotes([1], 0)
''',
        examples=(("dividir_em_lotes([1, 2, 3], 2)", "[[1, 2], [3]]"),),
    ),
    Capability(
        name="remover_duplicados",
        summary="Remove duplicados preservando a ordem de primeira aparicao.",
        signature="remover_duplicados(itens: Iterable, chave: str | None = None) -> list",
        returns="Lista sem duplicados, na ordem original.",
        keywords=("duplicado", "deduplicacao", "importacao", "limpeza", "dados",
                  "unico", "higienizacao"),
        module="processamento",
        source='''def remover_duplicados(itens, chave: str | None = None):
    """Remove duplicados preservando a ordem de primeira aparicao.

    Args:
        itens: colecao de origem.
        chave: quando informada, os itens sao dicionarios e a comparacao usa
            o valor desse campo.

    Returns:
        Lista sem duplicados, mantendo a primeira ocorrencia de cada valor.
    """
    vistos = set()
    resultado = []
    for item in itens:
        marcador = item.get(chave) if chave is not None else item
        try:
            hash(marcador)
        except TypeError:
            marcador = repr(marcador)
        if marcador in vistos:
            continue
        vistos.add(marcador)
        resultado.append(item)
    return resultado
''',
        tests='''def test_remover_duplicados_preserva_ordem():
    assert remover_duplicados([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_remover_duplicados_por_chave():
    registros = [{"id": 1, "n": "a"}, {"id": 1, "n": "b"}, {"id": 2, "n": "c"}]
    assert remover_duplicados(registros, chave="id") == [
        {"id": 1, "n": "a"},
        {"id": 2, "n": "c"},
    ]


def test_remover_duplicados_lista_vazia():
    assert remover_duplicados([]) == []


def test_remover_duplicados_aceita_itens_nao_hashaveis():
    assert remover_duplicados([[1], [1], [2]]) == [[1], [2]]
''',
        examples=(("remover_duplicados([3, 1, 3, 2, 1])", "[3, 1, 2]"),),
    ),
    Capability(
        name="variacao_percentual",
        summary="Calcula a variacao percentual entre dois valores.",
        signature="variacao_percentual(anterior: float, atual: float) -> float",
        returns="Variacao em pontos percentuais, com duas casas.",
        keywords=("variacao", "percentual", "crescimento", "comparacao", "metrica",
                  "evolucao", "tendencia"),
        module="indicadores",
        source='''def variacao_percentual(anterior: float, atual: float) -> float:
    """Calcula a variacao percentual entre dois valores.

    Args:
        anterior: valor do periodo base.
        atual: valor do periodo corrente.

    Returns:
        Variacao percentual arredondada em duas casas. Quando o valor base e
        zero, devolve 0.0 se nada mudou e 100.0 para qualquer crescimento,
        evitando divisao por zero na camada de apresentacao.
    """
    base = float(anterior)
    corrente = float(atual)
    if base == 0:
        return 0.0 if corrente == 0 else 100.0
    return round(100.0 * (corrente - base) / abs(base), 2)
''',
        tests='''def test_variacao_percentual_crescimento():
    assert variacao_percentual(100, 125) == 25.0


def test_variacao_percentual_queda():
    assert variacao_percentual(200, 150) == -25.0


def test_variacao_percentual_sem_mudanca():
    assert variacao_percentual(50, 50) == 0.0


def test_variacao_percentual_base_zero():
    assert variacao_percentual(0, 0) == 0.0
    assert variacao_percentual(0, 10) == 100.0
''',
        examples=(("variacao_percentual(100, 125)", "25.0"),),
    ),
)


def by_name(name: str) -> Capability | None:
    """Busca uma capacidade pelo nome exato."""
    for capability in CAPABILITIES:
        if capability.name == name:
            return capability
    return None
