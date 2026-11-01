"""
Janela do editor de acordes.

Aqui fica só a parte visual: botões, canvas, mouse e teclado.
As regras (ler acordes, achar pautas, transpor, salvar projeto) estão em logica.py.

Pode ser usado de dois jeitos:
  1) Dentro do app.py:   from partitura.janela import abrir_editor
  2) Sozinho:            python -m partitura.janela     (rodando na pasta do projeto)
"""

import copy
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog

import pymupdf

from partitura import logica as lg

# ---------------------------------------------------------------
# Ajustes da tela
# ---------------------------------------------------------------
ZOOM_INICIAL = 1.4        # tamanho da página na tela
ZOOM_MIN, ZOOM_MAX = 0.6, 3.0
LIMITE_ARRASTE = 4        # pixels que o mouse precisa andar para contar como arraste

# Tudo o que o programa "lembra" fica neste dicionário
estado = {
    "doc": None,            # o PDF aberto
    "caminho": None,        # onde ele está no computador
    "paginas": [],          # uma lista de acordes para cada página
    "pautas": {},           # pautas de cada página (calculadas quando precisa)
    "offset": None,         # distância acorde→pauta aprendida com este PDF
    "numero": 0,            # página atual (começa em 0)
    "historico": [],        # cópias antigas, para o desfazer
    "refazer": [],          # cópias desfeitas, para o refazer
    "modificado": False,    # tem alteração ainda não salva no projeto?
    "imagem": None,         # imagem mostrada na tela (precisa ficar guardada)
    "arraste": None,        # dados do clique/arraste em andamento
    "zoom": ZOOM_INICIAL,
    "tamanho": lg.TAMANHO_ACORDE,   # tamanho da letra dos acordes que o programa escreve
    "paleta": [],           # acordes da paleta (para as teclas 1-8)
    "pai": None,            # janela principal do app
    "encerrar": False,      # True quando roda sozinho
}

# Peças da janela (criadas em construir_janela)
janela = None
canvas = None
status = None
var_ativo = None
var_alinhar = None
combo_tom = None
combo_tamanho = None
frame_paleta = None


# ---------- tela ----------
def renderizar_pagina():
    if estado["doc"] is None:
        return
    numero = estado["numero"]
    zoom = estado["zoom"]
    # Copia só esta página para um PDF temporário, aplica as alterações e desenha
    temporario = pymupdf.open()
    temporario.insert_pdf(estado["doc"], from_page=numero, to_page=numero)
    pagina = temporario[0]
    lg.aplicar_edicoes(pagina, estado["paginas"][numero], estado["tamanho"])
    pixmap = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    temporario.close()

    estado["imagem"] = tk.PhotoImage(data=pixmap.tobytes("ppm"))
    canvas.delete("all")
    canvas.create_image(0, 0, anchor="nw", image=estado["imagem"])
    canvas.config(scrollregion=(0, 0, pixmap.width, pixmap.height))
    atualizar_status()


def contar_alteracoes():
    return sum(1 for acordes in estado["paginas"] for a in acordes if lg.alterado(a))


def atualizar_status(mensagem=""):
    if estado["doc"] is None:
        status.config(text="Nenhum PDF aberto")
        return
    texto = (f"Página {estado['numero'] + 1} de {len(estado['paginas'])}   |   "
             f"{contar_alteracoes()} alteração(ões)   |   Zoom {int(estado['zoom'] * 100)}%")
    if estado["modificado"]:
        texto += "   |   projeto não salvo"
    if mensagem:
        texto += "   |   " + mensagem
    status.config(text=texto)


def formatar_tamanho(valor):
    return f"{valor:g}"  # 12.0 vira "12" e 11.8 continua "11.8"


def mudar_tamanho(evento=None):
    if estado["doc"] is None:
        return
    estado["tamanho"] = float(combo_tamanho.get())
    estado["modificado"] = True
    renderizar_pagina()


def mudar_zoom(fator):
    if estado["doc"] is None:
        return
    novo = min(ZOOM_MAX, max(ZOOM_MIN, estado["zoom"] * fator))
    if abs(novo - estado["zoom"]) < 0.001:
        return
    estado["zoom"] = novo
    renderizar_pagina()


# ---------- encontrar acordes e posições ----------
def acordes_da_pagina():
    return estado["paginas"][estado["numero"]]


def pautas_da_pagina(numero=None):
    if numero is None:
        numero = estado["numero"]
    if numero not in estado["pautas"]:
        estado["pautas"][numero] = lg.achar_pautas(estado["doc"][numero])
    return estado["pautas"][numero]


def offset_da_pauta():
    if estado["offset"] is None:
        estado["offset"] = lg.calcular_offset(estado["paginas"], pautas_da_pagina)
    return estado["offset"]


def encaixar_y(y):
    if var_alinhar.get():
        return lg.encaixar_altura(acordes_da_pagina(), pautas_da_pagina(), y, offset_da_pauta())
    return lg.encaixar_altura(acordes_da_pagina(), [], y)  # sem pauta: só gruda nos acordes existentes


def posicao_do_mouse(evento):
    x_px = canvas.canvasx(evento.x)
    y_px = canvas.canvasy(evento.y)
    zoom = estado["zoom"]
    return x_px, y_px, x_px / zoom, y_px / zoom


# ---------- ações: editar, adicionar, mover, apagar, desfazer ----------
def registrar_historico():
    estado["historico"].append(copy.deepcopy(estado["paginas"]))
    if len(estado["historico"]) > 50:
        estado["historico"].pop(0)
    estado["refazer"].clear()


def depois_de_alterar():
    estado["modificado"] = True
    renderizar_pagina()


def editar_acorde(a):
    novo = simpledialog.askstring("Editar acorde", "Digite o acorde (deixe vazio para apagar):",
                                  initialvalue=a["texto"], parent=janela)
    if novo is None:
        return
    novo = novo.strip()
    if novo == a["texto"]:
        return
    registrar_historico()
    if novo == "":
        apagar_acorde(a, registrar=False)
        return
    a["texto"] = novo
    depois_de_alterar()


def adicionar_acorde(x_pt, y_pt):
    texto = var_ativo.get().strip()  # acorde escolhido na paleta
    if not texto:
        texto = simpledialog.askstring("Novo acorde", "Digite o acorde (ex.: G, F#, Bb, Am7, C/E):",
                                       parent=janela)
        if texto is None or texto.strip() == "":
            return
        texto = texto.strip()
    registrar_historico()
    acordes_da_pagina().append(lg.novo_acorde(texto, x_pt, encaixar_y(y_pt + 4)))
    depois_de_alterar()


def mover_acorde(a, x_pt, y_pt):
    registrar_historico()
    a["x"] = x_pt
    a["y"] = encaixar_y(y_pt)
    depois_de_alterar()


def apagar_acorde(a, registrar=True):
    if registrar:
        registrar_historico()
    if a["original"]:
        a["apagado"] = True
    else:
        acordes_da_pagina().remove(a)
    depois_de_alterar()


def desfazer(evento=None):
    if not estado["historico"]:
        return
    estado["refazer"].append(copy.deepcopy(estado["paginas"]))
    estado["paginas"] = estado["historico"].pop()
    depois_de_alterar()


def refazer(evento=None):
    if not estado["refazer"]:
        return
    estado["historico"].append(copy.deepcopy(estado["paginas"]))
    estado["paginas"] = estado["refazer"].pop()
    depois_de_alterar()


def transpor_tudo():
    if estado["doc"] is None:
        return
    n = simpledialog.askinteger("Transpor", "Quantos semitons? (positivo sobe, negativo desce)",
                                parent=janela, initialvalue=1, minvalue=-11, maxvalue=11)
    if not n:
        return
    registrar_historico()
    for acordes in estado["paginas"]:
        for a in acordes:
            if not a["apagado"]:
                a["texto"] = lg.transpor_acorde(a["texto"], n)
    depois_de_alterar()


# ---------- paleta do tom ----------
def montar_paleta(evento=None):
    for w in frame_paleta.winfo_children():
        w.destroy()
    var_ativo.set("")
    estado["paleta"] = lg.acordes_do_tom(combo_tom.get())
    ttk.Radiobutton(frame_paleta, text="Digitar (0)", variable=var_ativo, value="",
                    style="Toolbutton").pack(side="left", padx=1)
    for i, acorde in enumerate(estado["paleta"], start=1):
        ttk.Radiobutton(frame_paleta, text=f"{acorde} ({i})", variable=var_ativo, value=acorde,
                        style="Toolbutton").pack(side="left", padx=1)


def escolher_da_paleta(posicao):
    if posicao == -1:
        var_ativo.set("")
    elif 0 <= posicao < len(estado["paleta"]):
        var_ativo.set(estado["paleta"][posicao])


# ---------- mouse ----------
def ao_apertar(evento):
    if estado["doc"] is None:
        return
    x_px, y_px, x_pt, y_pt = posicao_do_mouse(evento)
    a = lg.acorde_na_posicao(acordes_da_pagina(), x_pt, y_pt, estado["tamanho"])
    estado["arraste"] = {
        "acorde": a, "inicio_px": (x_px, y_px), "movendo": False,
        "dx": (x_pt - a["x"]) if a else 0, "dy": (y_pt - a["y"]) if a else 0,
    }


def ao_arrastar(evento):
    arraste = estado["arraste"]
    if not arraste or not arraste["acorde"]:
        return
    x_px, y_px, x_pt, y_pt = posicao_do_mouse(evento)
    if not arraste["movendo"]:
        if abs(x_px - arraste["inicio_px"][0]) + abs(y_px - arraste["inicio_px"][1]) < LIMITE_ARRASTE:
            return
        arraste["movendo"] = True
    a = arraste["acorde"]
    x0, y0, x1, y1 = lg.caixa_do_acorde({"texto": a["texto"], "x": x_pt - arraste["dx"], "y": y_pt - arraste["dy"]}, estado["tamanho"])
    z = estado["zoom"]
    canvas.delete("arraste")
    canvas.create_rectangle(x0 * z, y0 * z, x1 * z, y1 * z, outline="#1a73e8", width=2, tags="arraste")


def ao_soltar(evento):
    arraste = estado["arraste"]
    estado["arraste"] = None
    if estado["doc"] is None or not arraste:
        return
    canvas.delete("arraste")
    _, _, x_pt, y_pt = posicao_do_mouse(evento)
    a = arraste["acorde"]
    if a is None:
        adicionar_acorde(x_pt, y_pt)
    elif arraste["movendo"]:
        mover_acorde(a, x_pt - arraste["dx"], y_pt - arraste["dy"])
    else:
        editar_acorde(a)


def ao_clicar_direito(evento):
    if estado["doc"] is None:
        return
    _, _, x_pt, y_pt = posicao_do_mouse(evento)
    a = lg.acorde_na_posicao(acordes_da_pagina(), x_pt, y_pt, estado["tamanho"])
    if a:
        apagar_acorde(a)


def ao_passar_mouse(evento):
    if estado["doc"] is None or estado["arraste"]:
        return
    _, _, x_pt, y_pt = posicao_do_mouse(evento)
    a = lg.acorde_na_posicao(acordes_da_pagina(), x_pt, y_pt, estado["tamanho"])
    canvas.delete("destaque")
    if a:
        x0, y0, x1, y1 = lg.caixa_do_acorde(a, estado["tamanho"])
        z = estado["zoom"]
        canvas.create_rectangle(x0 * z, y0 * z, x1 * z, y1 * z, outline="#e8710a", width=2, tags="destaque")
        canvas.config(cursor="hand2")
    else:
        canvas.config(cursor="arrow")


def ao_girar_roda(evento):
    canvas.yview_scroll(int(-evento.delta / 120), "units")


# ---------- abrir, trocar de página, salvar ----------
def abrir_pdf(caminho=None):
    if estado["modificado"]:
        if not messagebox.askyesno("Alterações não salvas",
                                   "Há alterações que não foram salvas no projeto.\nAbrir outro PDF mesmo assim?",
                                   parent=janela):
            return
    if caminho is None:
        caminho = filedialog.askopenfilename(
            title="Escolha a partitura em PDF", filetypes=[("Arquivos PDF", "*.pdf")], parent=janela)
    if not caminho:
        return
    try:
        doc = pymupdf.open(caminho)
        paginas = [lg.ler_acordes(pagina) for pagina in doc]
    except Exception as erro:
        messagebox.showerror("Erro", f"Não foi possível abrir o PDF:\n{erro}", parent=janela)
        return

    if estado["doc"] is not None:
        estado["doc"].close()
    estado.update({
        "doc": doc, "caminho": caminho, "paginas": paginas, "pautas": {}, "offset": None,
        "tamanho": lg.calcular_tamanho(paginas), "numero": 0, "historico": [], "refazer": [], "modificado": False,
    })
    janela.title(f"Editor de Acordes - {Path(caminho).name}")

    # Se já existe um projeto salvo para este PDF, oferece carregar
    if lg.caminho_projeto(caminho).exists() and messagebox.askyesno(
            "Projeto encontrado", "Encontrei acordes salvos para este PDF.\nCarregar?", parent=janela):
        try:
            configuracoes = lg.carregar_projeto(caminho, estado["paginas"])
            if configuracoes and configuracoes.get("tamanho"):
                estado["tamanho"] = float(configuracoes["tamanho"])
        except Exception as erro:
            messagebox.showerror("Erro", f"Não foi possível carregar o projeto:\n{erro}", parent=janela)
    combo_tamanho.set(formatar_tamanho(estado["tamanho"]))
    renderizar_pagina()


def mudar_pagina(deslocamento):
    if estado["doc"] is None:
        return
    novo = estado["numero"] + deslocamento
    if 0 <= novo < len(estado["paginas"]):
        estado["numero"] = novo
        canvas.yview_moveto(0)
        renderizar_pagina()


def salvar_projeto(evento=None):
    if estado["doc"] is None:
        return False
    try:
        destino = lg.gravar_projeto(estado["caminho"], estado["paginas"], estado["tamanho"])
    except Exception as erro:
        messagebox.showerror("Erro", f"Não foi possível salvar o projeto:\n{erro}", parent=janela)
        return False
    estado["modificado"] = False
    atualizar_status(f"projeto salvo em {destino.name}")
    return True


def exportar_pdf(evento=None):
    if estado["doc"] is None:
        return
    original = Path(estado["caminho"])
    saida = filedialog.asksaveasfilename(
        title="Exportar PDF editado", defaultextension=".pdf",
        initialdir=str(original.parent), initialfile=original.stem + "_editado.pdf",
        filetypes=[("Arquivos PDF", "*.pdf")], parent=janela)
    if not saida:
        return
    if Path(saida).resolve() == original.resolve():
        messagebox.showwarning("Atenção", "Escolha um nome diferente do arquivo original.", parent=janela)
        return
    try:
        doc = pymupdf.open(estado["caminho"])
        for numero, pagina in enumerate(doc):
            lg.aplicar_edicoes(pagina, estado["paginas"][numero], estado["tamanho"])
        doc.save(saida, garbage=3, deflate=True)
        doc.close()
    except Exception as erro:
        messagebox.showerror("Erro", f"Não foi possível salvar:\n{erro}", parent=janela)
        return
    messagebox.showinfo("Pronto!", f"PDF salvo em:\n{saida}", parent=janela)


def ao_fechar():
    global janela
    if estado["modificado"]:
        resposta = messagebox.askyesnocancel(
            "Alterações não salvas",
            "Salvar o projeto (os acordes) antes de sair?\n\n"
            "Sim = salvar e sair\nNão = sair sem salvar\nCancelar = continuar editando",
            parent=janela)
        if resposta is None:
            return
        if resposta and not salvar_projeto():
            return
    if estado["doc"] is not None:
        estado["doc"].close()
    estado.update({"doc": None, "caminho": None, "paginas": [], "pautas": {}, "offset": None,
                   "historico": [], "refazer": [], "modificado": False,
                   "numero": 0, "arraste": None, "imagem": None})
    janela.destroy()
    janela = None
    if estado["encerrar"] and estado["pai"] is not None:
        estado["pai"].destroy()


# ---------- montar a janela ----------
def construir_janela(pai):
    global janela, canvas, status, var_ativo, var_alinhar, combo_tom, combo_tamanho, frame_paleta

    janela = tk.Toplevel(pai)
    janela.title("Editor de Acordes")
    janela.geometry("1000x800")
    janela.protocol("WM_DELETE_WINDOW", ao_fechar)

    var_ativo = tk.StringVar(value="")
    var_alinhar = tk.BooleanVar(value=True)

    barra = ttk.Frame(janela, padding=(6, 6, 6, 2))
    barra.pack(fill="x")
    ttk.Button(barra, text="Abrir PDF", command=abrir_pdf).pack(side="left")
    ttk.Button(barra, text="◀", width=3, command=lambda: mudar_pagina(-1)).pack(side="left", padx=(12, 0))
    ttk.Button(barra, text="▶", width=3, command=lambda: mudar_pagina(1)).pack(side="left", padx=2)
    ttk.Button(barra, text="Desfazer", command=desfazer).pack(side="left", padx=(12, 0))
    ttk.Button(barra, text="Refazer", command=refazer).pack(side="left", padx=2)
    ttk.Button(barra, text="−", width=3, command=lambda: mudar_zoom(1 / 1.2)).pack(side="left", padx=(12, 0))
    ttk.Button(barra, text="+", width=3, command=lambda: mudar_zoom(1.2)).pack(side="left", padx=2)
    ttk.Button(barra, text="Transpor…", command=transpor_tudo).pack(side="left", padx=(12, 0))
    ttk.Button(barra, text="Exportar PDF", command=exportar_pdf).pack(side="right")
    ttk.Button(barra, text="Salvar projeto", command=salvar_projeto).pack(side="right", padx=4)

    barra2 = ttk.Frame(janela, padding=(6, 2, 6, 2))
    barra2.pack(fill="x")
    ttk.Label(barra2, text="Fonte:").pack(side="left")
    combo_tamanho = ttk.Combobox(barra2, values=[formatar_tamanho(t) for t in lg.TAMANHOS],
                                 state="readonly", width=5)
    combo_tamanho.set(formatar_tamanho(estado["tamanho"]))
    combo_tamanho.pack(side="left", padx=(4, 12))
    combo_tamanho.bind("<<ComboboxSelected>>", mudar_tamanho)
    ttk.Label(barra2, text="Tom:").pack(side="left")
    combo_tom = ttk.Combobox(barra2, values=lg.TONS, state="readonly", width=5)
    combo_tom.set("C")
    combo_tom.pack(side="left", padx=(4, 8))
    combo_tom.bind("<<ComboboxSelected>>", montar_paleta)
    frame_paleta = ttk.Frame(barra2)
    frame_paleta.pack(side="left")
    ttk.Checkbutton(barra2, text="Alinhar à pauta", variable=var_alinhar).pack(side="right")

    status = ttk.Label(janela, text="Nenhum PDF aberto", padding=(8, 2))
    status.pack(fill="x")
    ttk.Label(
        janela,
        text="Clique num acorde para editar  •  Clique no espaço vazio para adicionar (usa o acorde marcado na paleta)  •  "
             "Arraste para mover  •  Botão direito apaga  •  Teclas 0-8 escolhem da paleta",
        padding=(8, 2), foreground="#555555",
    ).pack(fill="x")

    area = ttk.Frame(janela)
    area.pack(fill="both", expand=True)
    rolagem = ttk.Scrollbar(area, orient="vertical")
    rolagem.pack(side="right", fill="y")
    canvas = tk.Canvas(area, background="#d9d9d9", yscrollcommand=rolagem.set, highlightthickness=0)
    canvas.pack(side="left", fill="both", expand=True)
    rolagem.config(command=canvas.yview)

    canvas.bind("<ButtonPress-1>", ao_apertar)
    canvas.bind("<B1-Motion>", ao_arrastar)
    canvas.bind("<ButtonRelease-1>", ao_soltar)
    canvas.bind("<Button-3>", ao_clicar_direito)
    canvas.bind("<Motion>", ao_passar_mouse)
    canvas.bind("<MouseWheel>", ao_girar_roda)
    janela.bind("<Control-z>", desfazer)
    janela.bind("<Control-y>", refazer)
    janela.bind("<Control-s>", salvar_projeto)
    janela.bind("<Control-e>", exportar_pdf)
    janela.bind("<Prior>", lambda e: mudar_pagina(-1))   # PageUp
    janela.bind("<Next>", lambda e: mudar_pagina(1))     # PageDown
    janela.bind("<Key-0>", lambda e: escolher_da_paleta(-1))
    for i in range(1, 9):
        janela.bind(f"<Key-{i}>", lambda e, i=i: escolher_da_paleta(i - 1))

    montar_paleta()


def abrir_editor(pai, caminho=None, encerrar_ao_fechar=False):
    # Já está aberto? Só traz para a frente.
    if janela is not None and janela.winfo_exists():
        janela.deiconify()
        janela.lift()
        janela.focus_force()
        if caminho:
            abrir_pdf(caminho)
        return
    # Escolhe o PDF ANTES de criar a janela (se cancelar, nada fica aberto)
    if caminho is None:
        caminho = filedialog.askopenfilename(
            title="Escolha a partitura em PDF", filetypes=[("Arquivos PDF", "*.pdf")], parent=pai)
        if not caminho:
            return
    lg.preparar_fontes()
    estado["pai"] = pai
    estado["encerrar"] = encerrar_ao_fechar
    construir_janela(pai)
    abrir_pdf(caminho)


if __name__ == "__main__":
    raiz = tk.Tk()
    raiz.withdraw()
    abrir_editor(raiz, encerrar_ao_fechar=True)
    if janela is None:
        raiz.destroy()
    else:
        raiz.mainloop()
