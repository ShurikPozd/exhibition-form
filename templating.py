"""Jinja2-окружение для шаблонов (общее для формы и админки)."""

from fastapi.templating import Jinja2Templates

import settings

templates = Jinja2Templates(directory=settings.TEMPLATES_DIR)
