"""Печатает заголовки колонок выгрузки — чтобы сверить их с шапкой Google-таблицы.

Запуск: python -m tools.print_headers
"""

from services.exporters import headers


def main() -> None:
    """Печатает список колонок в том же порядке, в котором их получит выгрузка."""
    for index, header in enumerate(headers(), start=1):
        print(f"{index}. {header}")


if __name__ == "__main__":
    main()
