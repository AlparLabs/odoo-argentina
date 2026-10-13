"""[AlparData] Fusión de módulos ADHOC 17.0 -> 19.0.

Corre como pre-migración de l10n_ar_ux. l10n_ar_tax depende de l10n_ar_ux y
l10n_ar_account_reports de l10n_ar_tax, así que esto siempre corre antes de
que carguen los módulos destino. Para entonces Odoo ya corrió update_list(),
así que existen en ir_module_module.

Está en 0.0.0 para no depender de los números de versión de ADHOC: corre en
cada cambio de versión de l10n_ar_ux y no hace nada si los módulos viejos ya
no están instalados.

La lógica de fusión replica openupgradelib.update_module_names(merge_modules=True)
en SQL plano para no depender de openupgradelib en el build.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# (módulo en 17, módulo que lo absorbe en 19)
MERGES = [
    ("l10n_ar_account_withholding", "l10n_ar_tax"),
    ("l10n_ar_withholding_ux", "l10n_ar_tax"),
    ("l10n_ar_account_tax_settlement", "l10n_ar_account_reports"),
    ("account_tax_settlement", "l10n_ar_account_reports"),
]

ACTIVE_STATES = ("installed", "to upgrade", "to remove")
DETACHED_PREFIX = "[ALPAR-UPGRADE] "


def _get_module(cr, name):
    cr.execute(
        "SELECT id, state, latest_version FROM ir_module_module WHERE name = %s",
        [name],
    )
    return cr.fetchone()


def _detach_custom_views(cr, modules):
    """Desactiva y desengancha las vistas sin xmlid que heredan de vistas de
    los módulos a fusionar.

    Sin esto, al validar la vista padre en 19 la vista custom rompe el upgrade
    (campos que ya no existen), y si el módulo destino no redefine la vista
    padre, la limpieza final la borra en cascada junto con la custom.
    Quedan inactivas, como vistas primarias, para rehacerlas a mano en 19.
    """
    cr.execute(
        """
        SELECT v.id, v.name, d.module, d.name
          FROM ir_ui_view v
          JOIN ir_model_data d ON d.model = 'ir.ui.view' AND d.res_id = v.inherit_id
         WHERE d.module IN %s
           AND NOT EXISTS (
                SELECT 1 FROM ir_model_data x
                 WHERE x.model = 'ir.ui.view' AND x.res_id = v.id)
        """,
        [tuple(modules)],
    )
    for view_id, view_name, parent_module, parent_xmlid in cr.fetchall():
        _logger.warning(
            "Vista custom %s (id %s) heredaba de %s.%s: queda inactiva y "
            "desenganchada, hay que rehacerla en 19",
            view_name, view_id, parent_module, parent_xmlid,
        )
        cr.execute(
            """
            UPDATE ir_ui_view
               SET active = FALSE,
                   inherit_id = NULL,
                   mode = 'primary',
                   name = %s || name
             WHERE id = %s
            """,
            [DETACHED_PREFIX, view_id],
        )


def _merge_module(cr, old, new):
    old_row = _get_module(cr, old)
    if not old_row or old_row[1] not in ACTIVE_STATES:
        _logger.info("%s no está instalado: nada que fusionar", old)
        return
    new_row = _get_module(cr, new)
    if not new_row:
        raise RuntimeError(
            "No se encontró %s en ir_module_module: falta su código en el "
            "addons_path, no se puede fusionar %s" % (new, old)
        )
    old_id, old_state, old_version = old_row
    new_state = new_row[1]
    _logger.info(
        "Fusionando %s (%s) en %s (%s)", old, old_state, new, new_state
    )

    # Se recrean cuando carga el módulo destino
    cr.execute("DELETE FROM ir_model_constraint WHERE module = %s", [old_id])
    cr.execute("DELETE FROM ir_model_relation WHERE module = %s", [old_id])

    # Las vistas del módulo viejo no se mueven: el destino recrea las que
    # sigue definiendo. Si se movieran, las que ya no define se validarían
    # con campos que no existen al cargar el destino, y si el destino se
    # instala no corre ninguna migración que las limpie.
    cr.execute(
        "SELECT res_id FROM ir_model_data WHERE module = %s AND model = 'ir.ui.view'",
        [old],
    )
    view_ids = [row[0] for row in cr.fetchall()]
    if view_ids:
        env = api.Environment(cr, SUPERUSER_ID, {})
        env["ir.ui.view"].browse(view_ids).exists().with_context(_force_unlink=True).unlink()

    # Mover los xmlids sin pisar los que el destino ya tiene
    cr.execute(
        """
        UPDATE ir_model_data
           SET module = %s
         WHERE module = %s
           AND name NOT IN (SELECT name FROM ir_model_data WHERE module = %s)
        """,
        [new, old, new],
    )
    # Los repetidos se renombran: como el destino no los carga, Odoo los
    # limpia al final del update
    cr.execute(
        """
        UPDATE ir_model_data
           SET name = name || '_alpar_merged_' || id,
               module = %s
         WHERE module = %s
        """,
        [new, old],
    )
    cr.execute(
        "UPDATE ir_module_module_dependency SET name = %s WHERE name = %s",
        [new, old],
    )

    if new_state == "uninstalled":
        # Nadie lo marcó para instalar: lo actualizamos desde la versión
        # del módulo viejo para que corran sus migraciones
        cr.execute(
            """
            UPDATE ir_module_module
               SET state = 'to upgrade', latest_version = %s
             WHERE name = %s
            """,
            [old_version, new],
        )
    # Si estaba 'to install' (lo marcó button_upgrade por ser dependencia
    # nueva) se instala y, como ya es dueño de los xmlids, los actualiza en
    # vez de duplicarlos.

    cr.execute("DELETE FROM ir_module_module WHERE id = %s", [old_id])
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = 'base'
           AND model = 'ir.module.module'
           AND name = %s
        """,
        ["module_" + old],
    )


def migrate(cr, version):
    if not version:
        return
    _detach_custom_views(cr, [old for old, _new in MERGES])
    for old, new in MERGES:
        _merge_module(cr, old, new)
