from pathlib import Path
from tkinter import Tk, filedialog, messagebox
from pdf2docx import Converter


def converter(caminho_pdf, caminho_docx):
    cv = Converter(caminho_pdf)
    try:
        cv.convert(caminho_docx)
    finally:
        cv.close()


def main():
    janela = Tk()
    janela.withdraw()
    janela.attributes("-topmost", True)

    entrada = filedialog.askopenfilename(
        title="Escolha o PDF",
        filetypes=[("Arquivos PDF", "*.pdf")],
    )
    if not entrada:
        return

    saida = filedialog.asksaveasfilename(
        title="Salvar como",
        defaultextension=".docx",
        initialfile=Path(entrada).stem + ".docx",
        filetypes=[("Documento Word", "*.docx")],
    )
    if not saida:
        return

    try:
        converter(entrada, saida)
        messagebox.showinfo("Pronto!", f"Arquivo salvo em:\n{saida}")
    except Exception as erro:
        messagebox.showerror("Erro", f"Não foi possível converter:\n{erro}")


main()