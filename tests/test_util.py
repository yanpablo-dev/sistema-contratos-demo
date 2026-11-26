"""Testes das funções utilitárias (texto, CNPJ, datas e JSON)."""
import os
import tempfile
import unittest
from datetime import date, datetime

from nucleo import util


class TestTexto(unittest.TestCase):
    def test_sem_acento(self):
        self.assertEqual(util.sem_acento("Prestação de Serviços"), "Prestacao de Servicos")
        self.assertEqual(util.sem_acento(None), "")

    def test_normalizar(self):
        self.assertEqual(util.normalizar("  Pão & Cia. Ltda - ME "), "PAO E CIA LTDA ME")

    def test_so_digitos(self):
        self.assertEqual(util.so_digitos("11.444.777/0001-61"), "11444777000161")
        self.assertEqual(util.so_digitos(None), "")


class TestCnpj(unittest.TestCase):
    def test_cnpj_valido(self):
        self.assertTrue(util.cnpj_valido("11.444.777/0001-61"))
        self.assertTrue(util.cnpj_valido("11222333000181"))

    def test_cnpj_invalido(self):
        self.assertFalse(util.cnpj_valido("11.444.777/0001-62"))  # dígito errado
        self.assertFalse(util.cnpj_valido("11111111111111"))  # todos iguais
        self.assertFalse(util.cnpj_valido("123"))  # tamanho errado
        self.assertFalse(util.cnpj_valido(""))

    def test_formatar_cnpj_e_cpf(self):
        self.assertEqual(util.formatar_cnpj("11444777000161"), "11.444.777/0001-61")
        self.assertEqual(util.formatar_cnpj("12345678909"), "123.456.789-09")
        self.assertEqual(util.formatar_cnpj("123"), "123")


class TestDatas(unittest.TestCase):
    def test_data_iso(self):
        self.assertEqual(util.data_iso("26/11/2026"), "2026-11-26")
        self.assertEqual(util.data_iso("5/1/2026"), "2026-01-05")
        self.assertEqual(util.data_iso("2026-11-26T10:00:00"), "2026-11-26")
        self.assertEqual(util.data_iso(date(2026, 11, 26)), "2026-11-26")
        self.assertEqual(util.data_iso(datetime(2026, 11, 26, 15, 30)), "2026-11-26")

    def test_data_iso_invalida(self):
        self.assertIsNone(util.data_iso("31/02/2026"))
        self.assertIsNone(util.data_iso("ontem"))
        self.assertIsNone(util.data_iso(None))
        self.assertIsNone(util.data_iso(""))


class TestJson(unittest.TestCase):
    def test_salvar_e_ler(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "sub", "dados.json")
            util.salvar_json(caminho, {"empresa": "Alfa Contabilidade", "valor": 1500})
            self.assertEqual(util.ler_json(caminho, None), {"empresa": "Alfa Contabilidade", "valor": 1500})
            self.assertFalse(os.path.exists(caminho + ".tmp"))

    def test_ler_inexistente_ou_corrompido(self):
        with tempfile.TemporaryDirectory() as pasta:
            self.assertEqual(util.ler_json(os.path.join(pasta, "nao_existe.json"), []), [])
            ruim = os.path.join(pasta, "ruim.json")
            with open(ruim, "w", encoding="utf-8") as f:
                f.write("{ isto não é json")
            self.assertEqual(util.ler_json(ruim, {}), {})

    def test_chave_arquivo(self):
        self.assertEqual(util.chave_arquivo("Contrato.DOCX", 1024, 1700000000.9), "contrato.docx|1024|1700000000")


if __name__ == "__main__":
    unittest.main()
