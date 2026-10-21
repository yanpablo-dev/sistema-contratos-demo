"""Modelos de contrato (Contábil e Locação/Aluguel) e geração de .docx.

Cada modelo fica em dados/modelos/<id>.json (versão editada) ou padrao_<id>.json (original).
Formato do texto, pensado para ser fácil de editar:
  - parágrafos separados por uma linha em branco
  - "# Título"      -> título centralizado em negrito
  - "## Seção"      -> título de seção em negrito
  - "**texto**"     -> negrito
  - "{{CAMPO}}"     -> substituído pelo valor do campo
  - "[[ASSINATURAS]]" -> quadro de assinaturas (partes + 2 testemunhas); sem o marcador, vai no fim do contrato
  - "?? texto"      -> parágrafo opcional: some do documento se algum {{CAMPO}} dele estiver vazio
Números de cláusula (1.1.1., 2 -), "CLÁUSULA ...:", "CONTRATANTE:" etc. saem em negrito automaticamente.
"""
import html
import io
import os
import re
import uuid
import zipfile
from datetime import date, datetime

from .config import PASTA_DADOS
from .util import formatar_cnpj, ler_json, salvar_json, so_digitos

PASTA_MODELOS = os.path.join(PASTA_DADOS, "modelos")
ARQ_CONTRATANTES = os.path.join(PASTA_DADOS, "contratantes.json")
ARQ_HISTORICO = os.path.join(PASTA_DADOS, "contratos_gerados.json")
IDS_PROPOSTA = ("prop_auditoria", "prop_presumido", "prop_diagnostico", "prop_simples")  # aba "Propostas"
IDS = ("contabil", "aditivo", "locacao", "cobranca", "suspensao", "notificacao", "acordo", "rescisao", "distrato") + IDS_PROPOSTA
IDS_COBRANCA = ("cobranca", "suspensao", "notificacao", "acordo", "rescisao", "distrato")  # aba "Cobrança / Termos de Acordo"
PASTA_COBRANCA = "Cobranças e Acordos"  # subpasta da pasta de contratos (fora da análise de contratos)
PASTA_PROPOSTAS = "Propostas"  # idem, para as propostas comerciais
CAMPOS_AUTOMATICOS = {"VALOR_EXTENSO", "FORMA_PAGAMENTO", "PARCELAS_TABELA",
                      "DATA_POS_ENCERRAMENTO", "MES_ENCERRAMENTO", "TEXTO_DEBITO",
                      "PRECO_TABELA", "TOTAL_HORAS", "VALOR_TOTAL", "VALOR_TOTAL_EXTENSO",  # proposta de auditoria
                      "PARCELA_1", "PARCELA_1_EXTENSO", "PARCELA_2", "PARCELA_2_EXTENSO", "PARCELA_3", "PARCELA_3_EXTENSO"}
EM_NEGRITO = {"RAZAO_SOCIAL", "REPRESENTANTE", "CNPJ"}
MAIUSCULAS = {"RAZAO_SOCIAL", "REPRESENTANTE", "NACIONALIDADE"}
NAO_LEMBRAR = {"NUMERO_CONTRATO", "NUMERO_PROPOSTA", "DATA_INICIO", "DATA_ASSINATURA",  # não reaproveita entre contratos
               "VENCIMENTOS", "VALOR_DEBITO", "PRAZO_DIAS", "DATA_ATUALIZACAO", "PERIODO_DEBITO", "VALOR_ENTRADA", "DATA_ENTRADA",
               "QTD_PARCELAS", "VALOR_PARCELA", "DATA_PRIMEIRA_PARCELA"}  # cada cobrança/acordo tem seus valores
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]


class ErroModelo(Exception):
    pass


# ================================================================ modelos
def _arq(id_, editado=True):
    return os.path.join(PASTA_MODELOS, f"{id_}.json" if editado else f"padrao_{id_}.json")


def carregar(id_):
    if id_ not in IDS:
        raise ErroModelo("Modelo desconhecido.")
    m = ler_json(_arq(id_), None)
    editado = m is not None
    if m is None:
        m = ler_json(_arq(id_, False), None)
    if m is None:
        raise ErroModelo(f"Arquivo do modelo '{id_}' não encontrado em dados\\modelos.")
    m["editado"] = editado
    return m


def listar():
    return [carregar(i) for i in IDS]


def salvar(id_, texto, campos, usuario):
    m = carregar(id_)
    usados = set(re.findall(r"\{\{(\w+)\}\}", texto))
    chaves = {c["chave"] for c in campos}
    extensos = {c["chave"] + "_EXTENSO" for c in campos if c.get("tipo") == "dinheiro"}
    faltam = sorted(usados - chaves - CAMPOS_AUTOMATICOS - extensos)
    if faltam:
        raise ErroModelo("O texto usa campos que não existem na lista: " + ", ".join(faltam) +
                         ". Adicione-os em “Campos” ou corrija o nome.")
    for c in campos:
        if not re.fullmatch(r"[A-Z0-9_]+", c.get("chave") or ""):
            raise ErroModelo(f"Nome de campo inválido: {c.get('chave')!r} (use só letras maiúsculas, números e _).")
    m.update(texto=texto, campos=campos, alterado_por=usuario,
             alterado_em=datetime.now().isoformat(timespec="seconds"))
    m.pop("editado", None)
    salvar_json(_arq(id_), m)
    return carregar(id_)


def restaurar(id_):
    if os.path.exists(_arq(id_)):
        os.remove(_arq(id_))
    return carregar(id_)


# ================================================================ valores
UNIDADES = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze",
            "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
DEZENAS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
CENTENAS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos",
            "oitocentos", "novecentos"]


def _ate_mil(n):
    if n == 0:
        return ""
    if n == 100:
        return "cem"
    c, r = divmod(n, 100)
    partes = [CENTENAS[c]] if c else []
    if r:
        if r < 20:
            partes.append(UNIDADES[r])
        else:
            d, u = divmod(r, 10)
            partes.append(DEZENAS[d] + (f" e {UNIDADES[u]}" if u else ""))
    return " e ".join(partes)


def _inteiro_extenso(n):
    if n == 0:
        return "zero"
    grupos = []
    for nome_s, nome_p in (("", ""), ("mil", "mil"), ("milhão", "milhões"), ("bilhão", "bilhões")):
        n, g = divmod(n, 1000)
        grupos.append((g, nome_s, nome_p))
        if not n:
            break
    partes = []
    for g, s, p in reversed(grupos):
        if not g:
            continue
        if s == "mil":
            partes.append("mil" if g == 1 else f"{_ate_mil(g)} mil")
        elif s:
            partes.append(f"{_ate_mil(g)} {s if g == 1 else p}")
        else:
            partes.append(_ate_mil(g))
    # "mil e cem", "dois mil e quinhentos"; "mil, duzentos e trinta"
    texto = partes[0]
    for p in partes[1:]:
        ult = grupos[0][0]
        texto += (" e " if (p == partes[-1] and (ult < 100 or ult % 100 == 0)) else ", ") + p
    return texto


def valor_extenso(valor):
    """'1.500,50' -> 'Mil e quinhentos reais e cinquenta centavos'."""
    centavos_total = round(_numero(valor) * 100)
    reais, cent = divmod(centavos_total, 100)
    partes = []
    if reais:
        sufixo = "real" if reais == 1 else ("de reais" if reais % 1_000_000 == 0 else "reais")
        partes.append(f"{_inteiro_extenso(reais)} {sufixo}")
    if cent:
        partes.append(f"{_inteiro_extenso(cent)} {'centavo' if cent == 1 else 'centavos'}")
    texto = " e ".join(partes) or "zero reais"
    return texto[0].upper() + texto[1:]


def _numero(valor):
    s = str(valor or "").strip().replace("R$", "").replace(" ", "")
    if not s:
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):  # "2.000" e "1.500.000" = milhar, não decimal
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        raise ErroModelo(f"Valor inválido: {valor!r}")


def formatar_dinheiro(valor):
    n = _numero(valor)
    inteiro, dec = f"{n:,.2f}".split(".")
    return inteiro.replace(",", ".") + "," + dec


def data_extenso(d):
    return f"{d.day:02d} de {MESES[d.month - 1]} de {d.year}"


def _data(v):
    v = (v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


def preparar_valores(modelo, brutos):
    """Aplica padrões, formatações e campos automáticos. Retorna (valores, faltando)."""
    vals = {}
    for c in modelo["campos"]:
        k = c["chave"]
        v = str(brutos.get(k) if brutos.get(k) not in (None, "") else (c.get("padrao") or "")).strip()
        tipo = c.get("tipo")
        if v:
            if tipo == "dinheiro":
                v = formatar_dinheiro(v)
            elif tipo == "data":
                d = _data(v)
                v = d.strftime("%d.%m.%Y") if d else v
            elif tipo == "data_extenso":
                d = _data(v)
                v = data_extenso(d) if d else v
            elif tipo == "numero" and v.isdigit():
                v = f"{int(v):02d} ({_inteiro_extenso(int(v))})"  # 3 -> "03 (três)"
            elif k == "CNPJ":
                v = formatar_cnpj(v) if len(so_digitos(v)) in (11, 14) else v
            elif k == "CPF" and len(so_digitos(v)) == 11:
                v = formatar_cnpj(v)
            if k in MAIUSCULAS:
                v = v.upper()
        elif tipo == "data_extenso":
            v = data_extenso(date.today())
        vals[k] = v
    if str(brutos.get("SEM_ASSINATURAS") or "").lower() in ("1", "true", "sim"):
        vals["SEM_ASSINATURAS"] = "1"  # sem linhas e nomes de assinatura (ex.: assinatura pelo Autentique)
    if "QTD_PARCELAS" in vals:
        _calcular_acordo(vals)
    if "DATA_ENCERRAMENTO" in vals:
        _calcular_encerramento(vals)
    if "HORAS_COORDENACAO" in vals:
        _calcular_auditoria(vals)
    if "VALOR" in vals:
        vals["VALOR_EXTENSO"] = valor_extenso(vals["VALOR"]) if vals["VALOR"] else ""
    for c in modelo["campos"]:  # todo valor em dinheiro ganha o seu _EXTENSO
        if c.get("tipo") == "dinheiro":
            v = vals.get(c["chave"])
            vals[c["chave"] + "_EXTENSO"] = valor_extenso(v) if v else ""
    faltando = [c["rotulo"] for c in modelo["campos"] if c.get("obrigatorio") and not vals.get(c["chave"])]
    return vals, faltando


def _somar_meses(d, n):
    import calendar
    a, m = divmod(d.month - 1 + n, 12)
    ano, mes = d.year + a, m + 1
    return d.replace(year=ano, month=mes, day=min(d.day, calendar.monthrange(ano, mes)[1]))


def _calcular_encerramento(vals):
    """Rescisão e distrato: dia seguinte ao encerramento, mês de encerramento e o parágrafo do débito."""
    from datetime import timedelta
    fim = _data(vals.get("DATA_ENCERRAMENTO"))
    vals["DATA_POS_ENCERRAMENTO"] = (fim + timedelta(days=1)).strftime("%d.%m.%Y") if fim else ""
    vals["MES_ENCERRAMENTO"] = f"{MESES[fim.month - 1]} de {fim.year}" if fim else ""
    if "VALOR_DEBITO" in vals:
        v = vals.get("VALOR_DEBITO")
        vals["TEXTO_DEBITO"] = (
            f"Fica expressamente declarado e reconhecido pelas partes o débito da Contratante junto à Contratada no valor de "
            f"R$ {v} ({valor_extenso(v).lower()}), correspondente a honorários em atraso. Este montante será objeto de "
            "acordo amigável formalizado em separado ou, na falta deste, cobrado por meio das medidas judicialmente cabíveis."
            if v else "As partes declaram que, na data deste distrato, não há honorários em atraso devidos pela Contratante à Contratada.")


def _calcular_auditoria(vals):
    """Proposta de auditoria: quadro de horas x valor da hora, total e as 3 parcelas (30% / 40% / 30%)."""
    def horas(k):
        m = re.search(r"\d+", vals.get(k) or "")
        return int(m.group()) if m else 0
    auditor, assistente = _numero(vals.get("VALOR_HORA_AUDITOR")), _numero(vals.get("VALOR_HORA_ASSISTENTE"))
    linhas = [("Coordenar o trabalho e elaborar pareceres", "Auditor", horas("HORAS_COORDENACAO"), auditor),
              ("Elaboração de relatórios de auditoria, análise de sistemas de informação, balancetes e balanços, "
               "emissão de parecer e supervisão", "Auditor", horas("HORAS_RELATORIOS"), auditor),
              ("Análise de contas patrimoniais e de resultado (receitas/despesas)", "Assistente", horas("HORAS_ANALISE"), assistente)]
    total_h = sum(l[2] for l in linhas)
    total = round(sum(l[2] * l[3] for l in linhas), 2)
    quadro = ["| **Descrição dos serviços** | **Profissional** | **Horas** | **R$ / hora** | **Total R$** |"]
    quadro += [f"| {d} | {p} | {h} | {formatar_dinheiro(v)} | {formatar_dinheiro(h * v)} |" for d, p, h, v in linhas]
    quadro.append(f"| **Totais** | | **{total_h}** | | **{formatar_dinheiro(total)}** |")
    vals["PRECO_TABELA"] = "\n".join(quadro)
    vals["TOTAL_HORAS"] = f"{total_h} ({_inteiro_extenso(total_h)})" if total_h else ""
    vals["VALOR_TOTAL"] = formatar_dinheiro(total) if total else ""
    vals["VALOR_TOTAL_EXTENSO"] = valor_extenso(total).lower() if total else ""
    p1 = p3 = round(total * 0.3, 2)
    p2 = round(total - p1 - p3, 2)  # os centavos que sobram ficam na parcela do meio
    for i, p in enumerate((p1, p2, p3), 1):
        vals[f"PARCELA_{i}"] = formatar_dinheiro(p) if total else ""
        vals[f"PARCELA_{i}_EXTENSO"] = valor_extenso(p).lower() if total else ""


def _calcular_acordo(vals):
    """Termo de acordo: valor da parcela (se vazio), texto da forma de pagamento e cronograma de parcelas."""
    vals["FORMA_PAGAMENTO"], vals["PARCELAS_TABELA"] = "", ""
    m = re.match(r"\d+", vals.get("QTD_PARCELAS") or "")
    n = int(m.group()) if m else 0
    total, entrada = _numero(vals.get("VALOR_DEBITO")), _numero(vals.get("VALOR_ENTRADA"))
    primeira = _data(vals.get("DATA_PRIMEIRA_PARCELA"))
    if not total or n <= 0 or entrada >= total:
        return
    resto = round(total - entrada, 2)
    if vals.get("VALOR_PARCELA"):
        parcelas = [_numero(vals["VALOR_PARCELA"])] * n
    else:  # parcelas iguais; os centavos que sobram vão na última
        base = int(resto * 100 / n) / 100
        parcelas = [base] * (n - 1) + [round(resto - base * (n - 1), 2)]
        vals["VALOR_PARCELA"] = formatar_dinheiro(parcelas[0])
    rs = lambda x: f"R$ {formatar_dinheiro(x)} ({valor_extenso(x)})"
    br = lambda d: d.strftime("%d/%m/%Y")
    if n == 1:
        forma = f"em parcela única de {rs(parcelas[0])}" + (f", com vencimento em {br(primeira)}" if primeira else "")
    else:
        iguais = parcelas[-1] == parcelas[0]
        forma = (f"em {vals['QTD_PARCELAS']} parcelas mensais {'e iguais ' if iguais else ''}de {rs(parcelas[0])}"
                 + ("" if iguais else f", sendo a última de {rs(parcelas[-1])}"))
        if primeira:
            forma += f", vencendo a primeira em {br(primeira)} e as demais no dia {primeira.day:02d} dos meses subsequentes"
    if entrada:
        dent = _data(vals.get("DATA_ENTRADA"))
        forma = (f"sendo {rs(entrada)} pagos a título de entrada" + (f", em {br(dent)}" if dent else "")
                 + f", e o restante, {rs(resto)}, " + forma)
    vals["FORMA_PAGAMENTO"] = forma
    linhas = ["| **Parcela** | **Vencimento** | **Valor** |"]
    if entrada:
        dent = _data(vals.get("DATA_ENTRADA"))
        linhas.append(f"| Entrada | {br(dent) if dent else '____/____/______'} | R$ {formatar_dinheiro(entrada)} |")
    for i, p in enumerate(parcelas):
        venc = br(_somar_meses(primeira, i)) if primeira else "____/____/______"
        linhas.append(f"| {i + 1}ª parcela | {venc} | R$ {formatar_dinheiro(p)} |")
    linhas.append(f"| **Total** | | **R$ {formatar_dinheiro(entrada + sum(parcelas))}** |")
    vals["PARCELAS_TABELA"] = "\n".join(linhas)


def preencher_texto(texto, vals):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: vals.get(m.group(1)) or "________", texto)


# ================================================================ contratantes (dados lembrados)
POR_MODELO = {"VALOR"}  # honorário contábil e aluguel são valores diferentes
GRUPO_VALOR = {"aditivo": "contabil"}  # o termo aditivo usa o mesmo honorário do contrato contábil


def contratante(chave, id_=None):
    id_ = GRUPO_VALOR.get(id_, id_)
    dados = dict(ler_json(ARQ_CONTRATANTES, {}).get(chave) or {})
    for k in POR_MODELO:
        v = dados.pop(f"{k}@{id_}", None)
        if v:
            dados[k] = v
    return {k: v for k, v in dados.items() if "@" not in k}


def lembrar_contratante(chave, vals, id_=None):
    if not chave:
        return
    id_ = GRUPO_VALOR.get(id_, id_)
    todos = ler_json(ARQ_CONTRATANTES, {})
    atual = todos.get(chave, {})
    for k, v in vals.items():
        if k in NAO_LEMBRAR or k in CAMPOS_AUTOMATICOS or not v:
            continue
        atual[f"{k}@{id_}" if k in POR_MODELO else k] = v
    todos[chave] = atual
    salvar_json(ARQ_CONTRATANTES, todos)


def historico():
    return ler_json(ARQ_HISTORICO, [])


def registrar(reg):
    h = historico()
    h.append(reg)
    salvar_json(ARQ_HISTORICO, h)


def atualizar_registro(id_, campos):
    """Atualiza um contrato do histórico (ex.: depois de editado)."""
    h = historico()
    for reg in h:
        if reg.get("id") == id_:
            reg.update(campos)
    salvar_json(ARQ_HISTORICO, h)


# ================================================================ DOCX
W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
ROTULO_NEGRITO = re.compile(
    r"^((?:\d+(?:\.\d+)*\.?\s*-\s*)|(?:\d+(?:\.\d+)+\.)|(?:\d+\.\s)|"
    r"(?:CONTRATADA:|CONTRATANTE:|CL[ÁA]USULA [A-ZÁÉÍÓÚÂÊÔÃÕÇ ]+:|Par[áa]grafo [A-Za-zÁÉÍÓÚáéíóúçã ]+?\s*[-:]))")


def _esc(t):
    return html.escape(t, quote=False)


EMOJI = re.compile("([\U0001F000-\U0001FAFF☀-➿⬀-⯿][️]?)")


def _run(texto, negrito=False, tamanho=None, fonte=None, destaque=False, cor=None):
    if not fonte and EMOJI.search(texto):  # Arial não tem emojis: usa a fonte de emojis do Windows neles
        return "".join(_run(p, negrito, tamanho, "Segoe UI Emoji" if EMOJI.fullmatch(p) else None, destaque, cor)
                        for p in EMOJI.split(texto) if p)
    props = []
    if fonte:
        props.append(f'<w:rFonts w:ascii="{fonte}" w:hAnsi="{fonte}" w:cs="{fonte}"/>')
    if negrito:
        props.append("<w:b/><w:bCs/>")
    if cor:
        props.append(f'<w:color w:val="{cor}"/>')
    if tamanho:
        props.append(f'<w:sz w:val="{tamanho}"/><w:szCs w:val="{tamanho}"/>')
    if destaque:
        props.append('<w:highlight w:val="yellow"/>')
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{_esc(texto)}</w:t></w:r>'


def _segmentos(texto, vals):
    """Divide o parágrafo em runs, tratando **negrito** e {{CAMPOS}}."""
    m = ROTULO_NEGRITO.match(texto)
    if m and not texto.startswith("**"):
        texto = f"**{m.group(1)}**" + texto[m.end():]
    runs = []
    for parte in re.split(r"(\*\*.+?\*\*)", texto):
        if not parte:
            continue
        negrito = parte.startswith("**") and parte.endswith("**") and len(parte) > 4
        if negrito:
            parte = parte[2:-2]
        for p2 in re.split(r"(\{\{\w+\}\})", parte):
            if not p2:
                continue
            mc = re.fullmatch(r"\{\{(\w+)\}\}", p2)
            if mc:
                v = vals.get(mc.group(1))
                if v:
                    runs.append(_run(v, negrito or mc.group(1) in EM_NEGRITO))
                else:
                    runs.append(_run("________", negrito, destaque=True))
            else:
                runs.append(_run(p2, negrito))
    return "".join(runs)


def _paragrafo(conteudo, alinhamento="both", antes=0, depois=200, mantem=False, linha=360):
    ppr = (f'<w:pPr>{"<w:keepNext/>" if mantem else ""}<w:spacing w:before="{antes}" w:after="{depois}" '
           f'w:line="{linha}" w:lineRule="auto"/><w:jc w:val="{alinhamento}"/></w:pPr>')
    return f"<w:p>{ppr}{conteudo}</w:p>"


def _imagem(rid, largura_pt, altura_pt, id_, nome):
    cx, cy = int(largura_pt * 12700), int(altura_pt * 12700)
    return (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{id_}" name="{nome}"/><wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/>'
            f'</wp:cNvGraphicFramePr><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{id_}" name="{nome}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
            f'</wp:inline></w:drawing></w:r>')


def _tabela(linhas, larguras, bordas=False, margem_meio=None):
    b = 'w:val="single" w:sz="8" w:space="0" w:color="000000"' if bordas else 'w:val="nil"'
    grade = "".join(f'<w:gridCol w:w="{w}"/>' for w in larguras)
    margens = ('<w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
               '<w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>') if bordas else ""
    if margem_meio:  # afasta as colunas (ex.: as duas linhas de assinatura não se encostam)
        margens = (f'<w:tblCellMar><w:left w:w="{margem_meio}" w:type="dxa"/>'
                   f'<w:right w:w="{margem_meio}" w:type="dxa"/></w:tblCellMar>')
    corpo = ""
    for celulas in linhas:
        corpo += "<w:tr><w:trPr><w:cantSplit/></w:trPr>"
        for conteudo, w in zip(celulas, larguras):
            corpo += (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/><w:vAlign w:val="center"/></w:tcPr>'
                      f'{conteudo or "<w:p/>"}</w:tc>')
        corpo += "</w:tr>"
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{sum(larguras)}" w:type="dxa"/><w:jc w:val="center"/>'
            f'<w:tblBorders><w:top {b}/><w:left {b}/><w:bottom {b}/><w:right {b}/>'
            f'<w:insideH {b}/><w:insideV {b}/></w:tblBorders><w:tblLayout w:type="fixed"/>{margens}</w:tblPr>'
            f'<w:tblGrid>{grade}</w:tblGrid>{corpo}</w:tbl>')


def _linhas_quadro(bloco):
    """Bloco escrito como '| célula | célula |' (uma linha por linha do quadro) -> lista de células, ou None."""
    linhas = [l.strip() for l in bloco.splitlines() if l.strip()]
    if not linhas or not all(l.startswith("|") for l in linhas):
        return None
    return [[c.strip() for c in l.strip().strip("|").split("|")] for l in linhas]


def _bloco_especial(bloco, vals):
    """[[PARCELAS]] / [[PRECO]] viram o quadro montado no cálculo; '?? ...' some se faltar algum campo dele."""
    b = bloco.strip()
    m = re.fullmatch(r"\[\[(PARCELAS|PRECO)\]\]", b)
    if m:
        return vals.get(m.group(1) + "_TABELA") or ""
    if b.startswith("?? "):
        b = b[3:]
        return "" if any(not vals.get(k) for k in re.findall(r"\{\{(\w+)\}\}", b)) else b
    return bloco


def _quadro_docx(linhas, vals):
    ncol = max(len(l) for l in linhas)
    larguras = ([6900, 2040] if ncol == 2 else [3540, 1350, 1000, 1450, 1600] if ncol == 5
                else [8940 // ncol] * ncol)
    rows = []
    for l in linhas:
        l = l + [""] * (ncol - len(l))
        rows.append([_paragrafo(_segmentos(c, vals), "left" if i == 0 else "center", 0, 0, linha=276)
                     for i, c in enumerate(l)])
    return _tabela(rows, larguras, bordas=True) + _paragrafo("", "left", 0, 60)


# ---------------------------------------------------------------- padrão visual (comum ao Word e ao PDF)
COR = "1F4E8C"  # azul Alfa: títulos de cláusula e linhas de separação
LOCAL_DATA = "Brasília/DF, _____ de ______________________ de ________."
ENDERECOS = [("Matriz", "Av. Exemplo, 1000, Sala 101, Centro, Brasília/DF"),
             ("Filial", "Rua Modelo, 200, Sala 305, Centro, Brasília/DF")]


def _partes(modelo):
    return modelo.get("assinaturas") or [["CONTRATADA", "CONTRATADA"], ["{{RAZAO_SOCIAL}}", "CONTRATANTE"]]


def _eh_clausula(titulo):
    """'## 1. - DO OBJETO' é cláusula (destaque azul); '## ÁREA CONTÁBIL:' é subtítulo."""
    return bool(re.match(r"\d", titulo)) or titulo.upper().startswith("CLÁUSULA")


def _sem_data(modelo):
    return "DATA_ASSINATURA" not in modelo["texto"]


def _borda(lado, cor=COR, esp=8):
    return f'<w:pBdr><w:{lado} w:val="single" w:sz="{esp}" w:space="4" w:color="{cor}"/></w:pBdr>'


def _p(conteudo, alinhamento="left", antes=0, depois=0, linha=240, extra="", mantem=False):
    """Parágrafo com propriedades extras (bordas etc.), usado no cabeçalho, rodapé e títulos."""
    return (f'<w:p><w:pPr>{"<w:keepNext/>" if mantem else ""}{extra}<w:spacing w:before="{antes}" w:after="{depois}" '
            f'w:line="{linha}" w:lineRule="auto"/><w:jc w:val="{alinhamento}"/></w:pPr>{conteudo}</w:p>')


def _linha_assinatura(altura):
    """Espaço em branco de 'altura' (twips) terminando numa linha contínua, da largura da célula.
    Altura exata em vez de 'espaço antes', que o Word ignora no topo de uma célula."""
    return (f'<w:p><w:pPr><w:keepNext/>{_borda("bottom", "000000", 6)}<w:spacing w:before="0" w:after="0" '
            f'w:line="{altura}" w:lineRule="exact"/></w:pPr></w:p>')


def _espaco_assinatura(modelo):
    """Multiplicador do espaço em branco acima das linhas de assinatura (no JSON do modelo; 1 = padrão)."""
    try:
        return min(max(float(modelo.get("espaco_assinatura") or 1), 0.5), 3)
    except (TypeError, ValueError):
        return 1.0


# parágrafo mínimo que começa uma folha nova
FOLHA_NOVA = ('<w:p><w:pPr><w:pageBreakBefore/><w:spacing w:before="0" w:after="0" w:line="20" w:lineRule="exact"/>'
              '<w:rPr><w:sz w:val="2"/></w:rPr></w:pPr></w:p>')


def _assinaturas(modelo, vals):
    if vals.get("SEM_ASSINATURAS"):
        return ""  # sem o quadro: o documento termina no texto (o espaço que sobra na folha é para assinar)
    return _quadro_assinaturas(modelo, vals)


def _manter_com_assinaturas(xml, vals):
    """Os dois parágrafos antes do quadro ("E, por estarem justos...", "Atenciosamente,") ficam na mesma folha dele."""
    if vals.get("SEM_ASSINATURAS"):
        return
    for i in (-2, -1):
        if len(xml) >= 2 and xml[i].startswith("<w:p><w:pPr>") and "<w:keepNext/>" not in xml[i]:
            xml[i] = xml[i].replace("<w:pPr>", "<w:pPr><w:keepNext/>", 1)


def _quadro_assinaturas(modelo, vals):
    fator = _espaco_assinatura(modelo)

    def bloco(nome, papel):
        nome = preencher_texto(nome, vals)
        # espaço em branco generoso acima da linha para caber a assinatura
        return (_linha_assinatura(int(1050 * fator)) +
                _p(_run(nome, True, 21), "center", 60, 0, 276, mantem=True) +
                _p(_run(papel, False, 21), "center", 0, 200, 276, mantem=True))

    def testemunha():
        return (_linha_assinatura(int(850 * fator)) +
                _p(_run("Nome:", False, 21), "left", 80, 120, 276) +
                _p(_run("CPF:", False, 21), "left", 0, 200, 276))

    partes = _partes(modelo)
    com_testemunhas = modelo.get("testemunhas", True)
    t = _p(_run(LOCAL_DATA), "right", 480, 0, 360, mantem=True) if _sem_data(modelo) else ""
    if len(partes) == 1 and not com_testemunhas:  # notificações: só a Alfa assina, ao centro
        return t + _tabela([[bloco(*partes[0])]], [5200], margem_meio=240)
    # partes, título e testemunhas numa tabela só, presa numa página (keepNext em todas as linhas menos a última)
    linhas = [[bloco(*partes[i]), bloco(*partes[i + 1]) if i + 1 < len(partes) else _p("", mantem=True)]
              for i in range(0, len(partes), 2)]
    if com_testemunhas:
        titulo = _p(_run("TESTEMUNHAS", True, 21, cor=COR), antes=360, depois=0, mantem=True)
        linhas.append([titulo, _p("", antes=360, mantem=True)])
        linhas.append([testemunha(), testemunha()])
    return t + _tabela(linhas, [4470, 4470], margem_meio=240)


def _corpo(modelo, vals):
    xml = []
    tem_assinaturas = False
    for bloco in re.split(r"\n\s*\n", modelo["texto"].strip()):
        bloco = _bloco_especial(bloco, vals)
        quadro = _linhas_quadro(bloco)
        if quadro:
            xml.append(_quadro_docx(quadro, vals))
            continue
        bloco = " ".join(l.strip() for l in bloco.splitlines()).strip()
        if not bloco:
            continue
        if bloco == "[[ASSINATURAS]]":
            _manter_com_assinaturas(xml, vals)
            xml.append(_assinaturas(modelo, vals))
            tem_assinaturas = True
        elif bloco.startswith(">> "):  # alinhado à direita (local e data)
            xml.append(_paragrafo(_segmentos(bloco[3:].strip(), vals), "right", 360 if tem_assinaturas else 0, 360))
        elif bloco.startswith("# "):
            xml.append(_p(_segmentos(f"**{bloco[2:].strip()}**", vals).replace("<w:b/>", '<w:b/><w:sz w:val="28"/>'),
                          "center", 0, 480, 276))
        elif bloco.startswith("## "):
            titulo = bloco[3:].strip()
            if _eh_clausula(titulo):
                xml.append(_p(_segmentos(f"**{titulo.upper()}**", vals).replace("<w:b/>", f'<w:b/><w:color w:val="{COR}"/>'),
                              "left", 400, 200, 276, extra=_borda("bottom", esp=4), mantem=True))
            else:
                xml.append(_p(_segmentos(f"**{titulo}**", vals), "left", 240, 120, 276, mantem=True))
        else:
            xml.append(_paragrafo(_segmentos(bloco, vals)))
    if not tem_assinaturas:  # todo documento termina com o quadro de assinaturas (ou folha em branco, sem o quadro)
        _manter_com_assinaturas(xml, vals)
        xml.append(_assinaturas(modelo, vals))
    # o Word exige um parágrafo depois de uma tabela no fim do documento; mínimo, para não criar página em branco
    xml.append('<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="20" w:lineRule="exact"/>'
               '<w:rPr><w:sz w:val="2"/></w:rPr></w:pPr></w:p>')
    return "".join(xml)


def _numero_cabecalho(modelo, vals):
    """'CONTRATO Nº 123' (ou 'PROPOSTA Nº 047 / 2026' nas propostas)."""
    numero = vals.get(modelo.get("campo_numero") or "NUMERO_CONTRATO") or "____________"
    return f'{modelo.get("rotulo_numero") or "CONTRATO Nº"} {numero}'


def _cabecalho(modelo, vals):
    direita = ""
    if modelo.get("mostrar_numero", True):
        direita += _p(_run(_numero_cabecalho(modelo, vals), True, 22, cor=COR), "right", 0, 120)
    direita += (_p(_run("Telefone (61) 4000-0000", False, 17), "right") +
                _p(_run("www.alfacontabil.example", False, 17), "right"))
    logo = _p(_imagem("rIdLogo", 62, 64, 101, "Logo Alfa"))
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr {W_NS}>'
            f'{_tabela([[logo, direita]], [3000, 5940])}{_p("", extra=_borda("bottom", esp=12))}</w:hdr>')


def _rodape(modelo):
    # espaço em branco no pé de todas as páginas, para as rubricas das partes
    rubricas = _p("", antes=1000)
    enderecos = "".join(_p(_run(f"{rot}: ", True, 15) + _run(txt, False, 15), "left") for rot, txt in ENDERECOS)
    pagina = ''.join(f'<w:r><w:rPr><w:sz w:val="16"/></w:rPr>{x}</w:r>' for x in (
        '<w:t xml:space="preserve">Página </w:t>', '<w:fldChar w:fldCharType="begin"/>',
        '<w:instrText xml:space="preserve"> PAGE </w:instrText>', '<w:fldChar w:fldCharType="separate"/>',
        '<w:t>1</w:t>', '<w:fldChar w:fldCharType="end"/>'))
    direita = _p(pagina + _run("   ") + _imagem("rIdQr", 32, 32, 102, "QR Code"), "right")
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {W_NS}>'
            f'{rubricas}{_p("", depois=80, extra=_borda("bottom", esp=6))}'
            f'{_tabela([[enderecos, direita]], [6740, 2200])}</w:ftr>')


def gerar_docx(modelo, vals):
    documento = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W_NS}><w:body>'
                 f'{_corpo(modelo, vals)}'
                 '<w:sectPr><w:headerReference w:type="default" r:id="rIdHdr"/>'
                 '<w:footerReference w:type="default" r:id="rIdFtr"/>'
                 '<w:pgSz w:w="12240" w:h="15840"/>'
                 '<w:pgMar w:top="2300" w:right="1650" w:bottom="3200" w:left="1650" w:header="500" w:footer="360" w:gutter="0"/>'
                 '</w:sectPr></w:body></w:document>')
    estilos = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W_NS}><w:docDefaults>'
               '<w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial" w:eastAsia="Arial"/>'
               '<w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="pt-BR"/></w:rPr></w:rPrDefault>'
               '<w:pPrDefault><w:pPr><w:spacing w:after="200" w:line="360" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
               '</w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
               '</w:styles>')
    tipos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Default Extension="jpg" ContentType="image/jpeg"/><Default Extension="png" ContentType="image/png"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
             '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
             '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
             '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
             '</Types>')
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    rels_raiz = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 f'<Relationship Id="rId1" Type="{rel}/officeDocument" Target="word/document.xml"/>'
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                 '</Relationships>')
    rels_doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'<Relationship Id="rIdSty" Type="{rel}/styles" Target="styles.xml"/>'
                f'<Relationship Id="rIdHdr" Type="{rel}/header" Target="header1.xml"/>'
                f'<Relationship Id="rIdFtr" Type="{rel}/footer" Target="footer1.xml"/>'
                '</Relationships>')
    rels_hdr = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'<Relationship Id="rIdLogo" Type="{rel}/image" Target="media/logo.jpg"/></Relationships>')
    rels_ftr = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'<Relationship Id="rIdQr" Type="{rel}/image" Target="media/qrcode.png"/></Relationships>')
    agora = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{_esc(modelo["nome"])}</dc:title><dc:creator>Alfa - Sistema de Contratos</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{agora}</dcterms:created></cp:coreProperties>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", tipos)
        z.writestr("_rels/.rels", rels_raiz)
        z.writestr("docProps/core.xml", core)
        z.writestr("word/document.xml", documento)
        z.writestr("word/styles.xml", estilos)
        z.writestr("word/header1.xml", _cabecalho(modelo, vals))
        z.writestr("word/footer1.xml", _rodape(modelo))
        z.writestr("word/_rels/document.xml.rels", rels_doc)
        z.writestr("word/_rels/header1.xml.rels", rels_hdr)
        z.writestr("word/_rels/footer1.xml.rels", rels_ftr)
        for nome in ("logo.jpg", "qrcode.png"):
            caminho = os.path.join(PASTA_MODELOS, nome)
            if os.path.exists(caminho):
                with open(caminho, "rb") as f:
                    z.writestr(f"word/media/{nome}", f.read())
    return buf.getvalue()


# ================================================================ PDF (via Microsoft Edge, que já vem no Windows)
NAVEGADORES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _inline_html(texto, vals):
    m = ROTULO_NEGRITO.match(texto)
    if m and not texto.startswith("**"):
        texto = f"**{m.group(1)}**" + texto[m.end():]
    saida = []
    for parte in re.split(r"(\*\*.+?\*\*)", texto):
        if not parte:
            continue
        negrito = parte.startswith("**") and parte.endswith("**") and len(parte) > 4
        if negrito:
            parte = parte[2:-2]
        trecho = ""
        for p2 in re.split(r"(\{\{\w+\}\})", parte):
            mc = re.fullmatch(r"\{\{(\w+)\}\}", p2 or "")
            if mc:
                v = vals.get(mc.group(1))
                if v:
                    trecho += f"<b>{html.escape(v)}</b>" if mc.group(1) in EM_NEGRITO and not negrito else html.escape(v)
                else:
                    trecho += '<span class="falta">________</span>'
            else:
                trecho += html.escape(p2 or "")
        saida.append(f"<b>{trecho}</b>" if negrito else trecho)
    return "".join(saida)


def _data_uri(nome, tipo):
    import base64
    caminho = os.path.join(PASTA_MODELOS, nome)
    if not os.path.exists(caminho):
        return ""
    with open(caminho, "rb") as f:
        return f"data:{tipo};base64," + base64.b64encode(f.read()).decode()


def _finais(corpo, vals):
    """Tira do corpo os dois últimos parágrafos para irem junto do quadro de assinaturas (mesma folha)."""
    antes = ""
    if not vals.get("SEM_ASSINATURAS"):
        while corpo and corpo[-1].startswith("<p>") and antes.count("<p>") < 2:
            antes = corpo.pop() + antes
    return antes


def _assinaturas_html(modelo, vals, antes=""):
    """Quadro de assinaturas (com os parágrafos finais na mesma folha); sem o quadro, nada."""
    if vals.get("SEM_ASSINATURAS"):
        return antes
    partes = "".join(
        f'<div class="ass"><div class="linha"></div><b>{html.escape(preencher_texto(nome, vals))}</b>'
        f'<span>{html.escape(papel)}</span></div>' for nome, papel in _partes(modelo))
    testemunhas = '<div class="ass"><div class="linha"></div><span class="esq">Nome:</span><span class="esq">CPF:</span></div>' * 2
    data = f'<p class="data">{html.escape(LOCAL_DATA)}</p>' if _sem_data(modelo) else ""
    if len(_partes(modelo)) == 1 and not modelo.get("testemunhas", True):  # notificações: só a Alfa, ao centro
        return f'<div class="assinaturas" style="--esp:{_espaco_assinatura(modelo)}">{antes}{data}<div class="grade unica">{partes}</div></div>'
    test = (f'<h3>Testemunhas</h3><div class="grade test">{testemunhas}</div>'
            if modelo.get("testemunhas", True) else "")
    return f'<div class="assinaturas" style="--esp:{_espaco_assinatura(modelo)}">{antes}{data}<div class="grade">{partes}</div>{test}</div>'


def gerar_html(modelo, vals):
    """Contrato em HTML pronto para impressão: cabeçalho e rodapé (com rubricas) repetem em todas as páginas."""
    corpo = []
    tem_assinaturas = False
    for bloco in re.split(r"\n\s*\n", modelo["texto"].strip()):
        bloco = _bloco_especial(bloco, vals)
        quadro = _linhas_quadro(bloco)
        if quadro:  # quadro longo (cronograma de parcelas) pode continuar na página seguinte
            classes = "quadro" + (" longo" if len(quadro) > 6 else "") + (" largo" if max(map(len, quadro)) >= 4 else "")
            corpo.append(f'<table class="{classes}">' + "".join(
                "<tr>" + "".join(f'<td class="{"c" if i else ""}">{_inline_html(c, vals)}</td>' for i, c in enumerate(l)) + "</tr>"
                for l in quadro) + "</table>")
            continue
        bloco = " ".join(l.strip() for l in bloco.splitlines()).strip()
        if not bloco:
            continue
        if bloco == "[[ASSINATURAS]]":
            corpo.append(_assinaturas_html(modelo, vals, _finais(corpo, vals)))
            tem_assinaturas = True
        elif bloco.startswith(">> "):
            corpo.append(f'<p class="dir">{_inline_html(bloco[3:].strip(), vals)}</p>')
        elif bloco.startswith("# "):
            corpo.append(f"<h1>{_inline_html('**' + bloco[2:].strip() + '**', vals)}</h1>")
        elif bloco.startswith("## "):
            titulo = bloco[3:].strip()
            if _eh_clausula(titulo):
                corpo.append(f'<h2>{_inline_html("**" + titulo.upper() + "**", vals)}</h2>')
            else:
                corpo.append(f'<h4>{_inline_html("**" + titulo + "**", vals)}</h4>')
        else:
            corpo.append(f"<p>{_inline_html(bloco, vals)}</p>")
    if not tem_assinaturas:  # todo documento termina com o quadro de assinaturas (ou folha em branco, sem o quadro)
        corpo.append(_assinaturas_html(modelo, vals, _finais(corpo, vals)))
    numero = (f'<div class="num">{html.escape(_numero_cabecalho(modelo, vals))}</div>'
              if modelo.get("mostrar_numero", True) else "")
    enderecos = "<br>".join(f"<b>{rot}:</b> {html.escape(txt)}" for rot, txt in ENDERECOS)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{html.escape(modelo['nome'])}</title>
<style>
  @page {{ size: Letter; margin: 0 22mm; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 10.5pt/1.6 Arial, Helvetica, sans-serif; color: #111; }}
  b {{ font-weight: bold; }}
  .topo, .rodape {{ position: fixed; left: 0; right: 0; }}
  .topo {{ top: 0; padding-top: 9mm; }}
  .topo .faixa {{ display: flex; justify-content: space-between; align-items: center; padding-bottom: 3mm;
                 border-bottom: 1.5pt solid #{COR}; }}
  .topo img {{ height: 22mm; }}
  .topo .dir {{ text-align: right; font-size: 8.5pt; line-height: 1.5; color: #333; }}
  .topo .num {{ font-size: 11pt; font-weight: bold; color: #{COR}; margin-bottom: 2mm; letter-spacing: .3pt; }}
  .rodape {{ bottom: 0; padding-bottom: 7mm; }}
  .rubricas {{ height: 22mm; }}  /* espaço em branco para as rubricas das partes */
  .base {{ display: flex; align-items: center; gap: 4mm; border-top: .8pt solid #{COR}; padding-top: 2.5mm; }}
  .base .end {{ flex: 1; font-size: 7.5pt; line-height: 1.45; color: #333; }}
  .base img {{ height: 11mm; }}
  table.pagina {{ width: 100%; border-collapse: collapse; }}
  table.pagina > thead td, table.pagina > tfoot td {{ padding: 0; }}
  .esp-topo {{ height: 44mm; }} .esp-rodape {{ height: 52mm; }}
  h1 {{ font-size: 14pt; text-align: center; margin: 2mm 0 8mm; letter-spacing: .4pt; }}
  h2 {{ font-size: 11pt; color: #{COR}; margin: 7mm 0 3mm; padding-bottom: 1.2mm;
        border-bottom: .6pt solid #{COR}; page-break-after: avoid; }}
  h4 {{ font-size: 11pt; margin: 5mm 0 2mm; page-break-after: avoid; }}
  p {{ margin: 0 0 3.5mm; text-align: justify; orphans: 3; widows: 3; }}
  .falta {{ background: #fde68a; }}
  table.quadro {{ width: 100%; border-collapse: collapse; margin: 2mm 0 5mm; page-break-inside: avoid; font-size: 10pt; }}
  table.quadro td {{ border: .8pt solid #444; padding: 2mm 3mm; }}
  table.quadro td.c {{ width: 23%; text-align: center; }}
  table.quadro.longo {{ page-break-inside: auto; }}
  table.quadro.largo {{ font-size: 9.5pt; }}
  table.quadro.largo td.c {{ width: 13%; }}
  table.quadro tr {{ page-break-inside: avoid; }}
  .assinaturas {{ page-break-inside: avoid; padding-top: 1mm; }}
  .folha-branca {{ page-break-before: always; height: 1px; }}  /* sem o quadro: folha em branco para assinar */
  .assinaturas .data {{ text-align: right; margin: 2mm 0 0; }}
  .assinaturas .grade {{ display: grid; grid-template-columns: 1fr 1fr; column-gap: 16mm; }}
  .assinaturas .grade.unica {{ grid-template-columns: 90mm; justify-content: center; margin-top: 6mm; }}
  p.dir {{ text-align: right; margin-bottom: 8mm; }}
  .assinaturas + p.dir {{ margin-top: 7mm; }}
  table.pagina > tbody > tr > td > :last-child {{ margin-bottom: 0; }}  /* sem margem sobrando: evita folha vazia no fim */
  .assinaturas .ass {{ text-align: center; font-size: 10.5pt; line-height: 1.45; display: flex; flex-direction: column; }}
  .assinaturas .ass .linha {{ height: calc(17mm * var(--esp, 1)); border-bottom: .8pt solid #000; margin-bottom: 2mm; }}
  .assinaturas .test .ass .linha {{ height: calc(15mm * var(--esp, 1)); }}
  .assinaturas .ass .esq {{ text-align: left; margin-top: 1.5mm; }}
  .assinaturas h3 {{ font-size: 10.5pt; color: #{COR}; text-transform: uppercase; letter-spacing: .5pt; margin: 6mm 0 0; }}
</style></head><body>
<div class="topo"><div class="faixa"><img src="{_data_uri('logo.jpg', 'image/jpeg')}" alt="Alfa">
  <div class="dir">{numero}Telefone (61) 4000-0000<br>www.alfacontabil.example</div></div></div>
<div class="rodape"><div class="rubricas"></div>
  <div class="base"><div class="end">{enderecos}</div><img src="{_data_uri('qrcode.png', 'image/png')}" alt="QR Code"></div></div>
<table class="pagina"><thead><tr><td><div class="esp-topo"></div></td></tr></thead>
<tfoot><tr><td><div class="esp-rodape"></div></td></tr></tfoot>
<tbody><tr><td>{''.join(corpo)}</td></tr></tbody></table>
</body></html>"""


def gerar_pdf(modelo, vals):
    import shutil
    import subprocess
    import tempfile
    navegador = next((n for n in NAVEGADORES if os.path.exists(n)), None)
    if not navegador:
        raise ErroModelo("Para gerar PDF é preciso ter o Microsoft Edge ou o Google Chrome instalado neste computador.")
    pasta = tempfile.mkdtemp(prefix="contrato_pdf_")
    try:
        origem = os.path.join(pasta, "contrato.html")
        destino = os.path.join(pasta, "contrato.pdf")
        with open(origem, "w", encoding="utf-8") as f:
            f.write(gerar_html(modelo, vals))
        try:
            subprocess.run([navegador, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
                            "--disable-extensions", f"--user-data-dir={os.path.join(pasta, 'perfil')}",
                            f"--print-to-pdf={destino}", "file:///" + origem.replace("\\", "/")],
                           capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            raise ErroModelo("O navegador demorou demais para gerar o PDF. Tente de novo.")
        if not os.path.exists(destino) or os.path.getsize(destino) < 500:
            raise ErroModelo("Não foi possível gerar o PDF.")
        with open(destino, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def salvar_pdf(modelo, vals, caminho_docx):
    """Salva o PDF ao lado do .docx, com o mesmo nome."""
    destino = os.path.splitext(caminho_docx)[0] + ".pdf"
    with open(destino, "wb") as f:
        f.write(gerar_pdf(modelo, vals))
    return destino


def nome_arquivo(modelo, vals):
    base = preencher_texto(modelo.get("nome_arquivo") or modelo["nome"], vals)
    base = re.sub(r'[\\/:*?"<>|]+', " ", base).replace("________", "SEM NOME")
    return re.sub(r"\s+", " ", base).strip()[:150] + ".docx"


def salvar_docx(modelo, vals, pasta):
    os.makedirs(pasta, exist_ok=True)
    nome = nome_arquivo(modelo, vals)
    destino = os.path.join(pasta, nome)
    base, ext = os.path.splitext(destino)
    n = 2
    while os.path.exists(destino):
        destino = f"{base} ({n}){ext}"
        n += 1
    with open(destino, "wb") as f:
        f.write(gerar_docx(modelo, vals))
    return destino


def novo_id():
    return uuid.uuid4().hex[:10]
