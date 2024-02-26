from typing import Optional

import ibis
import ibis.expr.datatypes as dt
import pandas as pd

# local
from ad_main.settings import PSQL_DB, get_ibis_conn, get_sqla_conn
from dados.dbdata import CID10, STATE_NAME, get_disease_suffix  # noqa:F401

DB_ENGINE = get_sqla_conn()
IBIS_CONN = get_ibis_conn()


class AlertCity:
    @staticmethod
    def search(
        disease: str,
        geocode: int,
        ew_start: Optional[int] = None,
        ew_end: Optional[int] = None,
    ) -> ibis.expr:
        """
        Return an ibis expression with the history for a given disease.
        Parameters
        ----------
        disease : str, {'dengue', 'chikungunya', 'zika'}
        geocode : int
        ew_start : Optional[int]
            The starting Year/Week, e.g.: 202202
        ew_end : Optional[int]
            The ending Year/Week, e.g.: 202205
        Returns
        -------
        ibis.expr.types.Expr
        """

        if disease not in CID10.keys():
            raise Exception(
                f"The diseases available are: {list(CID10.keys())}"
            )

        table_suffix = ""
        if disease != "dengue" and disease != "zika":
            table_suffix = get_disease_suffix(disease)

        # schema_city = IBIS_CONN.schema("Municipio")
        # t_hist = schema_city.table(f"Historico_alerta{table_suffix}")
        t_hist = IBIS_CONN.table(
            f"Historico_alerta{table_suffix}", PSQL_DB, "Municipio"
        )

        if ew_start and ew_end:
            t_hist_filter_bol = (
                t_hist["SE"].between(int(ew_start), int(ew_end))
            ) & (t_hist["municipio_geocodigo"] == geocode)

            t_hist_filter_expr = t_hist.filter(t_hist_filter_bol).order_by(
                ibis.desc("SE")
            )

        else:
            t_hist_filter_expr = (
                t_hist.filter(t_hist["municipio_geocodigo"] == geocode)
                .order_by(ibis.desc("SE"))
                .limit(3)
            )

        t_hist_accum_expr = t_hist_filter_expr.mutate(
            notif_accum_year=t_hist_filter_expr.casos.sum()
        )

        t_hist_accum_expr = t_hist_accum_expr.mutate(
            data_iniSE=t_hist_accum_expr.data_iniSE.cast(dt.timestamp)
        )

        # print(ibis.impala.compile(t_hist_accum_expr))

        return t_hist_accum_expr
