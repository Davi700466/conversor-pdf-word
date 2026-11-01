import pymupdf


def pdf_para_texto(entrada, saida):
    doc = pymupdf.open(entrada)   # abre o PDF
    textos = []                   # lista vazia: vai guardar o texto de cada página

    for pagina in doc:            # repete para cada página do PDF
        # FAÇA 1: pegue o texto desta página e coloque na lista "textos"
        textos.append(pagina.get_text())

    doc.close()                   # fecha o PDF

    # FAÇA 2: junte os textos de todas as páginas e grave no arquivo "saida"
    texto_final = "\n".join(textos)

    with open(saida, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto_final)
    