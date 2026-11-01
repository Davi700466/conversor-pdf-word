"""
Meu Conversor Pessoal - janela principal.

Este arquivo só monta a janela e o menu. O trabalho de verdade está em:
  - conversores/pdf_word.py   (PDF <-> Word)
  - partitura/                (editor de acordes para PDFs de partitura)
"""
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from conversores.pdf_text import pdf_para_texto
from conversores.pdf_word import pdf_para_word, word_para_pdf
from partitura.janela import abrir_editor

def caminho_recurso(nome):
    # Dentro do .exe, os arquivos extras ficam numa pasta temporária (sys._MEIPASS)
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return str(Path(base) / nome)


# ==============================================================
# DICIONÁRIO DE CONVERSÕES
# A chave é o nome que aparece no menu; o valor guarda as informações daquela opção.
# "editor" = em vez de converter, abre uma janela de edição (função indicada).
# ==============================================================



CONVERSOES = {
    "PDF para Word": {
        "entrada": "PDF",
        "saida": "Word (.docx)",
        "filtro": [("Arquivos PDF", "*.pdf")],
        "extensao": ".docx",
        "filtro_saida": [("Documento Word", "*.docx")],
        "funcao": pdf_para_word,
    },    
    
    "PDF para Texto": {
        "entrada": "PDF",
        "saida": "Texto (.txt)",
        "filtro": [("Arquivos PDF", "*.pdf")],
        "extensao": ".txt",
        "filtro_saida": [("Arquivo de texto", "*.txt")],
        "funcao": pdf_para_texto,
    },
    
    "Word para PDF": {
        "entrada": "Word (.docx)",
        "saida": "PDF",
        "filtro": [("Documentos Word", "*.docx")],
        "extensao": ".pdf",
        "filtro_saida": [("Arquivos PDF", "*.pdf")],
        "funcao": word_para_pdf,
    },
    "PDF de partitura": {
        "entrada": "PDF de partitura",
        "saida": "PDF com acordes editados",
        "filtro": [("Arquivos PDF", "*.pdf")],
        "funcao": None,
        "editor": abrir_editor,
    },
}

resultado = {}


# ==============================================================
# LÓGICA DA JANELA
# ==============================================================
def atualizar_arquivo():
    caminho = caminho_var.get()
    if caminho:
        arquivo.config(text=Path(caminho).name)
    else:
        arquivo.config(text="Nenhum arquivo selecionado")

def escolher_arquivo():
    info = CONVERSOES[combo.get()]
    # Opções com editor não precisam escolher arquivo aqui: o editor pergunta sozinho
    if info.get("editor"):
        info["editor"](janela)
        return

    escolhido = filedialog.askopenfilename(
        title="Escolha o arquivo",
        filetypes=info["filtro"],
    )
    if escolhido:
        caminho_var.set(escolhido)
        atualizar_arquivo()
        status.config(text="")

""" Essa função lê a opção escolhida com combo.get(), busca as informações no dicionário e atualiza a tela """
def ao_mudar_conversao(evento=None):
    info = CONVERSOES[combo.get()]
    descricao.config(text=f"Entrada: {info['entrada']}  →  Saída: {info['saida']}")
    caminho_var.set("")
    atualizar_arquivo()
    status.config(text="")
    if info.get("editor"):
        botao_escolher.config(text="Abrir editor de partitura")
        botao_converter.config(state="disabled")  # o editor cuida de tudo
    else:
        botao_escolher.config(text="Escolher arquivo")
        botao_converter.config(state="normal")

def executar_conversao(funcao, entrada, saida):
    # Roda em outra thread, para a janela não travar durante a conversão
    try:
        funcao(entrada, saida)
        resultado["erro"] = None
    except Exception as erro:
        resultado["erro"] = erro

def verificar_conversao(thread, saida):
    # Pergunta a cada 0,1 s se a thread terminou
    if thread.is_alive():
        janela.after(100, verificar_conversao, thread, saida)
        return

    barra.stop()
    barra.pack_forget()
    botao_converter.config(state="normal")
    botao_escolher.config(state="normal")
    combo.config(state="readonly")

    if resultado["erro"] is None:
        status.config(text="Pronto!")
        messagebox.showinfo("Pronto!", f"Arquivo salvo em:\n{saida}")
    else:
        status.config(text="Erro na conversão")
        messagebox.showerror("Erro", f"Não foi possível converter:\n{resultado['erro']}")

def ao_clicar_converter():
    info = CONVERSOES[combo.get()]
    entrada = caminho_var.get()

    if info["funcao"] is None:
        messagebox.showinfo("Em breve", "Esta conversão ainda não está disponível.")
        return

    if not entrada:
        messagebox.showwarning("Atenção", "Escolha um arquivo primeiro.")
        return

    saida = filedialog.asksaveasfilename(
        title="Salvar como",
        defaultextension=info["extensao"],
        initialfile=Path(entrada).stem + info["extensao"],
        filetypes=info["filtro_saida"],
    )
    if not saida:
        return

    status.config(text="Convertendo... aguarde")

    botao_converter.config(state="disabled")
    botao_escolher.config(state="disabled")
    combo.config(state="disabled")
    barra.pack(pady=5, before=status)
    barra.start(10)

    thread = threading.Thread(
        target=executar_conversao,
        args=(info["funcao"], entrada, saida),
        daemon=True,
    )
    thread.start()
    verificar_conversao(thread, saida)


# ==============================================================
# CRIAÇÃO DA JANELA PRINCIPAL
# ==============================================================
janela = tk.Tk()
janela.title("Meu Conversor Pessoal")
janela.geometry("480x460")
janela.resizable(False, False)

caminho_var = tk.StringVar()

titulo = ttk.Label(
    janela,
    text="Meu Conversor Pessoal",
    font=("Segoe UI", 16, "bold"),
)
titulo.pack(pady=20)

# Ícone da janela principal (as janelas filhas, como o editor, usam o mesmo)
try:
    janela.iconbitmap(default=caminho_recurso("assets/icone.ico"))
except tk.TclError:
    pass  # sem o ícone o programa funciona do mesmo jeito

rotulo = ttk.Label(janela, text="Tipo de conversão")
rotulo.pack()

combo = ttk.Combobox(
    janela,
    values=list(CONVERSOES.keys()),
    state="readonly",
    width=30,
)
combo.current(0)
combo.pack(pady=5)
combo.bind("<<ComboboxSelected>>", ao_mudar_conversao)

descricao = ttk.Label(janela, text="")
descricao.pack(pady=10)

arquivo = ttk.Label(janela, text="", wraplength=400)
arquivo.pack(pady=5)

botao_escolher = ttk.Button(janela, text="Escolher arquivo", command=escolher_arquivo)
botao_escolher.pack(pady=5)

botao_converter = ttk.Button(janela, text="Converter", command=ao_clicar_converter)
botao_converter.pack(pady=15)

barra = ttk.Progressbar(janela, mode="indeterminate", length=300)

status = ttk.Label(janela, text="")
status.pack()

ao_mudar_conversao()

janela.mainloop()
