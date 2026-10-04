# Conversor PDF para Word

Programa para Windows que converte arquivos PDF em documentos Word (.docx) editáveis, com janelas simples para escolher o arquivo e o local de salvamento.

Criei este projeto para ajudar minha tia, que é professora e vivia precisando transformar PDFs em Word para editar, e também para colocar em prática meus estudos de Python.

## Como usar (sem instalar nada)

1. Baixe o `ConversorPDF.exe` na aba Releases deste repositório.
2. Dê um duplo clique e aguarde a janela abrir (a primeira abertura pode demorar alguns segundos).
3. Escolha o PDF, escolha onde salvar e pronto.

> O Windows pode mostrar o aviso "O Windows protegeu seu PC", porque o programa não tem assinatura digital. Clique em **Mais informações > Executar assim mesmo**.

## Como rodar o código

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python conversor_pdf.py
```

## Como gerar o .exe

```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name ConversorPDF conversor_pdf.py
```

## Tecnologias

- Python
- pdf2docx
- tkinter (interface)
- PyInstaller (empacotamento)

## Limitações

- Funciona com PDFs que têm texto. PDFs escaneados (só imagem) precisariam de OCR.
- Layouts muito complexos podem sofrer pequenos ajustes ao abrir no Word.