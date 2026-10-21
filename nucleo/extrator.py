"""Extrai do conteúdo dos contratos: CNPJs, nome do CONTRATANTE e data de assinatura.

Funciona com .docx (XML), .pdf (pdfplumber, se instalado) e com formatos binários
antigos (.doc, .rtf, .wbk, .htm), dos quais o texto é recuperado decodificando os bytes.
O resultado fica em cache (dados/cache_textos.json) para as próximas análises.
"""
import html
import re
import zipfile
from datetime import date

from .util import cnpj_valido, so_digitos

try:
    import pdfplumber  # opcional
except Exception:  # pragma: no cover
    pdfplumber = None

VERSAO_EXTRATOR = 4

EXT_TEXTO = {".doc", ".docx", ".docm", ".dot", ".dotx", ".rtf", ".wbk", ".htm", ".html", ".txt", ".pdf", ".odt"}

RE_CNPJ = re.compile(r"(?<!\d)(\d{2})\s?\.?\s?(\d{3})\s?\.?\s?(\d{3})\s?/\s?(\d{4})\s?-?\s?(\d{2})(?!\d)")
RE_LIXO = re.compile(r"[^\x20-\x7E\xA0-\xFF\n]")
RE_ESPACOS = re.compile(r"[ \t\r\f\v]+")
MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
RE_DATA_EXTENSO = re.compile(
    r"(\d{1,2})\s*[ºo°]?\s+de\s+(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})",
    re.I,
)
RE_CONTRATANTE = re.compile(r"CONTRATANTES?\s*[:\-–]\s*(.{3,220})")
RE_CONTRATANTE_2 = re.compile(r"denominad[oa]s?\s+(?:simplesmente\s+)?CONTRATANTES?\s*,?\s*(.{3,220})", re.I)
RE_CONTRATADA = re.compile(r"CONTRATAD[OA]S?\s*[:\-–]")
CORTES_NOME = [
    ",", ";", " inscrit", " devidamente", " pessoa jur", " cnpj", " com sede", " neste ato",
    " portador", " brasileir", " estabelecid", " sito", " situad", " registrad", " cpf", " c.n.p.j",
    " empresa ", " sociedade ", " doravante", " residente", " domiciliad", " representad",
]
MARCAS_MODELO = ("xxx", "....", "____", "(nome", "nome da empresa", "razao social da", "razão social da")


def _limpar(texto):
    texto = RE_LIXO.sub(" ", texto)
    texto = texto.replace("FORMTEXT", " ")
    texto = RE_ESPACOS.sub(" ", texto)
    return re.sub(r"\n\s*\n+", "\n", texto)


def _texto_docx(caminho):
    with zipfile.ZipFile(caminho) as z:
        partes = []
        for nome in z.namelist():
            if nome.startswith("word/") and nome.endswith(".xml") and (
                "document" in nome or "header" in nome or "footer" in nome
            ):
                xml = z.read(nome).decode("utf-8", "ignore")
                xml = re.sub(r"</w:p>", "\n", xml)
                xml = re.sub(r"<w:tab/>", " ", xml)
                xml = re.sub(r"<[^>]+>", "", xml)
                partes.append(html.unescape(xml))
        if not partes and "content.xml" in z.namelist():  # .odt
            xml = z.read("content.xml").decode("utf-8", "ignore")
            partes.append(html.unescape(re.sub(r"<[^>]+>", " ", xml)))
        return "\n".join(partes)


def _texto_pdf(caminho):
    if pdfplumber is None:
        return ""
    partes = []
    with pdfplumber.open(caminho) as pdf:
        for pagina in pdf.pages[:6]:
            partes.append(pagina.extract_text() or "")
    return "\n".join(partes)


def _texto_binario(caminho):
    with open(caminho, "rb") as f:
        dados = f.read(8 * 1024 * 1024)
    t1 = dados.decode("cp1252", "ignore")
    t2 = dados.decode("utf-16le", "ignore")
    if caminho.lower().endswith((".htm", ".html")):
        t1 = html.unescape(re.sub(r"<[^>]+>", " ", t1))
    if caminho.lower().endswith(".rtf"):
        t1 = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252", "ignore"), t1)
        t1 = re.sub(r"\\[a-z]+-?\d* ?|[{}]", " ", t1)
    return t1 + "\n" + t2


def ler_texto(caminho, ext):
    if ext in (".docx", ".docm", ".dotx", ".odt"):
        try:
            return _texto_docx(caminho)
        except zipfile.BadZipFile:
            return _texto_binario(caminho)
    if ext == ".pdf":
        return _texto_pdf(caminho)
    return _texto_binario(caminho)


def _cortar_nome(trecho):
    t = trecho.strip(" :-–.,\n")
    t = t.split("\n")[0]
    baixo = t.lower()
    fim = len(t)
    for c in CORTES_NOME:
        i = baixo.find(c)
        if 2 < i < fim:
            fim = i
    nome = t[:fim].strip(" :-–.,")
    nome = re.sub(r"^(a|o|e|à)\s+", "", nome, flags=re.I)
    return nome[:120]


def _parece_modelo(nome):
    baixo = (nome or "").lower()
    return any(m in baixo for m in MARCAS_MODELO)


NAO_E_NOME = {"TEM", "TEEM", "CERTO", "AJUSTADO", "PRESENTE", "SERA", "DEVERA", "FICA", "PODERA", "OBRIGA",
              "OBRIGAM", "RESOLVEM", "FIRMAR", "PARTES", "ACIMA", "QUALIFICAD", "CONTRATADA", "CLAUSULA"}


def _nome_plausivel(nome):
    from .util import normalizar
    palavras = normalizar(nome).split()
    if not palavras or len(palavras) > 14:
        return False
    return not any(p in NAO_E_NOME or p.startswith("QUALIFICAD") for p in palavras[:6])


def _datas(texto):
    datas = []
    for m in RE_DATA_EXTENSO.finditer(texto):
        mes = MESES.get(m.group(2).lower().replace("ç", "c")) or MESES.get(m.group(2).lower())
        try:
            d = date(int(m.group(3)), mes, int(m.group(1)))
        except (TypeError, ValueError):
            continue
        if 1990 <= d.year <= 2100:
            datas.append(d)
    return datas


def analisar_texto(texto, cnpjs_proprios):
    """Recebe o texto bruto e devolve as evidências encontradas."""
    texto = _limpar(texto)
    proprios = set(cnpjs_proprios or [])

    todos = []
    for m in RE_CNPJ.finditer(texto):
        c = "".join(m.groups())
        if cnpj_valido(c) and c not in todos:
            todos.append(c)

    contratada = set()
    for m in RE_CONTRATADA.finditer(texto):
        for c in RE_CNPJ.finditer(texto[m.end(): m.end() + 450]):
            contratada.add("".join(c.groups()))

    contratante = None
    trecho = None
    cnpjs_contratante = []
    modelo_texto = False
    for rx in (RE_CONTRATANTE, RE_CONTRATANTE_2):
        for m in rx.finditer(texto):
            nome = _cortar_nome(m.group(1))
            if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", nome)) < 3:
                continue
            if _parece_modelo(nome):
                modelo_texto = True
                continue
            if not _nome_plausivel(nome):
                continue
            contratante = nome
            ini = max(0, m.start())
            trecho = texto[ini: ini + 330].replace("\n", " ")
            for c in RE_CNPJ.finditer(texto[m.start(): m.start() + 450]):
                cc = "".join(c.groups())
                if cnpj_valido(cc) and cc not in proprios and cc not in cnpjs_contratante:
                    cnpjs_contratante.append(cc)
            break
        if contratante:
            break

    if not contratante and _parece_modelo(texto[:6000]) and texto.lower().count("xxx") >= 2:
        modelo_texto = True

    cliente = cnpjs_contratante or [c for c in todos if c not in proprios and c not in contratada]
    datas = _datas(texto)
    return {
        "tem_texto": len(re.findall(r"[A-Za-zÀ-ÿ]{4,}", texto[:20000])) > 30,
        "cnpjs": todos[:15],
        "cnpjs_cliente": cliente[:6],
        "cnpj_do_contratante": bool(cnpjs_contratante),
        "contratante": contratante,
        "trecho": trecho,
        "modelo_texto": modelo_texto,
        # a última data por extenso costuma ser a da assinatura ("Brasília, 10 de março de 2015")
        "data_texto": datas[-1].isoformat() if datas else None,
    }


def extrair(caminho, ext, cnpjs_proprios):
    if ext not in EXT_TEXTO:
        return {"tem_texto": False, "cnpjs": [], "cnpjs_cliente": [], "contratante": None,
                "trecho": None, "modelo_texto": False, "data_texto": None}
    try:
        texto = ler_texto(caminho, ext)
    except Exception as e:  # arquivo corrompido, protegido por senha, em uso...
        return {"tem_texto": False, "cnpjs": [], "cnpjs_cliente": [], "contratante": None,
                "trecho": None, "modelo_texto": False, "data_texto": None, "erro": str(e)[:200]}
    return analisar_texto(texto, cnpjs_proprios)


__all__ = ["extrair", "analisar_texto", "EXT_TEXTO", "VERSAO_EXTRATOR", "so_digitos"]
