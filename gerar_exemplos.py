"""Cria dados de demonstração: empresas fictícias e documentos gerados pelo próprio sistema.

Rode uma vez antes de abrir o sistema:  python gerar_exemplos.py
Apaga e recria somente os dados de exemplo (dados/*.json e a pasta exemplo_contratos).
Todas as empresas, pessoas e CNPJs são fictícios (os CNPJs têm dígitos verificadores inválidos de propósito).
"""
import os
import shutil
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nucleo import config, modelos  # noqa: E402
from nucleo.util import formatar_cnpj, ler_json, salvar_json  # noqa: E402
import servidor  # noqa: E402

USUARIO = "demonstracao"
HOJE = date.today()

# nome, CNPJ (fictício), status, regime, classificação, representante, endereço
EMPRESAS = [
    ("PADARIA PAO DOURADO LTDA", "10100100000100", "ATIVA", "Simples", "ICMS", "MARIA EXEMPLO SOUZA", "Rua das Flores, 10, Centro, Brasília/DF"),
    ("TECH HORIZONTE SISTEMAS LTDA", "10200200000100", "ATIVA", "Presumido", "ISS", "CARLOS EXEMPLO LIMA", "Av. Central, 250, Sala 12, Brasília/DF"),
    ("CLINICA BEM VIVER LTDA", "10300300000100", "ATIVA", "Presumido", "ISS", "ANA EXEMPLO COSTA", "Quadra 5, Lote 3, Taguatinga/DF"),
    ("MERCADO BOM PRECO LTDA", "10400400000100", "ATIVA", "Simples", "ICMS/ISS", "JOSE EXEMPLO ALVES", "Rua do Comércio, 88, Ceilândia/DF"),
    ("CONSTRUTORA PEDRA FIRME LTDA", "10500500000100", "SUSPENSA", "Real", "ICMS/ISS", "PAULO EXEMPLO ROCHA", "Av. das Obras, 1200, Guará/DF"),
    ("AUTO PECAS VELOZ LTDA", "10600600000100", "ATIVA", "Simples", "ICMS", "LUCAS EXEMPLO MOURA", "Rua dos Motores, 45, Samambaia/DF"),
    ("RESTAURANTE SABOR DA TERRA LTDA", "10700700000100", "ATIVA", "Simples", "ICMS", "JULIANA EXEMPLO DIAS", "Quadra 2, Loja 7, Sobradinho/DF"),
    ("STUDIO CRIATIVO DESIGN LTDA", "10800800000100", "ATIVA", "Simples", "ISS", "BRUNO EXEMPLO TEIXEIRA", "Rua da Arte, 300, Brasília/DF"),
    ("FARMACIA SAUDE TOTAL LTDA", "10900900000100", "ATIVA", "Presumido", "ICMS", "FERNANDA EXEMPLO RIBEIRO", "Av. da Saúde, 77, Gama/DF"),
    ("TRANSPORTADORA ROTA CERTA LTDA", "11001000000100", "DISTRATO", "Real", "ICMS/ISS", "RICARDO EXEMPLO NUNES", "Rodovia Exemplo, Km 5, Brasília/DF"),
    ("ESCOLA APRENDER MAIS LTDA", "11101100000100", "ATIVA", "Isenta", "Outros", "PATRICIA EXEMPLO GOMES", "Rua do Saber, 15, Planaltina/DF"),
    ("PET SHOP AMIGO FIEL LTDA", "11201200000100", "BAIXADA", "Simples", "ICMS/ISS", "MARCOS EXEMPLO PINTO", "Rua dos Bichos, 9, Brasília/DF"),
]


def dados(i):
    nome, cnpj, _, _, _, rep, end = EMPRESAS[i]
    return {"RAZAO_SOCIAL": nome, "CNPJ": cnpj, "REPRESENTANTE": rep, "ENDERECO": end,
            "CPF": f"000.000.{i:03d}-00", "RG": f"0.000.{i:03d}", "AOS_CUIDADOS": rep}


def iso(dias_atras):
    return (HOJE - timedelta(days=dias_atras)).isoformat()


# (dias atrás, modelo, empresa, valores extras): conta uma história para cada cliente
DOCUMENTOS = [
    (120, "contabil", 0, {"NUMERO_CONTRATO": "001/2026", "VALOR": "850,00", "DATA_INICIO": iso(120)}),
    (110, "contabil", 1, {"NUMERO_CONTRATO": "002/2026", "VALOR": "1.900,00", "DATA_INICIO": iso(110)}),
    (100, "locacao", 7, {"VALOR": "150,00", "DATA_INICIO": iso(100)}),
    (95, "contabil", 2, {"NUMERO_CONTRATO": "003/2026", "VALOR": "2.400,00", "DATA_INICIO": iso(95)}),
    (60, "aditivo", 0, {"NUMERO_CONTRATO": "001/2026", "VALOR": "980,00", "DATA_INICIO": iso(30), "QTD_FUNCIONARIOS": "04"}),
    (40, "prop_simples", 6, {"NUMERO_PROPOSTA": "014 / 2026", "VALOR": "690,00"}),
    (35, "prop_auditoria", 8, {"NUMERO_PROPOSTA": "015 / 2026", "PERIODO_AUDITORIA": "exercício de 2025"}),
    # cobrança: um cliente em cada etapa
    (2, "cobranca", 3, {"VENCIMENTOS": "10/09/2026 e 10/10/2026", "VALOR_DEBITO": "1.700,00"}),
    (12, "cobranca", 5, {"VENCIMENTOS": "10/09/2026", "VALOR_DEBITO": "780,00"}),
    (30, "cobranca", 4, {"VENCIMENTOS": "10/07/2026 a 10/09/2026", "VALOR_DEBITO": "5.400,00"}),
    (20, "suspensao", 4, {"VENCIMENTOS": "10/07/2026 a 10/09/2026", "VALOR_DEBITO": "5.400,00"}),
    (25, "cobranca", 9, {"VENCIMENTOS": "10/06/2026 a 10/09/2026", "VALOR_DEBITO": "6.634,97"}),
    (15, "suspensao", 9, {"VENCIMENTOS": "10/06/2026 a 10/09/2026", "VALOR_DEBITO": "6.634,97"}),
    (8, "notificacao", 9, {"VALOR_DEBITO": "6.634,97"}),
    (45, "cobranca", 1, {"VENCIMENTOS": "10/07/2026 e 10/08/2026", "VALOR_DEBITO": "3.800,00"}),
    (38, "acordo", 1, {"VALOR_DEBITO": "3.800,00", "DATA_ATUALIZACAO": iso(38), "VALOR_ENTRADA": "800,00",
                       "DATA_ENTRADA": iso(38), "QTD_PARCELAS": "6", "DATA_PRIMEIRA_PARCELA": iso(8)}),
    (10, "rescisao", 9, {"DATA_ENCERRAMENTO": (HOJE + timedelta(days=20)).isoformat()}),
]


def main():
    cfg = config.carregar()
    raiz = cfg["pasta_raiz"]
    if os.path.abspath(raiz) != os.path.abspath(os.path.join(config.PASTA_APP, "exemplo_contratos")):
        sys.exit(f"A pasta de contratos configurada não é a de exemplos ({raiz}). Nada foi alterado.")
    shutil.rmtree(raiz, ignore_errors=True)
    os.makedirs(raiz)
    for nome in ("contratos_gerados.json", "contratantes.json", "movimentacoes.json", "ultima_analise.json"):
        caminho = config.caminho_dados(nome)
        if os.path.exists(caminho):
            os.remove(caminho)

    salvar_json(config.caminho_dados("empresas.json"), {
        "atualizado_em": datetime.now().isoformat(timespec="seconds"), "fonte": "Dados de demonstração",
        "empresas": [{"id": str(i + 1), "num": str(100 + i), "nome": n, "fantasia": n.replace(" LTDA", "").title(),
                      "cnpj": c, "cnpj_fmt": formatar_cnpj(c), "status": s, "arquivada": False,
                      "inicio_contrato": None, "data_status": None, "regime": r, "classificacao": cl, "uf": "DF",
                      "filial": "", "grupo": "", "resp_fiscal": "Equipe Fiscal", "resp_dp": "Equipe DP",
                      "resp_contabil": "Equipe Contábil"} for i, (n, c, s, r, cl, _, _) in enumerate(EMPRESAS)]})

    datas = []
    for dias, id_, i, extra in sorted(DOCUMENTOS, key=lambda d: -d[0]):  # do mais antigo ao mais novo
        valores = dict(dados(i), DATA_ASSINATURA=iso(dias), **extra)
        r = servidor._gerar_contrato(id_, valores, cfg, USUARIO, empresa_id=str(i + 1), com_pdf=True)
        datas.append(datetime.combine(HOJE - timedelta(days=dias), datetime.now().time()).isoformat(timespec="seconds"))
        print(f"  {id_:<15} {EMPRESAS[i][0]:<34} {r['arquivo']}")

    hist = ler_json(modelos.ARQ_HISTORICO, [])  # datas espalhadas no tempo, para as etapas e prazos aparecerem
    for reg, d in zip(hist, datas):
        reg["data"] = d
    salvar_json(modelos.ARQ_HISTORICO, hist)
    print(f"\n{len(EMPRESAS)} empresas e {len(hist)} documentos de exemplo criados em {raiz}")


if __name__ == "__main__":
    main()
