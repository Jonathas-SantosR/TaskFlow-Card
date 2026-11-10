import unittest
from unittest.mock import Mock, patch

from backend.app import executar_servidor


class TestesEncerramento(unittest.TestCase):
    def test_libera_porta_apos_ctrl_c_ou_retorno_normal(self):
        for interrupcao in (None, KeyboardInterrupt()):
            with self.subTest(interrupcao=type(interrupcao).__name__):
                servidor = Mock()
                servidor.serve_forever.side_effect = interrupcao
                with (
                    patch("backend.app.criar_aplicacao"),
                    patch("werkzeug.serving.make_server", return_value=servidor),
                    patch("builtins.print"),
                ):
                    executar_servidor()
                servidor.server_close.assert_called_once_with()
                servidor.shutdown.assert_not_called()
