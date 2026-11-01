"""
Lógica do editor de acordes (sem janelas).

Aqui ficam as regras do programa: ler os acordes de um PDF, achar as pautas, escrever
acordes na página, transpor, montar a paleta de um tom e salvar/carregar o projeto.
Nada neste arquivo usa tkinter, então tudo pode ser testado sem abrir uma janela
e reaproveitado em outros programas.

Conceitos usados nos nomes:
  - "acorde" é um dicionário com texto, posição (x, y) e se veio do PDF original.
  - y é a linha de base do texto (onde "apoiam" as letras), em pontos (1 pt = 1/72 polegada).
"""

import json
import logging
import os
import re
import statistics
import tempfile
from pathlib import Path

import pymupdf

# ---------------------------------------------------------------
# Ajustes (pode mexer à vontade)
# ---------------------------------------------------------------
TAMANHO_ACORDE = 11.8     # tamanho padrão da letra do acorde (usado se o PDF não tiver acordes)
TAMANHOS = [8, 9, 10, 11, 12, 13, 14, 16, 18, 20]   # opções do menu "Fonte"
TAMANHO_SIMBOLO = 10      # tamanho do ♯ e do ♭ (para a letra no tamanho padrão; escala junto)
SUBIDA_SIMBOLO = 4.2      # o quanto o ♯ e o ♭ ficam elevados (também escala)
ALTURA_ACIMA = 10.5       # caixa do acorde: quanto sobe a partir da linha de base (tamanho padrão)
ALTURA_ABAIXO = 2.5       # caixa do acorde: quanto desce (tamanho padrão)
OFFSET_PAUTA = 8.0        # distância padrão do acorde até a 1ª linha da pauta (só usada se o
                          # PDF não tiver acordes para o programa aprender a distância certa)
RAIO_PAUTA = 26           # distância (em pontos) para o clique "grudar" numa pauta
RAIO_ENCAIXE = 22         # idem, para alinhar com acordes que já existiam no PDF
DISTANCIA_JUNTAR = 3.0    # distância máxima (pt) para juntar pedaços de um mesmo acorde

CAMINHOS_FONTE_SIMBOLOS = [
    r"C:\Windows\Fonts\seguisym.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]

# Um acorde é: letra A-G + (# ou b) + (m, maj, dim...) + número + (/baixo)
PADRAO_ACORDE = re.compile(
    r"^[A-G][#b]?(m|maj|min|dim|aug|sus|add)?\d*(/[A-G][#b]?)?$"
)

NOTAS_SUSTENIDO = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTAS_BEMOL = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
VALOR_NOTA = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

TONS = ["C", "G", "D", "A", "E", "B", "F#", "F", "Bb", "Eb", "Ab", "Db",
        "Am", "Em", "Bm", "F#m", "C#m", "G#m", "Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm"]
TONS_COM_BEMOL = {"F", "Bb", "Eb", "Ab", "Db", "Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm"}


# ===============================================================
# Fontes (para desenhar ♯ e ♭)
# ===============================================================
_fontes = {"prontas": False, "caminho": None, "objeto": None}


def achar_fonte_simbolos():
    for caminho in CAMINHOS_FONTE_SIMBOLOS:
        if os.path.exists(caminho):
            return caminho
    return None


def criar_fonte_simbolos():
    # Fontes de sistema são grandes. Criamos uma cópia mínima só com ♯ e ♭,
    # para o PDF não ficar pesado. Se der qualquer problema, usa a fonte inteira.
    caminho = achar_fonte_simbolos()
    if not caminho:
        return None
    try:
        from fontTools import subset
        logging.getLogger("fontTools").setLevel(logging.ERROR)
        opcoes = subset.Options()
        fonte = subset.load_font(caminho, opcoes)
        recortador = subset.Subsetter(opcoes)
        recortador.populate(text="\u266f\u266d")
        recortador.subset(fonte)
        destino = str(Path(tempfile.gettempdir()) / "simbolos_acordes.ttf")
        subset.save_font(fonte, destino, opcoes)
        return destino
    except Exception:
        return caminho


def preparar_fontes():
    # Só prepara na primeira vez que o editor é aberto (o app abre mais rápido).
    if _fontes["prontas"]:
        return
    _fontes["caminho"] = criar_fonte_simbolos()
    try:
        _fontes["objeto"] = pymupdf.Font(fontfile=_fontes["caminho"]) if _fontes["caminho"] else None
    except Exception:
        _fontes["caminho"] = None
        _fontes["objeto"] = None
    _fontes["prontas"] = True


# ===============================================================
# Modelo do acorde
# ===============================================================
def novo_acorde(texto, x, y):
    return {
        "texto": texto, "x": x, "y": y,
        "original": False, "texto_orig": "", "x_orig": 0, "y_orig": 0,
        "caixa": (0, 0, 0, 0), "apagado": False,
    }


def mudou(a):
    return (a["apagado"] or a["texto"] != a["texto_orig"]
            or abs(a["x"] - a["x_orig"]) > 0.01 or abs(a["y"] - a["y_orig"]) > 0.01)


def alterado(a):
    # conta como "alteração": acorde novo ou original que foi mexido
    return (not a["original"]) or mudou(a)


# ===============================================================
# Ler os acordes que já existem no PDF
# ===============================================================
def ler_acordes(pagina):
    pedacos = []
    for bloco in pagina.get_text("dict")["blocks"]:
        for linha in bloco.get("lines", []):
            for s in linha["spans"]:
                texto = s["text"].strip()
                # só pedaços curtos e de tamanho típico de acorde
                if texto and 8.0 <= s["size"] <= 15.0 and len(texto) <= 12:
                    pedacos.append({
                        "texto": texto, "x": s["origin"][0], "y": s["origin"][1],
                        "x_fim": s["bbox"][2], "x0": s["bbox"][0], "tamanho": s["size"],
                    })

    # da esquerda para a direita, assim o "#" sempre vem depois da letra
    pedacos.sort(key=lambda p: p["x"])

    acordes = []
    for p in pedacos:
        junto = None
        for a in acordes:
            if abs(a["y"] - p["y"]) < 3.5 and -3 <= p["x"] - a["x_fim"] < DISTANCIA_JUNTAR:
                junto = a
                break
        if junto:
            junto["texto"] += p["texto"]
            junto["x_fim"] = max(junto["x_fim"], p["x_fim"])
        else:
            acordes.append({"texto": p["texto"], "x": p["x"], "y": p["y"],
                            "x_fim": p["x_fim"], "x0": p["x0"], "tamanho": p["tamanho"]})

    resultado = []
    for a in acordes:
        if not PADRAO_ACORDE.match(a["texto"]):
            continue  # número de compasso, título, andamento, letra da música...
        resultado.append({
            "texto": a["texto"], "x": a["x"], "y": a["y"],
            "original": True,
            "texto_orig": a["texto"], "x_orig": a["x"], "y_orig": a["y"],
            "tamanho_orig": a["tamanho"],
            "caixa": (a["x0"] - 0.8, a["y"] - ALTURA_ACIMA, a["x_fim"] + 0.8, a["y"] + ALTURA_ABAIXO),
            "apagado": False,
        })
    resultado.sort(key=lambda a: (round(a["y"]), a["x"]))
    return resultado


def calcular_tamanho(paginas):
    # Aprende com os acordes que já existem no PDF qual é o tamanho de letra usado.
    # Sem acordes para aprender (partitura vazia), devolve o tamanho padrão.
    tamanhos = [a["tamanho_orig"] for acordes in paginas for a in acordes
                if a["original"] and a.get("tamanho_orig")]
    if len(tamanhos) >= 3:
        return round(statistics.median(tamanhos), 1)
    return TAMANHO_ACORDE


# ===============================================================
# Pautas e altura dos acordes
# ===============================================================
def achar_pautas(pagina):
    # Procura grupos de 5 linhas horizontais, longas e igualmente espaçadas.
    linhas = []
    try:
        desenhos = pagina.get_drawings()
    except Exception:
        return []
    for d in desenhos:
        for item in d["items"]:
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 0.05 and abs(p1.x - p2.x) >= 80:
                    linhas.append(((p1.y + p2.y) / 2, min(p1.x, p2.x), max(p1.x, p2.x)))
            elif item[0] == "re":
                r = item[1]
                if r.height < 1.5 and r.width >= 80:
                    linhas.append(((r.y0 + r.y1) / 2, r.x0, r.x1))

    # junta linhas com a mesma altura (o PDF pode desenhar a mesma linha em vários pedaços)
    linhas.sort()
    unicas = []
    for y, x0, x1 in linhas:
        if unicas and abs(unicas[-1][0] - y) < 0.2:
            unicas[-1][1] = min(unicas[-1][1], x0)
            unicas[-1][2] = max(unicas[-1][2], x1)
        else:
            unicas.append([y, x0, x1])

    pautas = []
    i = 0
    while i + 4 < len(unicas):
        grupo = unicas[i:i + 5]
        espacos = [grupo[k + 1][0] - grupo[k][0] for k in range(4)]
        media = sum(espacos) / 4
        if 2 <= media <= 12 and max(espacos) - min(espacos) <= 0.35 * media:
            pautas.append({"topo": grupo[0][0], "base": grupo[4][0],
                           "x0": min(g[1] for g in grupo), "x1": max(g[2] for g in grupo)})
            i += 5
        else:
            i += 1
    return pautas


def amostras_de_offset(acordes, pautas):
    # Para cada acorde que já existia no PDF, mede a distância até o topo da pauta logo abaixo.
    amostras = []
    for a in acordes:
        if a["original"]:
            abaixo = [p["topo"] - a["y_orig"] for p in pautas if 0 < p["topo"] - a["y_orig"] < 60]
            if abaixo:
                amostras.append(min(abaixo))
    return amostras


def calcular_offset(paginas, obter_pautas):
    # Aprende com os acordes que já existem no PDF qual é a altura certa acima da pauta.
    # `obter_pautas(n)` devolve as pautas da página n. Sem acordes para aprender
    # (partitura vazia), devolve o valor padrão.
    amostras = []
    for n in range(len(paginas)):
        amostras += amostras_de_offset(paginas[n], obter_pautas(n))
        if len(amostras) >= 12:
            break
    return statistics.median(amostras) if len(amostras) >= 3 else OFFSET_PAUTA


def altura_na_pauta(pautas, y, offset=OFFSET_PAUTA):
    # Se o ponto y está perto de uma pauta, devolve a altura certa dos acordes dela.
    melhor, menor = None, None
    for p in pautas:
        linha_acorde = p["topo"] - offset
        faixa_topo, faixa_base = linha_acorde - 12, p["base"]
        if faixa_topo <= y <= faixa_base:
            distancia = 0
        else:
            distancia = min(abs(y - faixa_topo), abs(y - faixa_base))
        if menor is None or distancia < menor:
            menor, melhor = distancia, linha_acorde
    if melhor is not None and menor <= RAIO_PAUTA:
        return melhor
    return None


def encaixar_altura(acordes, pautas, y, offset=OFFSET_PAUTA):
    # 1º: gruda na pauta (se `pautas` vier vazia, pula este passo)
    pauta_y = altura_na_pauta(pautas, y, offset)
    if pauta_y is not None:
        return pauta_y
    # 2º: gruda numa linha de acordes que já existia no PDF
    linhas = {round(a["y_orig"], 1) for a in acordes if a["original"]}
    if linhas:
        mais_perto = min(linhas, key=lambda linha: abs(linha - y))
        if abs(mais_perto - y) <= RAIO_ENCAIXE:
            return mais_perto
    return y


# ===============================================================
# Texto do acorde: dividir, medir, escrever, achar com o mouse
# ===============================================================
def dividir(texto):
    # Separa em pedaços (trecho, é_símbolo). Ex.: "Bbm7" -> B, ♭, m7
    partes = []
    for i, c in enumerate(texto):
        anterior = texto[i - 1] if i > 0 else ""
        eh_bemol = (c == "b" and anterior != "" and
                    (anterior.isdigit() or
                     (anterior in "ABCDEFG" and (i == 1 or texto[i - 2] == "/"))))
        if c == "#":
            partes.append(("\u266f", True))
        elif eh_bemol:
            partes.append(("\u266d", True))
        elif partes and not partes[-1][1]:
            partes[-1] = (partes[-1][0] + c, False)
        else:
            partes.append((c, False))
    return partes


def largura_trecho(trecho, simbolo, tamanho=TAMANHO_ACORDE):
    escala = tamanho / TAMANHO_ACORDE  # o ♯ e o ♭ crescem junto com a letra
    if simbolo and _fontes["objeto"]:
        return _fontes["objeto"].text_length(trecho, fontsize=TAMANHO_SIMBOLO * escala) + 0.3 * escala
    if simbolo:
        trecho = "#" if trecho == "\u266f" else "b"
    return pymupdf.get_text_length(trecho, fontname="tibo", fontsize=tamanho)


def medir(texto, tamanho=TAMANHO_ACORDE):
    return sum(largura_trecho(t, s, tamanho) for t, s in dividir(texto))


def escrever_acorde(pagina, texto, x, y, tamanho=TAMANHO_ACORDE):
    escala = tamanho / TAMANHO_ACORDE
    for trecho, simbolo in dividir(texto):
        if simbolo and _fontes["objeto"]:
            pagina.insert_text((x, y - SUBIDA_SIMBOLO * escala), trecho,
                               fontname="simb", fontsize=TAMANHO_SIMBOLO * escala)
        else:
            if simbolo:
                trecho = "#" if trecho == "\u266f" else "b"
            pagina.insert_text((x, y), trecho, fontname="tibo", fontsize=tamanho)
        x += largura_trecho(trecho, simbolo, tamanho)


def tamanho_do_acorde(a, padrao):
    # Um acorde original que ninguém mexeu continua no tamanho que tinha no PDF.
    # Os novos e os editados usam o tamanho escolhido no menu ("padrao").
    if a.get("original") and not mudou(a):
        return a.get("tamanho_orig") or padrao
    return padrao


def caixa_do_acorde(a, tamanho=TAMANHO_ACORDE):
    # Retângulo (x0, y0, x1, y1) que "pertence" ao acorde, usado para saber se o clique pegou nele
    t = tamanho_do_acorde(a, tamanho) if "apagado" in a else tamanho
    escala = t / TAMANHO_ACORDE
    return (a["x"] - 1, a["y"] - ALTURA_ACIMA * escala - 1,
            a["x"] + medir(a["texto"], t) + 1, a["y"] + ALTURA_ABAIXO * escala + 1)


def acorde_na_posicao(acordes, x, y, tamanho=TAMANHO_ACORDE):
    for a in reversed(acordes):  # do último para o primeiro: o de cima ganha
        if a["apagado"]:
            continue
        x0, y0, x1, y1 = caixa_do_acorde(a, tamanho)
        if x0 <= x <= x1 and y0 <= y <= y1:
            return a
    return None


def aplicar_edicoes(pagina, acordes, tamanho=TAMANHO_ACORDE):
    # Serve para a tela e para salvar o PDF.
    if _fontes["caminho"]:
        pagina.insert_font(fontname="simb", fontfile=_fontes["caminho"])
    # 1) cobre de branco os acordes originais que foram alterados, movidos ou apagados
    for a in acordes:
        if a["original"] and mudou(a):
            pagina.draw_rect(pymupdf.Rect(a["caixa"]), color=None, fill=(1, 1, 1), overlay=True)
    # 2) escreve os acordes novos e os alterados
    for a in acordes:
        if a["apagado"]:
            continue
        if alterado(a):
            escrever_acorde(pagina, a["texto"], a["x"], a["y"], tamanho)


# ===============================================================
# Transposição e tons
# ===============================================================
def _indice_nota(nota):
    valor = VALOR_NOTA[nota[0]]
    if len(nota) > 1:
        valor += 1 if nota[1] == "#" else -1
    return valor % 12


def transpor_acorde(texto, semitons):
    m = re.match(r"^([A-G][#b]?)(.*?)(?:/([A-G][#b]?))?$", texto)
    if not m or semitons % 12 == 0:
        return texto
    raiz, qualidade, baixo = m.group(1), m.group(2), m.group(3)
    if "b" in raiz or (baixo and "b" in baixo):
        usar_bemol = True
    elif "#" in raiz or (baixo and "#" in baixo):
        usar_bemol = False
    else:
        usar_bemol = semitons < 0
    nomes = NOTAS_BEMOL if usar_bemol else NOTAS_SUSTENIDO
    novo = nomes[(_indice_nota(raiz) + semitons) % 12] + qualidade
    if baixo:
        novo += "/" + nomes[(_indice_nota(baixo) + semitons) % 12]
    return novo


def acordes_do_tom(tom):
    # Devolve os acordes do tom (graus 1 a 7 + dominante com sétima).
    menor = tom.endswith("m")
    raiz = _indice_nota(tom[:-1] if menor else tom)
    nomes = NOTAS_BEMOL if tom in TONS_COM_BEMOL else NOTAS_SUSTENIDO
    if menor:
        graus = [0, 2, 3, 5, 7, 8, 10]
        qualidades = ["m", "dim", "", "m", "m", "", ""]
    else:
        graus = [0, 2, 4, 5, 7, 9, 11]
        qualidades = ["", "m", "m", "", "", "m", "dim"]
    lista = [nomes[(raiz + g) % 12] + q for g, q in zip(graus, qualidades)]
    lista.append(nomes[(raiz + 7) % 12] + "7")
    return lista


# ===============================================================
# Projeto (.acordes.json)
# ===============================================================
def caminho_projeto(caminho_pdf):
    p = Path(caminho_pdf)
    return p.with_name(p.stem + ".acordes.json")


def exportar_projeto(paginas, nome_pdf, tamanho=None):
    saida = {"versao": 1, "pdf": nome_pdf, "tamanho": tamanho, "paginas": []}
    for acordes in paginas:
        novos, alterados = [], []
        for a in acordes:
            if not a["original"]:
                novos.append({"texto": a["texto"], "x": a["x"], "y": a["y"]})
            elif mudou(a):
                alterados.append({
                    "texto_orig": a["texto_orig"], "x_orig": a["x_orig"], "y_orig": a["y_orig"],
                    "texto": a["texto"], "x": a["x"], "y": a["y"], "apagado": a["apagado"],
                })
        saida["paginas"].append({"novos": novos, "alterados": alterados})
    return saida


def importar_projeto(dados, paginas):
    for numero, dados_pagina in enumerate(dados.get("paginas", [])):
        if numero >= len(paginas):
            break
        for alt in dados_pagina.get("alterados", []):
            for a in paginas[numero]:
                if (a["original"] and a["texto_orig"] == alt["texto_orig"]
                        and abs(a["x_orig"] - alt["x_orig"]) < 0.5
                        and abs(a["y_orig"] - alt["y_orig"]) < 0.5):
                    a["texto"], a["x"], a["y"] = alt["texto"], alt["x"], alt["y"]
                    a["apagado"] = bool(alt.get("apagado"))
                    break
        for n in dados_pagina.get("novos", []):
            paginas[numero].append(novo_acorde(n["texto"], n["x"], n["y"]))


def gravar_projeto(caminho_pdf, paginas, tamanho=None):
    # Escreve o .acordes.json ao lado do PDF e devolve o caminho dele
    destino = caminho_projeto(caminho_pdf)
    dados = exportar_projeto(paginas, Path(caminho_pdf).name, tamanho)
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


def carregar_projeto(caminho_pdf, paginas):
    # Lê o .acordes.json e aplica nas páginas.
    # Devolve False se não existir projeto salvo; senão, um dicionário com as configurações salvas.
    origem = caminho_projeto(caminho_pdf)
    if not origem.exists():
        return False
    dados = json.loads(origem.read_text(encoding="utf-8"))
    importar_projeto(dados, paginas)
    return {"tamanho": dados.get("tamanho")}
