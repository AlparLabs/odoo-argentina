"""[AlparData] Borra las vistas del módulo que ya no existen en su código.

Al migrar salteando versiones (ej. 17 -> 19) quedan en la base vistas que el
módulo ya no define. Odoo las borra recién al final del update, pero antes,
al cargar las vistas nuevas, valida la vista padre combinada con esas vistas
viejas y falla si usan campos que ya no existen.

Este archivo es genérico: el módulo se deduce de la ruta. Está en 0.0.0, así
que corre en cada cambio de versión; si no hay vistas obsoletas no hace nada.
Las vistas custom (sin xmlid) que heredan de las obsoletas quedan inactivas y
desenganchadas para rehacerlas a mano, en vez de borrarse en cascada.
"""
import ast
import logging
from pathlib import Path
from xml.etree import ElementTree

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MODULE_DIR = Path(__file__).resolve().parents[2]
MODULE = MODULE_DIR.name
DETACHED_PREFIX = "[ALPAR-UPGRADE] "


def _views_in_code():
    manifest = ast.literal_eval((MODULE_DIR / "__manifest__.py").read_text(encoding="utf-8"))
    names = set()
    for data_file in manifest.get("data", []):
        if not data_file.endswith(".xml"):
            continue
        root = ElementTree.parse(MODULE_DIR / data_file).getroot()
        for node in root.iter():
            is_view = (node.tag == "record" and node.get("model") == "ir.ui.view") or node.tag == "template"
            xmlid = node.get("id") if is_view else None
            if not xmlid:
                continue
            module, _sep, name = xmlid.rpartition(".")
            if module in ("", MODULE):
                names.add(name)
    return names


def _detach_custom_descendants(cr, view_ids):
    cr.execute(
        """
        WITH RECURSIVE descendants(id) AS (
            SELECT id FROM ir_ui_view WHERE inherit_id IN %s
            UNION
            SELECT v.id FROM ir_ui_view v JOIN descendants d ON v.inherit_id = d.id
        )
        SELECT v.id, v.name
          FROM ir_ui_view v
          JOIN descendants d ON d.id = v.id
         WHERE NOT EXISTS (
                SELECT 1 FROM ir_model_data x
                 WHERE x.model = 'ir.ui.view' AND x.res_id = v.id)
        """,
        [view_ids],
    )
    for view_id, view_name in cr.fetchall():
        _logger.warning(
            "%s: vista custom %s (id %s) heredaba de una vista obsoleta: queda "
            "inactiva y desenganchada, hay que rehacerla",
            MODULE, view_name, view_id,
        )
        cr.execute(
            """
            UPDATE ir_ui_view
               SET active = FALSE, inherit_id = NULL, mode = 'primary', name = %s || name
             WHERE id = %s
            """,
            [DETACHED_PREFIX, view_id],
        )


def migrate(cr, version):
    if not version:
        return
    in_code = _views_in_code()
    cr.execute(
        "SELECT name, res_id FROM ir_model_data WHERE module = %s AND model = 'ir.ui.view'",
        [MODULE],
    )
    obsolete = {name: res_id for name, res_id in cr.fetchall() if name not in in_code}
    if not obsolete:
        return
    _logger.info("%s: borrando vistas que ya no están en el código: %s", MODULE, sorted(obsolete))
    view_ids = tuple(obsolete.values())
    _detach_custom_descendants(cr, view_ids)
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["ir.ui.view"].browse(view_ids).exists().with_context(_force_unlink=True).unlink()
