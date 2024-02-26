"""
This module contains functions to interact with the main database of the
Alertadengue project.
"""
from sqlalchemy.engine import Engine
from typing import List, Tuple
import json
import logging
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import List, Optional, Tuple

import ibis
import numpy as np
import pandas as pd
from ad_main.settings import APPS_DIR, get_ibis_conn, get_sqla_conn
from django.conf import settings
from django.core.cache import cache
import ibis.expr.datatypes as dt
from sqlalchemy import text
from sqlalchemy.engine.base import Engine

# local
from .episem import episem

logger = logging.getLogger(__name__)

DB_ENGINE = get_sqla_conn()
IBIS_CONN = get_ibis_conn()


CID10 = {"dengue": "A90", "chikungunya": "A92.0", "zika": "A928"}
DISEASES_SHORT = ["dengue", "chik", "zika"]
DISEASES_NAME = CID10.keys()
ALERT_COLOR = {1: "verde", 2: "amarelo", 3: "laranja", 4: "vermelho"}
ALERT_CODE = dict(zip(ALERT_COLOR.values(), ALERT_COLOR.keys()))

ALL_STATE_NAMES = {
    "AC": ["Acre", [-8.77, -70.55], 6],
    "AL": ["Alagoas", [-9.71, -35.73], 6],
    "AM": ["Amazonas", [-3.07, -61.66], 6],
    "AP": ["Amapá", [1.41, -51.77], 6],
    "BA": ["Bahia", [-12.96, -38.51], 6],
    "CE": ["Ceará", [-3.71, -38.54], 6],
    "DF": ["Distrito Federal", [-15.83, -47.86], 6],
    "ES": ["Espírito Santo", [-19.19, -40.34], 6],
    "GO": ["Goiás", [-16.64, -49.31], 6],
    "MA": ["Maranhão", [-2.55, -44.3], 6],
    "MG": ["Minas Gerais", [-18.1, -44.38], 6],
    "MS": ["Mato Grosso do Sul", [-20.51, -54.54], 6],
    "MT": ["Mato Grosso", [-12.64, -55.42], 6],
    "PA": ["Pará", [-5.53, -52.29], 6],
    "PB": ["Paraíba", [-7.06, -35.55], 6],
    "PE": ["Pernambuco", [-8.28, -35.07], 6],
    "PI": ["Piauí", [-8.28, -43.68], 6],
    "PR": ["Paraná", [-24.89, -51.55], 6],
    "RJ": ["Rio de Janeiro", [-22.84, -43.15], 6],
    "RN": ["Rio Grande do Norte", [-5.22, -36.52], 6],
    "RO": ["Rondônia", [-11.22, -62.8], 6],
    "RR": ["Roraima", [1.89, -61.22], 6],
    "RS": ["Rio Grande do Sul", [-30.01, -51.22], 6],
    "SC": ["Santa Catarina", [-27.33, -49.44], 6],
    "SE": ["Sergipe", [-10.9, -37.07], 6],
    "SP": ["São Paulo", [-23.55, -46.64], 6],
    "TO": ["Tocantins", [-10.25, -48.25], 6],
}

STATE_NAME = {k: v[0] for k, v in ALL_STATE_NAMES.items()}
STATE_INITIAL = dict(zip(STATE_NAME.values(), STATE_NAME.keys()))
MAP_CENTER = {k: v[1] for k, v in ALL_STATE_NAMES.items()}
MAP_ZOOM = {k: v[2] for k, v in ALL_STATE_NAMES.items()}

with open(APPS_DIR / "data" / "municipalities.json", "r") as muns:
    _mun_decoded = muns.read().encode().decode("utf-8-sig")
    MUNICIPALITIES = json.loads(_mun_decoded)

# Ibis utils


def data_hist_uf(state_abbv: str, disease: str = "dengue") -> pd.DataFrame:
    """
    PostgreSQLTable[table]
    name: hist_uf_disease_materialized_view
    schema:
        state_abbv : string
        municipio_geocodigo : int32
        SE : int32
        data_iniSE : date
        casos_est : float32
        casos : int32
        nivel : int16
        receptivo : int16
    Parameters:
    ----------
        uf, disease
    Returns
    -------
        Dataframe
    """

    cache_name = "data_hist" + "_" + str(state_abbv) + "_" + str(disease)

    res = cache.get(cache_name)

    if res is None:
        _disease = get_disease_suffix(disease, empty_for_dengue=False)
        table_hist_uf = IBIS_CONN.table(f"hist_uf{_disease}_materialized_view")

        res = (
            table_hist_uf[table_hist_uf.state_abbv == state_abbv]
            .order_by("SE")
        )

        res = res.mutate(
            data_iniSE=res.data_iniSE.cast(dt.timestamp)
        ).execute()

        cache.set(
            cache_name,
            res,
            settings.QUERY_CACHE_TIMEOUT,
        )

    return res


class RegionalParameters:
    DB = settings.PSQL_DB

    t_parameters = IBIS_CONN.table("parameters", DB, "Dengue_global")
    t_municipio = IBIS_CONN.table("Municipio", DB, "Dengue_global")
    t_estado = IBIS_CONN.table("estado", DB, "Dengue_global")
    t_regional = IBIS_CONN.table("regional", DB, "Dengue_global")

    @classmethod
    def get_regional_names(cls, state_name: str) -> list:
        """
        Parameters
        ----------
            dict_keys with state names
        Returns
        -------
            list(iterable)
        """
        cache_name = (
            "regional_names_to" + "_" + str(state_name).replace(" ", "_")
        )
        res = cache.get(cache_name)

        if res is None:
            # print(f"add cache_name {cache_name}: ", res)

            municipio_uf_filter = cls.t_municipio[
                cls.t_municipio.uf == state_name
            ]
            t_joined = cls.t_regional.join(
                municipio_uf_filter, cls.t_parameters
            )[cls.t_regional.nome].distinct()
            df_regional_names = t_joined.execute()

            res = df_regional_names["nome"].to_list()

            cache.set(
                cache_name,
                res,
                settings.QUERY_CACHE_TIMEOUT,
            )

        return res

    @classmethod
    def get_var_climate_info(cls, geocodes: list) -> Tuple[str]:
        """
        Parameters
        ----------
            list dict_keys
        Returns
        ----------
            Tuples pairs
        """

        geocode_filter = cls.t_parameters.municipio_geocodigo.isin(geocodes)
        t_parameters_expr = cls.t_parameters[geocode_filter].distinct()
        climate_proj = t_parameters_expr.projection(
            ["codigo_estacao_wu", "varcli"]
        ).execute()
        var_climate_info = climate_proj.to_records(index=False).tolist()[0]

        return var_climate_info

    @classmethod
    def get_cities(
        cls,
        regional_name: Optional[str] = None,
        state_name: Optional[str] = None,
    ) -> dict:
        """
        Get a list of cities from available states with code and name pairs
        Returns
        ----------
        """
        cities_by_region = {}

        if regional_name is not None and state_name is not None:
            cache_name = (
                str(regional_name).replace(" ", "_")
                + "_"
                + str(state_name).replace(" ", "_")
            )
            # print('cache_name: ', cache_name)
            res = cache.get(cache_name)

            if res:
                # print(f'cache_name {cache_name} found: ', res)
                return res

            else:
                # print(f'Add new cache_name: {cache_name}')
                municipio_proj = cls.t_municipio[
                    "geocodigo", "nome", "uf", "id_regional"
                ]
                municipio_uf_filter = municipio_proj[
                    municipio_proj.uf == state_name
                ].order_by("id_regional")

                regional_proj = cls.t_regional["id", "nome"]
                regional_name_filter = regional_proj[
                    regional_proj.nome == regional_name
                ].order_by("id")

                cities_expr = (
                    municipio_uf_filter.join(
                        regional_name_filter, cls.t_parameters
                    )[municipio_uf_filter.geocodigo, municipio_uf_filter.nome]
                    .order_by("nome")
                    .execute()
                )

                for row in cities_expr.to_dict(orient="records"):
                    cities_by_region[row["geocodigo"]] = row["nome"]

                res = cities_by_region

                cache.set(
                    cache_name,
                    res,
                    settings.QUERY_CACHE_TIMEOUT,
                )

                return res

        else:
            cache_name = (
                "all_cities_from" + "_" + str(state_name).replace(" ", "_")
            )
            res = cache.get(cache_name)
            if res:
                # print(f'Fetch {cache_name}', res)
                return res
            else:
                # print(f'Add cache_name {cache_name}')
                if state_name is None:
                    state_names = [f"{state_name}"]

                else:
                    state_names = [f"{state_name}"]

                t_municipio_uf_expr = cls.t_municipio.uf.isin(state_names)

                cities_expr = (
                    cls.t_municipio[t_municipio_uf_expr]["geocodigo", "nome"]
                    .order_by("nome")
                    .execute()
                )

                for row in cities_expr.to_dict(orient="records"):
                    cities_by_region[row["geocodigo"]] = row["nome"]

                res = cities_by_region

                cache.set(
                    cache_name,
                    res,
                    settings.QUERY_CACHE_TIMEOUT,
                )

                return res

    @classmethod
    def get_station_data(cls, geocode: int, disease: str) -> pd:
        """
        Parameters
        ----------
        geocode : int
        disease : str, {'dengue', 'chik', 'zika'}
        Returns
        ----------
        dataframe: pandas
            climate data by gocode and disease
        """

        climate_keys = [
            "cid10",
            "municipio_geocodigo",
            "codigo_estacao_wu",
            "varcli",
            "clicrit",
            "varcli2",
            "clicrit2",
            "limiar_preseason",
            "limiar_posseason",
            "limiar_epidemico",
        ]

        station_filter = (cls.t_parameters["cid10"] == CID10.get(disease)) & (
            cls.t_parameters["municipio_geocodigo"] == geocode
        )
        climate_expr = (
            cls.t_parameters[climate_keys].filter(station_filter).execute()
        )

        return tuple(climate_expr.values)


# General util functions
def _nan_to_num_int_list(v):
    """
    :param v: numpy.array
    :return: list
    """
    try:
        return np.nan_to_num(v.fillna(0)).astype(int).tolist()
    except Exception:
        return np.nan_to_num(v).astype(int).tolist()


def _episem(dt):
    return episem(dt, sep="")


def normalize_str(string: str) -> str:
    """
    São Tomé -> sao tome
    """
    non_ascii = (
        unicodedata.normalize("NFKD", string)
        .encode("ascii", "ignore")
        .decode()
    )
    string = non_ascii.lower()
    return string


def get_disease_suffix(disease: str, empty_for_dengue: bool = True):
    """
    :param disease:
    :return:
    """
    return (
        ("" if empty_for_dengue else "_dengue")
        if disease == "dengue"
        else "_chik"
        if disease == "chikungunya"
        else "_zika"
        if disease == "zika"
        else ""
    )


# TODO: check if this works and is necessary

'''
def get_city_name_by_id(geocode: int, db_engine: Engine) -> str:
    """
    Get the name of a city by its geocode.

    Parameters
    ----------
    geocode : int
        The geocode of the city.
    db_engine : Engine
        The database engine to use for the query.

    Returns
    -------
    str
        The name of the city.
    """

    with db_engine.connect() as conn:
        res = conn.execute(
            f"""
            SELECT nome
            FROM "Dengue_global"."Municipio"
            WHERE geocodigo={geocode};
        """
        )
        return res.fetchone()[0]

'''


'''
def get_all_active_cities_state(
    db_engine: Engine,
) -> List[Tuple[str, str, str, str]]:
    """
    Fetches a list of names of active cities from the database.

    Parameters
    ----------
    db_engine : Engine
        The database engine instance to execute the query.

    Returns
    -------
    List[Tuple[str, str, str, str]]
        A list of tuples containing municipality geocode, start date, city name, and state.
    """
    # Check if the result is cached
    res = cache.get("get_all_active_cities_state")

    if res is None:
        # If not cached, fetch the data from the database
        with db_engine.connect() as conn:
            res = conn.execute(
                """
                SELECT DISTINCT
                hist.municipio_geocodigo,
                hist."data_iniSE",
                city.nome,
                city.uf
                FROM "Municipio"."Historico_alerta" AS hist
                INNER JOIN "Dengue_global"."Municipio" AS city
                    ON (hist.municipio_geocodigo=city.geocodigo)
                WHERE hist."data_iniSE" >= (
                    SELECT MAX(hist."data_iniSE") - interval '52 weeks'
                    FROM "Municipio"."Historico_alerta" AS hist
                    )
                ORDER BY hist."data_iniSE";
                """
            )
            res = res.fetchall()
            # Cache the result with a timeout
            cache.set(
                "get_all_active_cities_state",
                res,
                settings.QUERY_CACHE_TIMEOUT,
            )
    return res

'''


def get_last_alert(geo_id, disease, db_engine: Engine = DB_ENGINE):
    """
    Get the last alert level for a specific municipality and disease.

    Parameters
    ----------
    geo_id : str
        The geocode of the municipality.
    disease : str
        The name of the disease.
    db_engine : sqlalchemy.engine.Engine, optional
        The database engine, defaults to DB_ENGINE.

    Returns
    -------
    pandas.DataFrame
        The last alert level for the specified municipality and disease.
    """

    table_name = "Historico_alerta" + get_disease_suffix(disease)

    sql = f"""
    SELECT nivel
    FROM "Municipio"."{table_name}"
    WHERE municipio_geocodigo={geo_id}
    ORDER BY "data_iniSE" DESC
    LIMIT 1
    """

    with db_engine.connect() as conn:
        data = conn.execute(sql).fetchall()
        return pd.DataFrame(data)


def load_series(
    cidade,
    disease: str = "dengue",
    epiweek: int = 0,
    db_engine: Engine = DB_ENGINE,
):
    """
    Loads the alert series for visualization on the website.

    Parameters
    ----------
    cidade : int
        The city code for which to retrieve the alert series.
    disease : str, optional
        The disease code (CID10) for which to retrieve the alert series. Defaults to "dengue".
    epiweek: int, optional
        The epidemiological week for which to retrieve the alert series. Defaults to 0.
    db_engine : Engine, optional
        The database engine to use for the query. Defaults to DB_ENGINE.

    Returns
    -------
    dictionary
        The alert series data.
    """

    cache_key = "load_series-{}-{}".format(cidade, disease)
    result = cache.get(cache_key)

    if result is None:
        ap = str(cidade)

        if epiweek is not None:
            dados_alerta = Forecast.load_cases(
                geocode=cidade, disease=disease, epiweek=epiweek
            )
        else:
            dados_alerta = load_cases_without_forecast(
                geocode=cidade, disease=disease
            )

        if len(dados_alerta) == 0:
            return {ap: None}

        series = defaultdict(lambda: defaultdict(lambda: []))

        series[ap]["dia"] = dados_alerta.data_iniSE.tolist()

        series[ap]["casos_est_min"] = _nan_to_num_int_list(
            dados_alerta.casos_est_min
        )

        series[ap]["casos_est"] = _nan_to_num_int_list(dados_alerta.casos_est)

        series[ap]["casos_est_max"] = _nan_to_num_int_list(
            dados_alerta.casos_est_max
        )

        series[ap]["casos"] = _nan_to_num_int_list(dados_alerta.casos)
        # (1,4)->(0,3)
        series[ap]["alerta"] = (
            dados_alerta.nivel.fillna(1).astype(int) - 1
        ).tolist()
        series[ap]["SE"] = (dados_alerta.SE.astype(int)).tolist()
        series[ap]["prt1"] = dados_alerta.p_rt1.astype(float).tolist()

        k_forecast = [
            k for k in dados_alerta.keys() if k.startswith("forecast_")
        ]

        if k_forecast:
            for k in k_forecast:
                series[ap][k] = dados_alerta[k].astype(float).tolist()

        series[ap] = dict(series[ap])

        result = dict(series)
        cache.set(cache_key, result, settings.QUERY_CACHE_TIMEOUT)

    return result


def load_cases_without_forecast(
    geocode: int, disease, db_engine: Engine = DB_ENGINE
):
    """
    Parameters
    ----------
    geocode : int
        The geocode for which to retrieve forecast dates.
    disease : str
        The disease code (CID10) for which to retrieve forecast dates.
    db_engine : Engine
        The database engine to use for the query.
    """

    with db_engine.connect() as conn:
        table_name = "Historico_alerta" + get_disease_suffix(disease)

        result = conn.execute(
            f"""
            SELECT * FROM "Municipio"."{table_name}"
            WHERE municipio_geocodigo={geocode} ORDER BY "data_iniSE" ASC
            """
        )

        data_alert = pd.DataFrame(result.fetchall(), columns=result.keys())

        # Convert relevant columns to datetime
        data_alert["data_iniSE"] = pd.to_datetime(data_alert["data_iniSE"])
        # Add more columns if needed

    return data_alert


def get_city_alert(cidade, disease="dengue"):
    """
    Retorna vários indicadores de alerta a nível da cidade.
    :param cidade: geocódigo
    :param doenca: dengue|chikungunya|zika
    :return: tuple -> alert, SE, case_series, last_year,
        obs_case_series, min_max_est, dia, prt1
    """
    series = load_series(cidade, disease)
    series_city = series[str(cidade)]

    if series_city is None:
        return ([], None, [0], 0, [0], [0, 0], datetime.now(), 0)

    alert = series_city["alerta"][-1]
    SE = series_city["SE"][-1]
    case_series = series_city["casos_est"]
    last_year = (
        series_city["casos"][-52] if len(series_city["casos"]) >= 52 else None
    )

    obs_case_series = series_city["casos"]
    min_max_est = (
        series_city["casos_est_min"][-1],
        series_city["casos_est_max"][-1],
    )
    dia = series_city["dia"][-1]
    prt1 = np.mean(series_city["prt1"][-3:])

    return (
        alert,
        SE,
        case_series,
        last_year,
        obs_case_series,
        min_max_est,
        dia,
        prt1,
    )


def calculate_digit(dig):
    """
    Calcula o digito verificador do geocódigo de município
    :param dig: geocódigo com 6 dígitos
    :return: dígito verificador
    """
    peso = [1, 2, 1, 2, 1, 2, 0]
    soma = 0
    dig = str(dig)

    for i in range(6):
        valor = int(dig[i]) * peso[i]
        soma += sum([int(d) for d in str(valor)]) if valor > 9 else valor

    dv = 0 if soma % 10 == 0 else (10 - (soma % 10))
    return dv


@np.vectorize
def add_dv(geocodigo):
    """
    Retorna o geocóodigo do município adicionando o digito verificador,
    se necessário.
    :param geocodigo: geocóodigo com 6 ou 7 dígitos
    """
    if len(str(geocodigo)) == 7:
        return geocodigo
    elif len(str(geocodigo)) == 6:
        return int(str(geocodigo) + str(calculate_digit(geocodigo)))
    else:
        raise ValueError("geocode does not match!")


def get_epiyears(
    state_name: str,
    disease: Optional[str] = None,
    db_engine: Engine = DB_ENGINE,
) -> List[Tuple]:
    """
    Retrieve epidemiological years data from the database.

    Parameters:
    state_name (str): Name of the state.
    disease (Optional[str]): Disease name, defaults to None.
    db_engine (Engine): Database engine, defaults to DB_ENGINE.

    Returns:
    List[Tuple]: List of tuples containing the retrieved data.
    """
    parameters = {"state_name": state_name}
    disease_filter = ""

    if disease:
        disease_code = CID10.get(disease, "")
        parameters["disease_code"] = disease_code
        disease_filter = " AND disease_code = :disease_code"

    sql_text_query = """
    SELECT ano_notif, se_notif, casos
    FROM public.epiyear_summary_materialized_view
    WHERE uf = :state_name{disease_filter}
    ORDER BY ano_notif, se_notif
    """.format(
        disease_filter=disease_filter
    )

    with db_engine.connect() as conn:
        result = conn.execute(text(sql_text_query), parameters)
        data = [tuple(row) for row in result.fetchall()]
    return data


class NotificationResume:
    @staticmethod
    def count_cities_by_uf(
        uf: str, disease: str = "dengue", db_engine: Engine = DB_ENGINE
    ) -> int:
        """
        Return the total number of cities measured for a given state and disease.
        """
        view_name = f"public.city_count_by_uf_{disease}_materialized_view"

        sql_text = text(
            f"""
            SELECT city_count
            FROM {view_name}
            WHERE uf = :uf
        """
        )

        try:
            with db_engine.connect() as conn:
                result = conn.execute(sql_text, {"uf": uf}).fetchone()
                return int(result[0]) if result else 0
        except Exception as e:
            print(
                f"Error executing count_cities_by_uf for {disease} in {uf}: {e}"
            )
            return 0


class Forecast:
    @staticmethod
    def get_min_max_date(
        geocode: int, cid10: str, db_engine: Engine = DB_ENGINE
    ) -> tuple[str, str]:
        """
        Retrieves the minimum and maximum date from the forecasts
        for a given geocode and disease code (CID10).

        Parameters
        ----------
        geocode : int
            The geocode for which to retrieve forecast dates.
        cid10 : str
            The disease code (CID10) for which to retrieve forecast dates.
        db_engine : Engine
            The database engine to use for the query.

        Returns
        -------
        tuple[str, str]
            A tuple containing the minimum and maximum forecast dates as strings in 'YYYY-MM-DD' format.
        """
        sql = f"""
        SELECT
            TO_CHAR(MIN(init_date_epiweek), 'YYYY-MM-DD') AS epiweek_min,
            TO_CHAR(MAX(init_date_epiweek), 'YYYY-MM-DD') AS epiweek_max
        FROM
            forecast.forecast_cases AS f
            INNER JOIN forecast.forecast_city AS fc
            ON (f.geocode = fc.geocode AND fc.active=TRUE)
            INNER JOIN forecast.forecast_model AS fm
            ON (fc.forecast_model_id = fm.id AND fm.active = TRUE)
        WHERE f.geocode={geocode} AND cid10='{cid10}'
        """

        with db_engine.connect() as connection:
            result = connection.execute(sql)
            values = result.fetchone()

        return values[0], values[1]

    @staticmethod
    def load_cases(
        geocode: int, disease: str, epiweek: int, db_engine: Engine = DB_ENGINE
    ):
        """
        :param geocode:
        :param disease:
        :param epiweek:
        :return:
        """

        # sql settings
        cid10 = CID10[disease]

        sql = """
        SELECT DISTINCT ON (forecast_cases.forecast_model_id)
        forecast_cases.forecast_model_id,
        forecast_model.name AS forecast_model_name,
        forecast_cases.published_date
        FROM
        forecast.forecast_cases
        INNER JOIN forecast.forecast_model
            ON (
            forecast_cases.forecast_model_id =
            forecast_model.id
            )
        WHERE
        cid10 = %s
        AND geocode = %s
        AND epiweek = %s
        ORDER BY forecast_model_id, published_date DESC
        """

        with db_engine.connect() as conn:
            result = conn.execute(sql, (cid10, geocode, epiweek))
            df_forecast_model = pd.DataFrame(
                result.fetchall(), columns=result.keys()
            )

        # return df_forecast_model

        table_name = "Historico_alerta" + get_disease_suffix(disease)

        sql_alert = """
        SELECT * FROM "Municipio"."{}"
        WHERE municipio_geocodigo={} ORDER BY "data_iniSE" ASC
        """.format(
            table_name, geocode
        )

        sql = """
        SELECT
            (CASE
             WHEN tb_cases."data_iniSE" IS NOT Null
               THEN tb_cases."data_iniSE"
             %(forecast_date_ini_epiweek)s
             ELSE Null
             END
            ) AS "data_iniSE",
            tb_cases.casos_est_min,
            tb_cases.casos_est,
            tb_cases.casos_est_max,
            tb_cases.casos,
            tb_cases.nivel,
            (CASE
             WHEN tb_cases."SE" IS NOT Null THEN tb_cases."SE"
             %(forecast_epiweek)s
             ELSE Null
             END
            ) AS "SE",
            tb_cases.p_rt1
            %(forecast_models_cases)s
        FROM
            (%(sql_alert)s) AS tb_cases %(forecast_models_joins)s
        ORDER BY "data_iniSE" ASC
        """

        sql_forecast_by_model = """
        FULL OUTER JOIN (
          SELECT
            epiweek,
            init_date_epiweek,
            cases AS forecast_%(model_name)s_cases
          FROM
            forecast.forecast_cases
            INNER JOIN forecast.forecast_model
              ON (
                forecast_cases.forecast_model_id = forecast_model.id
                AND forecast_model.active=TRUE
              )
            INNER JOIN forecast.forecast_city
              ON (
                forecast_city.geocode = forecast_cases.geocode
                AND forecast_cases.forecast_model_id =
                  forecast_city.forecast_model_id
                AND forecast_city.active=TRUE
              )
          WHERE
            cid10='%(cid10)s'
            AND forecast_cases.geocode=%(geocode)s
            AND published_date='%(published_date)s'
            AND forecast_cases.forecast_model_id=%(model_id)s
        ) AS forecast%(model_id)s ON (
          tb_cases."SE" = forecast%(model_id)s.epiweek
        )
        """

        forecast_date_ini_epiweek = ""
        forecast_models_cases = ""
        forecast_models_joins = ""
        forecast_epiweek = ""
        forecast_config = {
            "geocode": geocode,
            "cid10": cid10,
            "published_date": None,
            "model_name": None,
            "model_id": None,
        }

        for i, row in df_forecast_model.iterrows():
            forecast_config.update(
                {
                    "published_date": row.published_date,
                    "model_name": row.forecast_model_name,
                    "model_id": row.forecast_model_id,
                }
            )
            # forecast models join sql
            forecast_models_joins += sql_forecast_by_model % forecast_config

            # forecast date ini selection
            forecast_date_ini_epiweek += (
                """
            WHEN forecast%(model_id)s.init_date_epiweek IS NOT Null
               THEN forecast%(model_id)s.init_date_epiweek
            """
                % forecast_config
            )

            # forecast epiweek selection
            forecast_epiweek += (
                """
            WHEN forecast%(model_id)s.epiweek IS NOT Null
               THEN forecast%(model_id)s.epiweek
            """
                % forecast_config
            )

            # forecast models cases selection
            forecast_models_cases += (
                ",forecast_%(model_name)s_cases" % forecast_config
            )

        if forecast_models_cases == "":
            forecast_models_cases = ",1"

        sql = sql % {
            "forecast_models_joins": forecast_models_joins,
            "forecast_models_cases": forecast_models_cases,
            "forecast_date_ini_epiweek": forecast_date_ini_epiweek,
            "forecast_epiweek": forecast_epiweek,
            "sql_alert": sql_alert,
        }

        with db_engine.connect() as conn:
            result = conn.execute(sql)
            return pd.DataFrame(result.fetchall(), columns=result.keys())


class ReportCity:
    @classmethod
    def read_disease_data(
        cls,
        disease: str,
        geocode: int,
        year_week: int,
    ) -> ibis.expr.types.Expr:
        """
        Return an ibis expression with the history for a given disease.
        Parameters
        ----------
        disease : str, {'dengue', 'chik', 'zika'}
        geocode : int
        year_week : int
            The starting Year/Week, e.g.: 202002
        Returns
        -------
        ibis.expr.types.Expr
        """

        if disease not in CID10.keys():
            raise Exception(
                f"The diseases available are: {[k for k in CID10.keys()]}"
            )

        table_suffix = ""
        if disease != "dengue":
            table_suffix = get_disease_suffix(disease)  # F'_{disease}'

        t_hist = IBIS_CONN.table(
            f"Historico_alerta{table_suffix}", settings.PSQL_DB, "Municipio"
        )

        # 200 = 2 years
        ew_end = year_week
        ew_start = ew_end - 200

        t_hist_filter_bol = (t_hist.SE.between(ew_start, ew_end)) & (
            t_hist["municipio_geocodigo"] == geocode
        )

        t_hist_proj = t_hist.filter(t_hist_filter_bol).limit(200)

        nivel = (
            ibis.case()
            .when((t_hist_proj.nivel.cast("string") == "1"), "verde")
            .when((t_hist_proj.nivel.cast("string") == "2"), "amarelo")
            .when((t_hist_proj.nivel.cast("string") == "3"), "laranja")
            .when((t_hist_proj.nivel.cast("string") == "4"), "vermelho")
            .else_("-")
            .end()
        ).name("nivel")

        hist_keys = [
            t_hist_proj.SE.name("SE"),
            t_hist_proj.casos.name("casos notif."),
            t_hist_proj.casos_est.name("casos_est"),
            t_hist_proj.p_inc100k.name("incidência"),
            t_hist_proj.p_rt1.name("pr(incid. subir)"),
            t_hist_proj.tempmin.name("temp.min"),
            t_hist_proj.tempmed.name("temp.med"),
            t_hist_proj.tempmax.name("temp.max"),
            t_hist_proj.umidmin.name("umid.min"),
            t_hist_proj.umidmed.name("umid.med"),
            t_hist_proj.umidmax.name("umid.max"),
            nivel,
            t_hist_proj.nivel.name("level_code"),
        ]

        return (
            t_hist_proj[hist_keys]
            # .order_by(("SE", True))
            .execute().set_index("SE")
        )


class ReportState:
    """Report State class."""

    @classmethod
    def csv_get_regional_by_state(self, state: str) -> pd:
        """
        Import CSV file with the municipalities of regional health by state.
        Parameters
        ----------
            state: State abbreviation.
        Returns:
            df: df with the municipalities of the regionals filtered by state.
        """
        # TODO: Export CSV to JSON file: see #

        cache_name = "regional_by_state_" + "_" + str(state)
        res = cache.get(cache_name)

        if res is None:
            df_reg = pd.read_csv(
                settings.APPS_DIR / "data" / "regionais_saude_name.csv",
                names=[
                    "UF",
                    "municipio_nome",
                    "municipio_geocodigo",
                    "id_regional",
                    "nome_regional",
                ],
                skiprows=1,
            )

            df_reg.municipio_geocodigo = add_dv(df_reg.municipio_geocodigo)

            df = df_reg[df_reg.UF.eq(state)]

            res = df.loc[
                :,
                [
                    "id_regional",
                    "nome_regional",
                    "municipio_geocodigo",
                    "municipio_nome",
                ],
            ]

            cache.set(
                cache_name,
                res,
                settings.QUERY_CACHE_TIMEOUT,
            )

        return res

    @classmethod
    def create_report_state_data(cls, geocodes, disease, year_week):
        if disease not in CID10.keys():
            raise Exception(
                f"The diseases available are: {[k for k in CID10.keys()]}"
            )

        table_suffix = ""
        if disease != "dengue":
            table_suffix = get_disease_suffix(disease)  # F'_{disease}'

        t_hist = IBIS_CONN.table(
            f"Historico_alerta{table_suffix}", settings.PSQL_DB, "Municipio"
        )

        #  200 = 2 years
        ew_start = year_week - 20

        t_hist_filter_bol = (t_hist["SE"].between(ew_start, year_week)) & (
            t_hist["municipio_geocodigo"].isin(geocodes)
        )

        t_hist_proj = t_hist.filter(t_hist_filter_bol).limit(100)

        cols_ = [
            "SE",
            "casos_est",
            "casos",
            "nivel",
            "municipio_geocodigo",
            "municipio_nome",
        ]

        return (
            t_hist_proj[cols_]
            .order_by(("SE", False))
            .execute()
            # .set_index("SE")
        )
