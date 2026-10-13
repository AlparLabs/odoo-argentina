"""[AlparData] Reactiva las vistas del módulo que la plataforma de upgrade desactivó.

La plataforma de upgrade de Odoo desactiva las vistas de módulos que no
conoce. Al cargar el XML, Odoo actualiza el arch pero no las reactiva, y las
vistas de otros módulos que heredan de ellas fallan (ej. l10n_ar_tax
buscando el label payment_total de account_payment_pro).

Corre como post-migración: el arch ya es el del código actual y todavía no
cargaron los módulos que dependen de este. Solo reactiva vistas que el código
no declara inactivas.

Este archivo es genérico: el módulo se deduce de la ruta. Está en 0.0.0, así
que corre en cada cambio de versión; si no hay nada que reactivar no hace nada.
"""
import ast
import logging
from pathlib import Path
from xml.etree import ElementTree

_logger = logging.getLogger(__name__)

MODULE_DIR = Path(__file__).resolve().parents[2]
MODULE = MODULE_DIR.name


def _declared_inactive(node):
    if node.tag == "template":
        return node.get("active", "").strip().lower() in ("false", "0")
    active = node.find("field[@name='active']")
    if active is None:
        return False
    value = (active.get("eval") or active.text or "").strip().lower()
    return value in ("false", "0")


def _active_views_in_code():
    manifest = ast.literal_eval((MODULE_DIR / "__manifest__.py").read_text(encoding="utf-8"))
    names = set()
    for data_file in manifest.get("data", []):
        if not data_file.endswith(".xml"):
            continue
        root = ElementTree.parse(MODULE_DIR / data_file).getroot()
        for node in root.iter():
            is_view = (node.tag == "record" and node.get("model") == "ir.ui.view") or node.tag == "template"
            xmlid = node.get("id") if is_view else None
            if not xmlid or _declared_inactive(node):
                continue
            module, _sep, name = xmlid.rpartition(".")
            if module in ("", MODULE):
                names.add(name)
    return names


def migrate(cr, version):
    if not version:
        return
    names = _active_views_in_code()
    if not names:
        return
    cr.execute(
        """
        UPDATE ir_ui_view v
           SET active = TRUE
          FROM ir_model_data d
         WHERE d.model = 'ir.ui.view'
           AND d.res_id = v.id
           AND d.module = %s
           AND d.name IN %s
           AND NOT v.active
        RETURNING d.name
        """,
        [MODULE, tuple(names)],
    )
    reactivated = sorted(row[0] for row in cr.fetchall())
    if reactivated:
        _logger.info("%s: reactivando vistas desactivadas en el upgrade: %s", MODULE, reactivated)
