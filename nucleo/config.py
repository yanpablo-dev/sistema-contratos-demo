"""Configuração do sistema (gravada em dados/config.json)."""
import os

from .util import ler_json, salvar_json

PASTA_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_DADOS = os.path.join(PASTA_APP, "dados")
PASTA_WEB = os.path.join(PASTA_APP, "web")
ARQ_CONFIG = os.path.join(PASTA_DADOS, "config.json")

PADRAO = {
    # Pasta que contém os contratos (na demonstração, a pasta de exemplos criada por gerar_exemplos.py)
    "pasta_raiz": os.path.join(PASTA_APP, "exemplo_contratos"),
    # Nome da pasta (dentro da raiz) que recebe os contratos de empresas que não são mais nossas
    "pasta_encerrados": "Contrato Encerrado",
    "contask_web": "http://127.0.0.1:3000",
    "contask_api": "http://127.0.0.1:8800",
    "contask_email": "",
    # Pasta do Autentique (link do painel ou id) com os contratos assinados
    "autentique_pasta": "",
    # Mostrar do Autentique somente documentos de empresas nossas (status_nossos no Contask)
    "autentique_somente_nossas": True,
    # Status do Contask que significam "a empresa é nossa"
    "status_nossos": ["ATIVA", "SUSPENSA"],
    # CNPJs da própria Alfa (aparecem como CONTRATADA e devem ser ignorados)
    "cnpjs_proprios": ["11444777000161", "11222333000181"],
    # Caminhos relativos à raiz que não entram na análise
    "pastas_ignoradas": [],
    "extensoes_ignoradas": [".db", ".ini", ".dic", ".tmp", ".lnk", ".shs"],
    # Pontuação mínima para aceitar automaticamente uma identificação por nome
    "limite_confianca": 80,
    # Abaixo disto a sugestão é descartada; entre os dois limites vai para "Revisar"
    "limite_revisao": 60,
    "porta": 8765,
    # Subpasta (dentro da pasta dos contratos) onde os contratos gerados pelos modelos são salvos; vazio = a própria pasta
    "pasta_novos_contratos": "",
}


def carregar():
    cfg = dict(PADRAO)
    cfg.update(ler_json(ARQ_CONFIG, {}))
    return cfg


def salvar(alteracoes):
    cfg = carregar()
    for k, v in alteracoes.items():
        if k in PADRAO:
            cfg[k] = v
    salvar_json(ARQ_CONFIG, cfg)
    return cfg


def caminho_dados(nome):
    return os.path.join(PASTA_DADOS, nome)
