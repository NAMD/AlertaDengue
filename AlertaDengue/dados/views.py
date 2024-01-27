import datetime
import json
import locale
import os
import random
from collections import OrderedDict, defaultdict
from copy import deepcopy
from datetime import timedelta
from pathlib import Path, PurePath

import fiona
import numpy as np

#
from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.staticfiles.finders import find
from django.core.cache import cache
from django.http import Http404, HttpResponse

# from django.shortcuts import redirect
from django.templatetags.static import static
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_page
from django.views.generic.base import TemplateView, View

# local
from gis.geotiff import convert_from_shapefile

from . import models as M
from .charts.alerts import AlertCitiesCharts
from .charts.cities import ReportCityCharts
from .charts.home import (
    _create_indicator_chart,
    _create_scatter_chart,
    _create_stack_chart,
)
from .charts.states import ReportStateCharts
from .dbdata import (
    ALERT_COLOR,
    CID10,
    DISEASES_NAME,
    MAP_CENTER,
    MAP_ZOOM,
    STATE_INITIAL,
    STATE_NAME,
    Forecast,
    NotificationResume,
    RegionalParameters,
    ReportCity,
    ReportState,
    data_hist_uf,
    get_city_alert,
    get_last_alert,
)
from .episem import episem, episem2date
from .maps import get_city_info
from .models import City


def get_static(static_dir):
    if not settings.DEBUG:
        return Path(static(static_dir))
    _app_dir = settings.APPS_DIR
    path_to_find = PurePath(find(static_dir))
    return str(path_to_find.relative_to(_app_dir))


DBF = apps.get_model("dbf", "DBF")

locale.setlocale(locale.LC_TIME, locale="pt_BR.UTF-8")


def _get_disease_label(disease_code: str) -> str:
    return (
        "Dengue"
        if disease_code == "dengue"
        else "Chikungunya"
        if disease_code == "chikungunya"
        else "Zika"
        if disease_code == "zika"
        else None
    )


def hex_to_rgb(value):
    value = value.lstrip("#")
    lv = len(value)
    return tuple(
        int(value[i : i + lv // 3], 16)
        for i in range(0, lv, lv // 3)  # noqa: E203
    )


def get_last_color_alert(geocode, disease, color_type="rgb"):
    """
    :param geocode:
    :param disease:
    :param color_type: rba|hex
    :return:
    """
    df_level = get_last_alert(geocode, disease)

    level = (
        0
        if df_level.empty
        else 0
        if not (1 <= df_level.nivel[0] <= 4)
        else df_level.nivel[0]
    )

    color_list = [
        "#cccccc",  # gray
        "#00ff00",  # green
        "#ffff00",  # yellow
        "#ff9900",  # orange
        "#ff0000",  # red
    ]

    if color_type == "hex":
        return color_list[level]

    return hex_to_rgb(color_list[level])


class _GetMethod:
    """"""

    def _get(self, param, default=None):
        """
        :param param:
        :param default:
        :return:
        """
        result = (
            self.request.GET[param] if param in self.request.GET else default
        )

        return result if result else default


class AboutPageView(TemplateView):
    template_name = "about.html"

    def get_context_data(self, **kwargs):
        context = super(AboutPageView, self).get_context_data(**kwargs)
        return context


def download_technical_report_pdf(request, *args, **kwargs):
    pdf_path = os.path.join(
        settings.MEDIA_ROOT, "templates/about/technical-report.pdf"
    )

    if not os.path.exists(pdf_path):
        raise Http404("Technical Report PDF not found")

    pdf_output = (
        "RELATÓRIO TÉCNICO 02_23 clima e arboviroses - projeções para "
        "2024-26out2023.pdf"
    )

    with open(pdf_path, "rb") as pdf_file:
        response = HttpResponse(
            pdf_file.read(), content_type="application/pdf"
        )
        response[
            "Content-Disposition"
        ] = f'attachment; filename="{pdf_output}"'
        return response


class TeamPageView(TemplateView):
    template_name = "team.html"

    def get_context_data(self, **kwargs):
        context = super(TeamPageView, self).get_context_data(**kwargs)
        return context


class JoininPageView(TemplateView):
    template_name = "joinin.html"

    def get_context_data(self, **kwargs):
        context = super(JoininPageView, self).get_context_data(**kwargs)
        return context


class DataPublicServicesPageView(TemplateView):
    template_name = "services.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        service = kwargs.get("service", None)
        service_type = (
            None if "service_type" not in kwargs else kwargs["service_type"]
        )

        if service == "maps":
            if service_type is None:

                geo_info_path = get_static("geojson/geo_info.json")

                with open(geo_info_path) as f:
                    geo_info_json = json.load(f)

                    context.update(
                        {
                            "geocodes": sorted(list(geo_info_json.keys())),
                            "mapserver_url": settings.MAPSERVER_URL,
                            "geo_info": geo_info_json,
                        }
                    )
                self.template_name = "services_maps.html"
            else:
                self.template_name = "services_maps_doc.html"
        elif service == "tutorial":
            if service_type is None:
                self.template_name = "services_tutorial.html"
            elif service_type == "R":
                self.template_name = "services_tutorial_R.html"
            else:
                self.template_name = "services_tutorial_Python.html"
        elif service == "api":
            if service_type is None:
                self.template_name = "services_api.html"

                options_cities = ""
                for state_abbv, state_name in STATE_NAME.items():
                    for (geocode, city_name,) in RegionalParameters.get_cities(
                        state_name=state_name
                    ).items():
                        options_cities += """
                        <option value="{0!s}">
                            {0!s} - {1!s} - {2!s}
                        </option>""".format(
                            geocode, city_name.upper(), state_abbv
                        )

                dt_end = datetime.datetime.now()
                dt_start = dt_end - datetime.timedelta(weeks=4)

                yw_start = episem(dt_start, sep="")
                yw_end = episem(dt_end, sep="")

                dt_start_fmt = episem2date(yw_start, 1).strftime("%Y-%m-%d")
                dt_end_fmt = episem2date(yw_end, 1).strftime("%Y-%m-%d")

                context.update(
                    {
                        "options_cities": options_cities,
                        "date_query_start": dt_start_fmt,
                        "date_query_end": dt_end_fmt,
                    }
                )

                return context
            elif service_type == "tutorialR":
                self.template_name = "services_api_tutorialR.html"
            else:
                self.template_name = "services_api_doc.html"
        else:
            self.template_name = "services.html"

        return context


class AlertaMainView(TemplateView):
    template_name = "main.html"

    def get_context_data(self, **kwargs):
        context = super(AlertaMainView, self).get_context_data(**kwargs)

        return context


class AlertCityPageBaseView(TemplateView, _GetMethod):
    pass


class AlertaMunicipioPageView(AlertCityPageBaseView):
    template_name = "alerta_municipio.html"

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return cache_page(60 * 60 * 8)(view)  # Cache the view for 15 minutes

    def dispatch(self, request, *args, **kwargs):
        super().get_context_data(**kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        chart_alerts = AlertCitiesCharts()

        disease_code = context["disease"]
        disease_label = _get_disease_label(disease_code)
        geocode = context["geocodigo"]

        # Fetch city info from cache or database
        city_info = cache.get(f"city_info:{geocode}")
        if city_info is None:
            city_info = get_city_info(geocode)
            cache.set(
                f"city_info:{geocode}", city_info, 60 * 60 * 24
            )  # Cache for 24 hours

        # Fetch forecast epiweek reference
        forecast_date_min, forecast_date_max = Forecast.get_min_max_date(
            geocode=geocode, cid10=CID10[disease_code]
        )
        forecast_date_ref = self._get("ref", forecast_date_max)

        if forecast_date_ref is None:
            epiweek = None
        else:
            epiweek = episem(forecast_date_ref).replace("W", "")

        (
            alert,
            SE,
            case_series,
            last_year,
            observed_cases,
            min_max_est,
            dia,
            prt1,
        ) = get_city_alert(geocode, disease_code)

        if alert is not None:
            casos_ap = {geocode: int(case_series[-1])}
            bairros = {geocode: city_info["nome"]}
            total_series = case_series[-12:]
            total_observed_series = observed_cases[-12:]
        else:
            casos_ap = {}
            bairros = {}
            total_series = [0]
            total_observed_series = [0]

        try:
            city_chart = chart_alerts.create_alert_chart(
                geocode,
                city_info["nome"],
                disease_label,
                disease_code,
                epiweek,
            )
        except ValueError:
            context = {
                "message": _(
                    "A doença {} não está registrada "
                    "em nosso banco de dados para o município de {}."
                ).format(disease_label, city_info["nome"])
            }
            self.template_name = "error.html"
            return context

        context.update(
            {
                "geocodigo": geocode,  # legacy
                "geocode": geocode,
                "state": city_info["uf"],
                "state_abv": STATE_INITIAL[city_info["uf"]],
                "nome": city_info["nome"],
                "populacao": city_info["populacao"],
                "incidencia": (case_series[-1] / city_info["populacao"])
                * 100000,  # casos/100000
                "casos_por_ap": json.dumps(casos_ap),
                "alerta": {geocode: alert},
                "prt1": prt1 * 100,
                "novos_casos": case_series[-1],
                "bairros": bairros,
                "min_est": min_max_est[0],
                "max_est": min_max_est[1],
                "series_casos": {geocode: case_series[-12:]},
                "SE": SE,
                "WEEK": str(SE)[4:],
                "data1": dia.strftime("%d de %B de %Y"),
                "data2": dia + timedelta(6),
                "last_year": last_year,
                "look_back": len(total_series),
                "total_series": ", ".join(map(str, total_series)),
                "total_observed": total_observed_series[-1],
                "total_observed_series": ", ".join(
                    map(str, total_observed_series)
                ),
                "disease_label": disease_label,
                "disease_code": disease_code,
                "forecast_date_ref": forecast_date_ref,
                "forecast_date_min": forecast_date_min,
                "forecast_date_max": forecast_date_max,
                "epiweek": epiweek,
                "geojson_url": f"/static/geojson/{geocode}.json",
                "chart_alert": city_chart,
            }
        )
        return context


class SinanCasesView(View):
    def get(self, request, year, sample):
        sample = int(sample)
        try:
            assert int(year) in [2010, 2011, 2012, 2013]
        except AssertionError:
            messages.error(
                self.request,
                "O projeto conté dados apenas dos anos 2010 a 2013.",
            )

        sample = 1 if sample == 0 else sample / 100.0
        cases = '{"type":"FeatureCollection", "features":['
        if int(year) == 2010:
            dados = M.Dengue_2010.objects.geojson()
        elif int(year) == 2011:
            dados = M.Dengue_2011.objects.geojson()
        elif int(year) == 2012:
            dados = M.Dengue_2012.objects.geojson()
        elif int(year) == 2013:
            dados = M.Dengue_2013.objects.geojson()
        else:
            dados = []

        if len(dados) < 5500:
            sample = 1
        for c in random.sample(list(dados), int(len(dados) * sample)):
            cases += (
                '{"type":"Feature","geometry":'
                + c.geojson
                + ', "properties":{"data":"'
                + c.dt_notific.isoformat()
                + '"}},'
            )
        cases = cases[:-1] + "]}"
        # json.loads(cases)
        return HttpResponse(cases, content_type="application/json")


class AlertaStateView(TemplateView):
    template_name = "state_cities.html"
    _state_name = STATE_NAME

    def get_context_data(self, **kwargs):
        """
        :param kwargs:
        :return:
        """
        context = super(AlertaStateView, self).get_context_data(**kwargs)

        state_name = self._state_name[context["state"]]
        disease = context["disease"]

        cities_alert = NotificationResume.get_cities_alert_by_state(
            state_name, disease
        )

        alerts = dict(
            cities_alert[["municipio_geocodigo", "level_alert"]].values
        )
        mun_dict = dict(cities_alert[["municipio_geocodigo", "nome"]].values)
        mun_dict_ordered = OrderedDict(
            sorted(mun_dict.items(), key=lambda v: v[1])
        )
        geo_ids = list(mun_dict.keys())

        dbf = (
            DBF.objects.filter(abbreviation=context["state"])
            .order_by("export_date")
            .last()
        )

        if dbf is None:
            last_update = _("desconhecida")
        else:
            last_update = dbf.export_date

        if len(geo_ids) > 0:
            cases_series_last_12 = NotificationResume.tail_estimated_cases(
                geo_ids, 12
            )
        else:
            cases_series_last_12 = {}

        context.update(
            {
                "state_abv": context["state"],
                "state": state_name,
                "map_center": MAP_CENTER[context["state"]],
                "map_zoom": MAP_ZOOM[context["state"]],
                "mun_dict": mun_dict,
                "mun_dict_ordered": mun_dict_ordered,
                "geo_ids": geo_ids,
                "alerts_level": alerts,
                "case_series": cases_series_last_12,
                "disease_label": context["disease"].title(),
                "last_update": last_update,
            }
        )

        return context


class ChartsMainView(TemplateView):
    template_name = "components/home/charts.html"

    def get_img_map(self, state_abbv: str, disease: str) -> str:
        """
        Verify if file exists and return a string to path.
        Parameters
        ----------
        state_abbv: str
            State full name
        disease: str
            option: dengue|chikungunya|zika
        Returns
        -------
        image_path: str
        """

        img_name = Path(
            "img",
            "incidence_maps",
            "state",
            f"incidence_{state_abbv}_{disease}.png",
        )

        img_data = f"""
            <div class='mt-4'>
                <img
                src='{get_static(img_name)}'
                alt=''
                title='Mapa de {disease} para o estado de {state_abbv}'
                style='width:100%'
                />
            </div>"""

        return img_data

    def get_context_data(self, **kwargs):
        context = super(ChartsMainView, self).get_context_data(**kwargs)

        create_scatter_chart = defaultdict(dict)
        create_indicator_chart = defaultdict(dict)
        create_stack_chart = defaultdict(dict)
        count_cities = defaultdict(dict)
        create_maps = defaultdict(dict)
        last_se = defaultdict(dict)
        empty_charts_count = defaultdict(dict)
        states_alert = defaultdict(dict)
        notif_resume = NotificationResume

        state_abbv = context["state"]
        state_name = STATE_NAME.get(state_abbv)
        states_alert[state_abbv] = state_abbv

        # Use as an argument to fetch in database
        for disease in tuple(DISEASES_NAME):
            no_data_chart = f"""
                <div class='alert alert-primary' align='center'>
                    Não há dados suficientes para a geração do
                    gráfico sobre {disease}
                </div>"""

            empty_charts_count[disease] = 0

            create_maps[disease][state_abbv] = self.get_img_map(
                state_abbv, disease
            )

            # count_cities_by_uf('Santa Catarina', 'dengue')
            count_cities[disease][
                state_abbv
            ] = notif_resume.count_cities_by_uf(state_name, disease)

            df = data_hist_uf(state_abbv=state_abbv, disease=disease)

            if disease == "dengue":
                if not df.empty:
                    last_se[state_abbv] = (
                        str(df.SE.max())[4:] + "/" + str(df.SE.max())[:4]
                    )

                else:
                    last_se[state_abbv] = ""

            # scatterchart
            if df.casos_est.any():
                df_cases = deepcopy(df)

                keys = ["casos_est", "casos"]
                df_by_uf = df_cases.groupby(["SE"])[keys].sum()

                scatter_chart = _create_scatter_chart(df=df_by_uf)
            else:
                scatter_chart = no_data_chart
                empty_charts_count[disease] += 1

            create_scatter_chart[disease][state_abbv] = scatter_chart

            # indicatorchart
            if df.casos.any():
                df_receptivity = deepcopy(df)

                indicator_chart = _create_indicator_chart(
                    df=df_receptivity, state_abbv=state_abbv
                )
            else:
                indicator_chart = no_data_chart
                empty_charts_count[disease] += 1

            create_indicator_chart[disease][state_abbv] = indicator_chart

            # stackbarchart
            df_nivel = deepcopy(df)

            if not df_nivel.empty:
                df_alert = (
                    df_nivel.groupby(["SE", "nivel"])["municipio_geocodigo"]
                    .count()
                    .reset_index()
                )

                color_alert = {1: "Green", 2: "Yellow", 3: "Orange", 4: "Red"}
                df_alert.nivel = df_alert.nivel.apply(
                    lambda v: f"{color_alert[v]} Alert"
                )

                this_year_week = df_alert.SE.max()
                get_week = df_alert.SE >= this_year_week - 53
                df_alert_uf = df_alert[get_week].sort_values(
                    by=["nivel"], ascending=False
                )

                stack_chart = _create_stack_chart(
                    df=df_alert_uf,
                )
            else:
                stack_chart = no_data_chart
                empty_charts_count[disease] += 1

            create_stack_chart[disease][state_abbv] = stack_chart

        context.update(
            {
                "chart_scatter": create_scatter_chart,
                "chart_indicator": create_indicator_chart,
                "chart_stack": create_stack_chart,
                "count_cities": count_cities,
                "last_se": last_se,
                "create_maps": create_maps,
                "no_data_chart": no_data_chart,
                "empty_charts_count": empty_charts_count,
                "states_alert": states_alert,
            }
        )
        return context


class GeoTiffView(View):
    def get(self, request, geocodigo, disease):
        """
        :param kwargs:
        :return:
        """
        geocode = geocodigo

        # load shapefile
        for path in (settings.STATIC_ROOT, settings.STATICFILES_DIRS[0]):
            if not os.path.isdir(path):
                continue
            shp_path = os.path.join(path, "shapefile")

        shp = fiona.open(os.path.join(shp_path, "%s.shp" % geocode))

        result = convert_from_shapefile(
            shapefile=shp, rgb_color=get_last_color_alert(geocode, disease)
        )

        response = HttpResponse(
            result, content_type="application/force-download"
        )

        response["Content-Disposition"] = (
            "attachment; filename=%s.tiff" % geocode
        )

        return response


class GeoJsonView(View):
    def get(self, request, geocodigo, disease):
        cache_key = f"geojson_{geocodigo}"
        geojson = cache.get(cache_key)  # NOQA F811

        if not geojson:
            # Get the path of the GeoJSON file
            geojson_path = self.get_geojson_path(geocodigo)

            # Load the GeoJSON file
            with open(geojson_path) as f:
                geojson_data = json.load(f)

            # Modify the properties of the GeoJSON with the alert color
            hex_color = self.get_last_color_alert(
                geocodigo, disease, color_type="hex"
            )
            geojson_data["features"][0]["properties"]["fill"] = hex_color

            # Serialize the GeoJSON to a string
            geojson = json.dumps(geojson_data)

            # Store in cache for a certain period of time (e.g., 1 hour)
            cache.set(cache_key, geojson, timeout=3600)

        # Create the HTTP response with the GeoJSON
        response = HttpResponse(geojson, content_type="application/json")
        response[
            "Content-Disposition"
        ] = f"attachment; filename={geocodigo}.json"
        return response

    def get_geojson_path(self, geocodigo):
        for path in (
            Path(settings.STATIC_ROOT),
            Path(settings.STATICFILES_DIRS[0]),
        ):
            geojson_path = path / "geojson" / f"{geocodigo}.json"
            if geojson_path.is_file():
                return str(geojson_path)

        # If the file is not found, return an empty path
        return ""


class ReportView(TemplateView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_context_data(self, **kwargs):
        """
        :param kwargs:
        :return:
        """
        context = super().get_context_data(**kwargs)

        report_type = (
            context["report_type"] if "report_type" in context else None
        )

        if report_type is None:
            context.update(self.view_filter_report_type(context))
        elif report_type == "city":
            context.update(self.view_filter_city(context))
        else:
            context.update(self.view_filter_state(context))

        context.update({"disease_list": CID10})

        return context

    def view_filter_report_type(self, context):
        """
        :param context:
        :return:
        """
        self.template_name = "report_filter_report_type.html"

        options_states = ""
        for state_initial, state_name in STATE_NAME.items():
            options_states += """
            <option value="%(state_initial)s">
                %(state_name)s
            </option>""" % {
                "state_name": state_name,
                "state_initial": state_initial,
            }

        context.update({"options_states": options_states})

        return context

    def view_filter_city(self, context):
        """
        :param context:
        :return:
        """
        self.template_name = "report_filter_city.html"

        options_cities = ""
        for geocode, city_name in RegionalParameters.get_cities(
            state_name=STATE_NAME[context["state"]]
        ).items():
            options_cities += """
            <option value="%(geocode)s">
                %(city_name)s
            </option>""" % {
                "geocode": geocode,
                "city_name": city_name,
            }

        dt = datetime.datetime.now() - datetime.timedelta(days=7)
        yw = episem(dt, sep="")
        dt_fmt = episem2date(yw, 1).strftime("%Y-%m-%d")

        context.update(
            {"options_cities": options_cities, "date_query": dt_fmt}
        )

        return context

    def view_filter_state(self, context):
        """
        :param context:
        :return:
        """
        self.template_name = "report_filter_state.html"

        dt = datetime.datetime.now() - datetime.timedelta(days=7)
        yw = episem(dt, sep="")
        dt_fmt = episem2date(yw, 1).strftime("%Y-%m-%d")

        context.update({"date_query": dt_fmt})

        return context


class ReportCityView(TemplateView):
    template_name = "report_city.html"

    def raise_error(self, context, message):
        """
        :return:
        """
        self.template_name = "error.html"
        context.update({"message": message})
        return context

    def get_context_data(self, **kwargs):
        """
        :param kwargs:
        :return:
        """
        context = super(ReportCityView, self).get_context_data(**kwargs)

        geocode = int(context["geocode"])
        year_week = int(context["year_week"])
        year, week = context["year_week"][:4], context["year_week"][-2:]

        error_message_city_doesnt_exist = (
            "Esse municipio não participa do Infodengue. Se tiver "
            + "interesse em aderir, contacte-nos pelo email "
            + ' <a href="mailto:alerta_dengue@fiocruz.br">'
            + "alerta_dengue@fiocruz.br</a>"
        )

        city = City.objects.get(pk=int(geocode))

        regional_get_param = RegionalParameters.get_station_data(
            geocode=int(geocode), disease="dengue"
        )[0]

        # TODO: Fix NA's in the parameters table
        if regional_get_param[5] == "NA":
            regional_get_param[5] = 0

        threshold_pre_epidemic = regional_get_param[7]
        threshold_pos_epidemic = regional_get_param[8]
        threshold_epidemic = regional_get_param[9]

        # Create the dictionary with climate variables

        varcli_dict = {
            "temp.min": [_("°C temperatura mínima")],
            "temp.med": [_("°C temperatura média")],
            "temp.max": [_("°C temperatura máxima")],
            "umid.min": [_("% umidade mínima do ar")],
            "umid.med": [_("% umidade média do ar")],
            "umid.max": [_("% umidade máxima do ar")],
        }

        var_climate = {}
        varcli_pair = {}

        if regional_get_param[3]:
            climate_title1 = regional_get_param[3]
            climate_crit1 = regional_get_param[4]
            varcli_pair[climate_title1] = climate_crit1
            varcli_dict[regional_get_param[3].replace("_", ".")].append(
                regional_get_param[4]
            )

        if regional_get_param[5]:
            climate_title2 = regional_get_param[5]
            climate_crit2 = regional_get_param[6]
            varcli_pair[climate_title2] = climate_crit2
            varcli_dict[regional_get_param[5].replace("_", ".")].append(
                regional_get_param[6]
            )

        varcli_keys = [w.replace("_", ".") for w in list(varcli_pair.keys())]

        for v in varcli_keys:
            var_climate[v] = varcli_dict.get(v)

        df_dengue = ReportCity.read_disease_data(
            disease="dengue",
            geocode=geocode,
            year_week=year_week,
        )

        df_chik = ReportCity.read_disease_data(
            disease="chikungunya",
            geocode=geocode,
            year_week=year_week,
        )

        df_zika = ReportCity.read_disease_data(
            disease="zika",
            geocode=geocode,
            year_week=year_week,
        )

        total_n_dengue = 0
        total_n_dengue_last_year = 0
        total_n_chik = 0
        total_n_chik_last_year = 0
        total_n_zika = 0
        total_n_zika_last_year = 0

        last_year_week_l = []
        disease_last_code = []

        this_year = int(context["year_week"][:4])

        climate_cols = [
            "temp.min",
            "temp.med",
            "temp.max",
            "umid.min",
            "umid.med",
            "umid.max",
        ]

        if not df_dengue.empty:
            last_year_week_l.append(df_dengue.index.max())

            chart_dengue_climate = ReportCityCharts.create_climate_chart(
                df=df_dengue.reset_index()[["SE", *climate_cols]],
                var_climate=var_climate,
            )

            chart_dengue_incidence = ReportCityCharts.create_incidence_chart(
                df=df_dengue,
                year_week=year_week,
                threshold_pre_epidemic=threshold_pre_epidemic,
                threshold_pos_epidemic=threshold_pos_epidemic,
                threshold_epidemic=threshold_epidemic,
            )

            total_n_dengue = df_dengue[df_dengue.index // 100 == this_year][
                "casos notif."
            ].sum()

            total_n_dengue_last_year = df_dengue[
                (df_dengue.index // 100 == year_week // 100 - 1)
                & (df_dengue.index <= year_week - 100)
            ]["casos notif."].sum()

        if not df_chik.empty:
            last_year_week_l.append(df_chik.index.max())

            chart_chik_climate = ReportCityCharts.create_climate_chart(
                df=df_chik.reset_index()[["SE", *climate_cols]],
                var_climate=var_climate,
            )

            chart_chik_incidence = ReportCityCharts.create_incidence_chart(
                df=df_chik,
                year_week=year_week,
                threshold_pre_epidemic=threshold_pre_epidemic,
                threshold_pos_epidemic=threshold_pos_epidemic,
                threshold_epidemic=threshold_epidemic,
            )

            total_n_chik = df_chik[df_chik.index // 100 == this_year][
                "casos notif."
            ].sum()

            total_n_chik_last_year = df_chik[
                (df_chik.index // 100 == year_week // 100 - 1)
                & (df_chik.index <= year_week - 100)
            ]["casos notif."].sum()

        if not df_zika.empty:
            last_year_week_l.append(df_zika.index.max())

            chart_zika_climate = ReportCityCharts.create_climate_chart(
                df=df_zika.reset_index()[["SE", *climate_cols]],
                var_climate=var_climate,
            )

            chart_zika_incidence = ReportCityCharts.create_incidence_chart(
                df=df_zika,
                year_week=year_week,
                threshold_pre_epidemic=threshold_pre_epidemic,
                threshold_pos_epidemic=threshold_pos_epidemic,
                threshold_epidemic=threshold_epidemic,
            )

            total_n_zika = df_zika[df_zika.index // 100 == this_year][
                "casos notif."
            ].sum()

            total_n_zika_last_year = df_zika[
                (df_zika.index // 100 == year_week // 100 - 1)
                & (df_zika.index <= year_week - 100)
            ]["casos notif."].sum()

        if not last_year_week_l:
            return self.raise_error(context, error_message_city_doesnt_exist)

        last_year_week = int(np.nanmax(last_year_week_l))

        for df in [df_dengue, df_chik, df_zika]:
            result = df[df.index == last_year_week]
            if not result.empty:
                disease_last_code.append(float(result["level_code"].iloc[0]))

        max_alert_code = int(np.nanmax(disease_last_code))
        max_alert_color = ALERT_COLOR[max_alert_code]

        # param used by df.to_html
        html_param = dict(
            na_rep="",
            float_format=lambda x: ("%d" % x) if not np.isnan(x) else "",
            index=False,
            classes="table table-striped table-bordered",
        )

        cols_to_html = [
            *varcli_keys,
            "casos notif.",
            "casos_est",
            "incidência",
            # 'pr(incid. subir)',
            "nivel",
        ]

        prepare_html = (
            lambda df: df[cols_to_html]
            .iloc[-12:, :]
            .reset_index()
            .sort_values(by="SE", ascending=[False])
            .to_html(**html_param)
        )

        last_year_week_s = str(last_year_week)
        last_year = last_year_week_s[:4]
        last_week = last_year_week_s[-2:]

        context.update(
            {
                "year": year,
                "week": week,
                "last_year": last_year,
                "last_week": last_week,
                "city_name": city.name,
                "state_name": city.state,
                "df_dengue": prepare_html(df_dengue),
                "df_chik": prepare_html(df_chik),
                "df_zika": prepare_html(df_zika),
                "chart_dengue_climate": chart_dengue_climate,
                "chart_dengue_incidence": chart_dengue_incidence,
                "chart_chik_climate": chart_chik_climate,
                "chart_chik_incidence": chart_chik_incidence,
                "chart_zika_climate": chart_zika_climate,
                "chart_zika_incidence": chart_zika_incidence,
                "total_n_dengue": total_n_dengue,
                "total_n_dengue_last_year": total_n_dengue_last_year,
                "total_n_chik": total_n_chik,
                "total_n_chik_last_year": total_n_chik_last_year,
                "total_n_zika": total_n_zika,
                "total_n_zika_last_year": total_n_zika_last_year,
                "max_alert_color": max_alert_color.title(),
            }
        )
        return context


class ReportStateData(TemplateView):
    template_name = "components/report_state/report_state_charts.html"

    def get_context_data(self, **kwargs):

        context = super(ReportStateData, self).get_context_data(**kwargs)
        state_abbv = context["state"]
        year_week = int(context["year_week"])
        regional_id = int(context["regional_id"])

        level_chart = {}
        notif_chart = {}
        mun_by_regional = {}

        df = ReportState.csv_get_regional_by_state(state_abbv)

        df_regional_filtered = df[df.id_regional == regional_id]

        mun_by_regional = df_regional_filtered.set_index(
            "municipio_geocodigo"
        )["municipio_nome"].to_dict()

        for d in CID10.keys():
            df_muni_by_reg = ReportState.create_report_state_data(
                df_regional_filtered.municipio_geocodigo.to_list(),
                d,
                year_week,
            )

            notif_chart[d] = ReportStateCharts.create_notific_chart(
                df_muni_by_reg
            )

            level_chart[d] = ReportStateCharts.create_level_chart(
                df_muni_by_reg
            )

        context.update(
            {
                "year_week": year_week,
                "state_abbv": state_abbv,
                "notif_chart": notif_chart,
                "level_chart": level_chart,
                "regional_id": regional_id,
                "cities": mun_by_regional,
            }
        )

        return context


class ReportStateView(TemplateView):
    template_name = "report_state.html"

    def get_context_data(self, **kwargs):
        context = super(ReportStateView, self).get_context_data(**kwargs)
        context = super().get_context_data(**kwargs)
        state = context["state"]
        last_year_week_s = context["year_week"]

        last_year = last_year_week_s[:4]
        last_week = last_year_week_s[-2:]

        df = ReportState.csv_get_regional_by_state(state)

        regional_dict = {
            d["id_regional"]: d["nome_regional"]
            for d in df.iloc[:, 0:2].to_dict(orient="records")
        }

        context.update(
            {
                "state_name": STATE_NAME[state],
                "regional_dict": regional_dict,
                "year_week": context["year_week"],
                "last_year": last_year,
                "last_week": last_week,
            }
        )

        return context
