"""
tests/test_web_scrapper.py — Автотесты модуля веб-поиска ArgosScrapper.
Сетевые запросы мокируются — тесты не зависят от внешних ресурсов.
Запуск: python -m pytest tests/test_web_scrapper.py -v
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.skills.web_scrapper.skill import ArgosScrapper


def _make_response(html: str, status: int = 200) -> MagicMock:
    """Создаёт мок HTTP-ответа с заданным HTML и статусом."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.text = html
    return mock_resp


class TestArgosScrapper(unittest.TestCase):

    def setUp(self):
        self.scrapper = ArgosScrapper()

    # ── URL-кодирование ────────────────────────────────────────────────────

    def test_query_url_encoded(self):
        """Запрос с пробелами и спецсимволами должен быть корректно закодирован."""
        html = '<a class="result__snippet">ответ</a>'
        with patch('requests.get', return_value=_make_response(html)) as mock_get:
            self.scrapper.quick_search('python программирование')
            called_url = mock_get.call_args[0][0]
            self.assertIn('python+%D0%BF%D1%80%D0%BE%D0%B3%D1%80%D0%B0%D0%BC%D0%BC%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5', called_url)
            self.assertNotIn(' ', called_url)

    # ── Успешный парсинг по старому классу ────────────────────────────────

    def test_returns_snippets_old_class(self):
        """Сниппеты с классом result__snippet на теге <a> должны парситься."""
        html = '''
        <html><body>
          <a class="result__snippet">Первый результат поиска.</a>
          <a class="result__snippet">Второй результат поиска.</a>
          <a class="result__snippet">Третий результат поиска.</a>
          <a class="result__snippet">Четвёртый результат (не должен попасть).</a>
        </body></html>
        '''
        with patch('requests.get', return_value=_make_response(html)):
            result = self.scrapper.quick_search('тест')
        self.assertIn('Данные из глобальной сети:', result)
        self.assertIn('Первый результат', result)
        self.assertIn('Второй результат', result)
        self.assertIn('Третий результат', result)
        self.assertNotIn('Четвёртый результат', result)

    # ── Резервный селектор ────────────────────────────────────────────────

    def test_fallback_to_div_result_body(self):
        """При отсутствии <a class=result__snippet> берётся div.result__body."""
        html = '''
        <html><body>
          <div class="result__body">Резервный сниппет один.</div>
          <div class="result__body">Резервный сниппет два.</div>
        </body></html>
        '''
        with patch('requests.get', return_value=_make_response(html)):
            result = self.scrapper.quick_search('резерв')
        self.assertIn('Данные из глобальной сети:', result)
        self.assertIn('Резервный сниппет', result)

    # ── Нет результатов ───────────────────────────────────────────────────

    def test_no_snippets_returns_not_found(self):
        """Если совпадений нет — возвращается сообщение об отсутствии результатов."""
        html = '<html><body><p>Пусто</p></body></html>'
        with patch('requests.get', return_value=_make_response(html)):
            result = self.scrapper.quick_search('xyz_нет_результатов')
        self.assertIn('не дал результатов', result)

    # ── HTTP-ошибка ───────────────────────────────────────────────────────

    def test_http_error_returns_error_message(self):
        """При статусе != 200 возвращается сообщение об ошибке доступа."""
        with patch('requests.get', return_value=_make_response('', status=503)):
            result = self.scrapper.quick_search('тест')
        self.assertIn('Ошибка доступа', result)

    # ── Сетевое исключение ────────────────────────────────────────────────

    def test_network_exception_returns_failure_message(self):
        """При сетевом исключении возвращается сообщение о сбое."""
        with patch('requests.get', side_effect=ConnectionError('timeout')):
            result = self.scrapper.quick_search('тест')
        self.assertIn('Сбой сетевого сканирования', result)

    # ── Форматирование с разделителем ─────────────────────────────────────

    def test_results_joined_with_pipe(self):
        """Несколько результатов должны разделяться символом ' | '."""
        html = '''
        <html><body>
          <a class="result__snippet">А</a>
          <a class="result__snippet">Б</a>
          <a class="result__snippet">В</a>
        </body></html>
        '''
        with patch('requests.get', return_value=_make_response(html)):
            result = self.scrapper.quick_search('тест')
        self.assertIn('А | Б | В', result)


if __name__ == '__main__':
    unittest.main()
