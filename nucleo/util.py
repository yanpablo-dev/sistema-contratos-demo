"""Funções utilitárias compartilhadas: normalização de texto, datas e JSON."""
import json
import os
import re
import threading
import unicodedata
from datetime import date, datetime

_trava_json = threading.RLock()


def sem_acento(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c))


def normalizar(texto):
    """Maiúsculas, sem acento, só letras/números separados por um espaço."""
    t = sem_acento(texto).upper().replace("&", " E ")
    t = re.sub(r"[^A-Z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def so_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def cnpj_valido(cnpj):
    c = so_digitos(cnpj)
    if len(c) != 14 or c == c[0] * 14:
        return False

    def dv(base, pesos):
        s = sum(int(d) * p for d, p in zip(base, pesos))
        r = s % 11
        return "0" if r < 2 else str(11 - r)

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    return c[12] == dv(c[:12], p1) and c[13] == dv(c[:13], p2)


def formatar_cnpj(cnpj):
    c = so_digitos(cnpj)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    if len(c) == 11:
        return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
    return c


def ts_iso(ts):
    try:
        return datetime.fromtimestamp(ts).isoformat(timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return None


def data_iso(valor):
    """Converte dd/mm/aaaa, aaaa-mm-dd[...] ou datetime em 'aaaa-mm-dd'."""
    if valor in (None, "", "None"):
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    s = str(valor).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            return None
    return None


def ler_json(caminho, padrao):
    with _trava_json:
        try:
            with open(caminho, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return padrao
        except (OSError, ValueError):
            return padrao


def salvar_json(caminho, dados):
    with _trava_json:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        tmp = caminho + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=1)
        os.replace(tmp, caminho)


def chave_arquivo(nome, tamanho, mtime):
    """Identidade estável de um arquivo, que sobrevive a uma movimentação de pasta."""
    return f"{nome.lower()}|{tamanho}|{int(mtime)}"
