"""
Testes da lógica do editor (não abrem janela).

Como rodar, na pasta do projeto:
    python -m pip install pytest
    python -m pytest
"""
import pymupdf

from partitura import logica as lg


def test_padrao_reconhece_acordes_e_ignora_o_resto():
    for ok in ["C", "F#m7", "Bb/D", "G7", "Cmaj7", "Bdim", "Asus4"]:
        assert lg.PADRAO_ACORDE.match(ok), ok
    for ruim in ["101", "q. = 60", "Interpretação", "H", ""]:
        assert not lg.PADRAO_ACORDE.match(ruim), ruim


def test_transpor():
    assert lg.transpor_acorde("C", 2) == "D"
    assert lg.transpor_acorde("F#m7", 1) == "Gm7"
    assert lg.transpor_acorde("Bb/D", 2) == "C/E"
    assert lg.transpor_acorde("G", -2) == "F"
    assert lg.transpor_acorde("A", -1) == "Ab"
    assert lg.transpor_acorde("Bbm", 12) == "Bbm"
    assert lg.transpor_acorde("texto qualquer", 3) == "texto qualquer"


def test_acordes_do_tom():
    assert lg.acordes_do_tom("G") == ["G", "Am", "Bm", "C", "D", "Em", "F#dim", "D7"]
    assert lg.acordes_do_tom("Am") == ["Am", "Bdim", "C", "Dm", "Em", "F", "G", "E7"]
    assert lg.acordes_do_tom("Bb")[0:4] == ["Bb", "Cm", "Dm", "Eb"]


def test_dividir_separa_simbolos():
    assert lg.dividir("F#m7") == [("F", False), ("♯", True), ("m7", False)]
    assert lg.dividir("Bb") == [("B", False), ("♭", True)]
    assert lg.dividir("Bm") == [("Bm", False)]  # o "b" de "Bm" não existe aqui: B + m


def _pdf_com_pautas(caminho, topos=(300, 450), espaco=6, acima=17, acordes=("Ab", "Dm", "Eb", "Fm7")):
    doc = pymupdf.open()
    pg = doc.new_page(width=595, height=842)
    for topo in topos:
        for k in range(5):
            pg.draw_line((40, topo + k * espaco), (555, topo + k * espaco), width=0.5)
        for i, c in enumerate(acordes):
            pg.insert_text((60 + i * 110, topo - acima), c, fontname="tibo", fontsize=11.8)
    doc.save(caminho)
    doc.close()


def test_acha_pautas_e_aprende_altura(tmp_path):
    caminho = str(tmp_path / "ritmo.pdf")
    _pdf_com_pautas(caminho)
    doc = pymupdf.open(caminho)
    pautas = [lg.achar_pautas(p) for p in doc]
    assert len(pautas[0]) == 2
    paginas = [lg.ler_acordes(p) for p in doc]
    assert [a["texto"] for a in paginas[0]][:4] == ["Ab", "Dm", "Eb", "Fm7"]
    assert abs(lg.calcular_offset(paginas, lambda n: pautas[n]) - 17) < 0.2
    # clique perto da pauta cai na altura dos acordes (topo 300 - 17 = 283)
    y = lg.encaixar_altura(paginas[0], pautas[0], 290, 17)
    assert abs(y - 283) < 0.2


def test_partitura_vazia_usa_offset_padrao(tmp_path):
    caminho = str(tmp_path / "vazia.pdf")
    _pdf_com_pautas(caminho, acordes=())
    doc = pymupdf.open(caminho)
    paginas = [lg.ler_acordes(p) for p in doc]
    assert paginas == [[]]
    assert lg.calcular_offset(paginas, lambda n: lg.achar_pautas(doc[n])) == lg.OFFSET_PAUTA


def test_projeto_salva_e_recarrega(tmp_path):
    caminho = str(tmp_path / "ritmo.pdf")
    _pdf_com_pautas(caminho)
    doc = pymupdf.open(caminho)
    paginas = [lg.ler_acordes(p) for p in doc]
    paginas[0][0]["texto"] = "Gm"                                  # alterou um original
    paginas[0][1]["apagado"] = True                               # apagou outro
    paginas[0].append(lg.novo_acorde("C/E", 100.0, 283.0))        # adicionou um novo
    lg.gravar_projeto(caminho, paginas, tamanho=14)

    de_novo = [lg.ler_acordes(p) for p in pymupdf.open(caminho)]
    configuracoes = lg.carregar_projeto(caminho, de_novo)
    assert configuracoes["tamanho"] == 14
    assert de_novo[0][0]["texto"] == "Gm"
    assert de_novo[0][1]["apagado"] is True
    assert de_novo[0][-1]["texto"] == "C/E"


def test_sem_projeto_salvo_devolve_falso(tmp_path):
    assert lg.carregar_projeto(str(tmp_path / "nao_existe.pdf"), [[]]) is False


def test_edicoes_aparecem_no_pdf(tmp_path):
    caminho = str(tmp_path / "ritmo.pdf")
    _pdf_com_pautas(caminho)
    lg.preparar_fontes()
    doc = pymupdf.open(caminho)
    paginas = [lg.ler_acordes(p) for p in doc]
    paginas[0][0]["texto"] = "Em"
    paginas[0].append(lg.novo_acorde("Am7", 300.0, 283.0))
    lg.aplicar_edicoes(doc[0], paginas[0])
    texto = doc[0].get_text()
    assert "Em" in texto and "Am7" in texto


def test_aprende_tamanho_da_fonte(tmp_path):
    caminho = str(tmp_path / "ritmo.pdf")
    _pdf_com_pautas(caminho)
    paginas = [lg.ler_acordes(p) for p in pymupdf.open(caminho)]
    assert abs(lg.calcular_tamanho(paginas) - 11.8) < 0.1
    assert lg.calcular_tamanho([[]]) == lg.TAMANHO_ACORDE  # sem acordes: tamanho padrão


def test_fonte_maior_ocupa_mais_espaco():
    assert lg.medir("F#m7", 18) > lg.medir("F#m7", 12) > lg.medir("F#m7", 8)
    a = lg.novo_acorde("Am", 100.0, 200.0)
    pequena, grande = lg.caixa_do_acorde(a, 10), lg.caixa_do_acorde(a, 20)
    assert (grande[2] - grande[0]) > (pequena[2] - pequena[0])
    assert (grande[3] - grande[1]) > (pequena[3] - pequena[1])


def test_tamanho_escolhido_vale_para_novos_e_original_intocado_mantem_o_seu(tmp_path):
    caminho = str(tmp_path / "ritmo.pdf")
    _pdf_com_pautas(caminho)
    lg.preparar_fontes()
    doc = pymupdf.open(caminho)
    paginas = [lg.ler_acordes(p) for p in doc]
    original = paginas[0][0]
    novo = lg.novo_acorde("Am7", 300.0, 283.0)
    paginas[0].append(novo)
    assert lg.tamanho_do_acorde(original, 20) == original["tamanho_orig"]
    assert lg.tamanho_do_acorde(novo, 20) == 20
    lg.aplicar_edicoes(doc[0], paginas[0], 20)
    tamanhos = [s["size"] for b in doc[0].get_text("dict")["blocks"] for l in b.get("lines", [])
                for s in l["spans"] if s["text"].strip() == "Am7"]
    assert tamanhos and abs(tamanhos[0] - 20) < 0.1
