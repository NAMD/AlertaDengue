from django.http import HttpResponse
from django.views.generic.base import View
import datetime as dt
from datetime import datetime
import os

# local
from .db import NotificationQueries, STATE_NAME, AlertCity
from dados.episem import episem

import json
from dotenv import load_dotenv
from os.path import join, dirname

env_file = os.environ.get('ENV_FILE', '.env')

env_path = join(dirname(dirname(dirname(__file__))), env_file)
load_dotenv(env_path)


class _GetMethod:
    """"""

    def _get(self, param, default=None, cast=None, error_message=None):
        """

        :param param:
        :param default:
        :return:
        """
        if (
            error_message is not None
            and param not in self.request.GET
            and default is None
        ):
            raise Exception(error_message)

        result = (
            self.request.GET[param] if param in self.request.GET else default
        )

        return result if cast is None or result is None else cast(result)


class NotificationReducedCSV_View(View, _GetMethod):
    """"""

    _state_name = STATE_NAME

    request = None

    def get(self, request):
        """

        :param kwargs:
        :return:
        """
        self.request = request

        state_name = self._get('state_abv', default='').upper()

        if state_name not in self._state_name:
            return HttpResponse(
                'ERROR: The parameter state_abv not found. '
                + 'This parameter must have 2 letters (e.g. RJ).',
                content_type="text/plain",
                status=404,
            )

        uf = self._state_name[state_name]

        chart_type = self._get('chart_type')

        notifQuery = NotificationQueries(
            uf=uf,
            disease_values=self._get('diseases'),
            age_values=self._get('ages'),
            gender_values=self._get('genders'),
            city_values=self._get('cities'),
            initial_date=self._get('initial_date'),
            final_date=self._get('final_date'),
        )

        result = None

        if chart_type == 'disease':
            result = notifQuery.get_disease_dist().to_csv()
        elif chart_type == 'age':
            result = notifQuery.get_age_dist().to_csv()
        elif chart_type == 'age_gender':
            result = notifQuery.get_age_gender_dist().to_csv()
        elif chart_type == 'age_male':
            result = notifQuery.get_age_male_dist().to_csv()
        elif chart_type == 'age_female':
            result = notifQuery.get_age_female_dist().to_csv()
        elif chart_type == 'gender':
            result = notifQuery.get_gender_dist().to_csv()
        elif chart_type == 'period':
            result = notifQuery.get_period_dist().to_csv(
                date_format='%Y-%m-%d'
            )
        elif chart_type == 'epiyears':
            # just filter by one disease
            result = notifQuery.get_epiyears(uf, self._get('disease')).to_csv()
        elif chart_type == 'total_cases':
            result = notifQuery.get_total_rows().to_csv()
        elif chart_type == 'selected_cases':
            result = notifQuery.get_selected_rows().to_csv()

        return HttpResponse(result, content_type="text/plain")


class AlertCityView(View, _GetMethod):
    """"""

    request = None

    def get(self, request):
        self.request = request
        format = ''

        dt_now = dt.datetime.now()
        dt_start = dt_now - dt.timedelta(weeks=int(os.getenv('WEEK_ND')))

        # Epidemic Year Week default format = YYYYWW
        year_end, week_end = (
            episem(dt_now, sep='')[:4],
            episem(dt_now, sep='')[-2:],
        )
        year_start, week_start = (
            episem(dt_start, sep='')[:4],
            episem(dt_start, sep='')[-2:],
        )

        try:
            disease = self._get(
                'disease', error_message='Disease sent is empty.'
            ).lower()
            geocode = self._get(
                'geocode', cast=int, error_message='GEO-Code sent is empty.'
            )
            format = self._get(
                'format', error_message='Format sent is empty.'
            ).lower()

            epiweek_start = self._get(
                'epiweek_start',
                default=int(week_start),
                cast=int,
                error_message='Epidemic start week sent is empty.',
            )

            epiweek_end = self._get(
                'epiweek_end',
                default=int(week_end),
                cast=int,
                error_message='Epidemic end week sent is empty.',
            )

            epiyear_start = self._get(
                'epiyear_start',
                default=int(year_start),
                cast=int,
                error_message='Epidemic start year sent is empty.',
            )
            epiyear_end = self._get(
                'epiyear_end',
                default=int(year_end),
                cast=int,
                error_message='Epidemic end year sent is empty.',
            )

            if format not in ['csv', 'json']:
                raise Exception(
                    'The output format available are: `csv` or `json`.'
                )

            # EpidemEpidemiological Week default format = YYYYWW
            epi_yearweek_start = epiyear_start * 100 + epiweek_start
            epi_yearweek_end = epiyear_end * 100 + epiweek_end

            df = None

            while True:
                df = AlertCity.search(
                    geocode=geocode,
                    disease=disease,
                    ew_start=epi_yearweek_start,
                    ew_end=epi_yearweek_end,
                )
                if not df.empty:
                    break
                epi_yearweek_start -= 3

            # change all keys to lower case
            df.drop(
                columns=['municipio_geocodigo', 'municipio_nome'],
                inplace=True,
            )

            if format == 'json':
                result = df.to_json(orient='records')
            else:
                result = df.to_csv(index=False)
        except Exception as e:
            if format == 'json':
                result = '{"error_message": "%s"}' % e
            else:
                result = '[EE] error_message: %s' % e

        content_type = 'application/json' if format == 'json' else 'text/plain'

        return HttpResponse(result, content_type=content_type)


class EpiYearWeekView(View, _GetMethod):
    """
    JSON output
    """

    request = None

    def get(self, request):
        self.request = request
        output_format = 'json'

        try:
            epidate_s = self._get(
                'epidate', error_message='epidate sent is empty.'
            )

            epidate = datetime.strptime(epidate_s, '%Y-%m-%d')
            epi_year_week = episem(epidate, sep='')

            if output_format == 'json':
                result = json.dumps(
                    dict(
                        epi_year_week=epi_year_week,
                        epi_year=epi_year_week[:4],
                        epi_week=epi_year_week[4:],
                    )
                )
            else:
                result = '' % epi_year_week

        except Exception as e:
            if output_format == 'json':
                result = '{"error_message": "%s"}' % e
            else:
                result = '[EE] error_message: %s' % e

        content_type = (
            'application/json' if output_format == 'json' else 'text/plain'
        )

        return HttpResponse(result, content_type=content_type)
