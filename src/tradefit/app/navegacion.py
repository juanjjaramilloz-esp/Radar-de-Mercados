"""Páginas de la app y navegación entre ellas (``st.navigation``).

Streamlit identifica cada página por su ``url_path``, así que se pueden crear en
cada ejecución con el título en el idioma activo y enlazarlas desde cualquier
parte. Los módulos de las páginas se importan dentro de la función porque
``ficha`` importa de ``main`` y ``main`` enlaza a la ficha: así no hay ciclo.
"""

import streamlit as st

from tradefit.app.i18n import t


def pagina(nombre: str) -> st.Page:
    """La página ``"radar"`` o ``"ficha"``, con su título en el idioma activo."""
    from tradefit.app import ficha, main  # noqa: PLC0415 — evita el ciclo main ↔ ficha

    if nombre == "ficha":
        return st.Page(ficha.page, title=t("ficha_nav_ficha"), icon="🧾", url_path="ficha")
    return st.Page(main.main, title=t("ficha_nav_radar"), icon="📡", url_path="radar", default=True)


def ejecutar() -> None:
    """Navegación arriba y ejecuta la página elegida."""
    st.navigation([pagina("radar"), pagina("ficha")], position="top").run()
