"""
Conversões entre PDF e Word.

Este arquivo não conhece janelas: cada função recebe o caminho de entrada e o de saída,
faz a conversão e pronto. Por isso pode ser reaproveitado em outros programas (um site, por exemplo).
"""
import os
import sys


def pdf_para_word(entrada, saida):
    # O import fica aqui dentro para o programa abrir mais rápido
    from pdf2docx import Converter

    cv = Converter(entrada)
    try:
        cv.convert(saida)
    finally:
        cv.close()  # sempre libera o arquivo, mesmo se der erro


def word_para_pdf(entrada, saida):
    # No .exe sem console (--windowed) stdout/stderr não existem; o docx2pdf precisa deles
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    import pythoncom           # vem do pywin32 (só Windows)
    from docx2pdf import convert  # precisa do Microsoft Word instalado

    pythoncom.CoInitialize()   # necessário porque a conversão roda em outra thread
    try:
        convert(entrada, saida)
    finally:
        pythoncom.CoUninitialize()
