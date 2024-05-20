import os
import re
import io
import csv
from datetime import datetime
from dateutil import parser
from pathlib import Path

import pandas as pd
import owncloud

from django.http import JsonResponse, HttpResponse, HttpRequest
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.views import View
from django.shortcuts import render, redirect
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from celery.result import AsyncResult

from .sinan.utils import EXPECTED_FIELDS, REQUIRED_FIELDS
from .tasks import sinan_split_by_uf_or_chunk, owncloud_download_file
from .models import UFs, Diseases, SINAN, OwnCloudUser


User = get_user_model()


class UploadSINAN(View):
    template_name = "upload.html"

    @never_cache
    def get(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_staff:  # type: ignore
            return redirect("dados:main")
        context = {}

        context["ufs"] = UFs.choices
        context["diseases"] = Diseases.choices

        return render(request, self.template_name, context)


class ProcessSINAN(View):
    template_name = "process-file.html"

    @never_cache
    def get(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_staff:  # type: ignore
            messages.error(request, "Unauthorized")
            return redirect("dados:main")

        context = {}

        user_id = request.GET.get("user_id", None)
        disease = request.GET.get("disease", None)
        notification_year = request.GET.get("notification_year", None)
        uf = request.GET.get("uf", None)
        file_path = request.GET.get("file_path", None)
        task_id = request.GET.get("task_id", None)

        if not all(
            [user_id, disease, notification_year, uf, file_path, task_id]
        ):
            messages.error(
                request,
                "Access denied, please use /upload/sinan/ instead",
            )
            return redirect("upload_sinan")

        user = User.objects.get(pk=user_id)

        if request.user != user:
            messages.error(
                request,
                "Access denied, please use /upload/sinan/ instead",
            )
            return redirect("upload_sinan")

        dest_dir = Path(os.path.splitext(str(file_path))[0])
        dest_dir.mkdir(exist_ok=True)

        context["user_id"] = user_id
        context["disease"] = disease
        context["notification_year"] = notification_year
        context["uf"] = uf
        context["task_id"] = task_id
        context["dest_dir"] = str(dest_dir)
        context["file_name"] = Path(str(file_path)).name

        return render(request, self.template_name, context)


@never_cache
def owncloud_list_files(request: HttpRequest) -> JsonResponse:
    if not request.user.is_staff:  # type: ignore
        return JsonResponse(
            {'error': 'Unauthorized'}, status=403
        )

    if request.method == "GET":
        try:
            owncloud_user = OwnCloudUser.objects.get(user=request.user)
        except OwnCloudUser.DoesNotExist:
            return JsonResponse(
                {'error': (
                    'OwnCloud user not configured. Please contact the moderation'
                )}, status=404
            )

        directory = request.GET.get("directory-path")

        try:
            oc = owncloud.Client(settings.OWNCLOUD_URL)
            oc.login(owncloud_user.username, owncloud_user.password)
        except (owncloud.HTTPResponseError, AttributeError):
            oc.logout()
            return JsonResponse(
                {'error': (
                    'Unable to login with OwnCloud user '
                    f'{owncloud_user.username}'
                )}, status=403
            )

        try:
            files = sorted(
                oc.list(directory),
                key=(
                    lambda file: parser.parse(
                        file.attributes['{DAV:}getlastmodified']
                    )
                ),
                reverse=True
            )
        except owncloud.HTTPResponseError:
            return JsonResponse(
                {'error': f'Directory {directory} not found'},
                status=404
            )
        finally:
            oc.logout()

        res: list[dict[str, str | int]] = []
        for file in files:
            res_file = {}
            last_modify = parser.parse(
                file.attributes['{DAV:}getlastmodified']
            )
            res_file["name"] = file.name
            res_file["path"] = file.path
            res_file["last_modify"] = last_modify.strftime("%x %H:%M")
            res_file["size"] = file.get_size()
            try:
                res_file["status"] = SINAN.objects.get(filename=file.name)
            except SINAN.DoesNotExist:
                res_file["status"] = ""
            res.append(res_file)

        return JsonResponse({"owncloud_files": res}, status=200)
    return JsonResponse({'error': 'Invalid request'}, status=403)


@never_cache
def owncloud_download_file_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_staff:  # type: ignore
        return JsonResponse(
            {'error': 'Unauthorized'}, status=403
        )

    if request.method == "POST":
        try:
            owncloud_user = OwnCloudUser.objects.get(user=request.user)
        except OwnCloudUser.DoesNotExist:
            return JsonResponse(
                {'error': (
                    'OwnCloud user not configured. Please contact the moderation'
                )}, status=404
            )

        file_path = request.POST.get("file_path", None)
        output_path = request.POST.get("output_path", None)
        imported_files = Path(settings.DBF_SINAN) / "imported"

        if not file_path:
            return JsonResponse(
                {"error": "file_path must be specified"}, status=404
            )

        if not output_path:
            file = Path(file_path)
            output_path = str(imported_files / file.name)

        try:
            oc = owncloud.Client(settings.OWNCLOUD_URL)
            oc.login(owncloud_user.username, owncloud_user.password)
        except (owncloud.HTTPResponseError, AttributeError):
            oc.logout()
            return JsonResponse(
                {'error': (
                    'Unable to login with OwnCloud user '
                    f'{owncloud_user.username}'
                )}, status=403
            )

        task = owncloud_download_file.delay(
            username=owncloud_user.username,
            password=owncloud_user.password,
            file_path=str(file_path),
            output_path=str(output_path)
        )

        return JsonResponse(
            {"task_id": task.id, "output_path": str(output_path)}, status=201
        )

    if request.method == "GET":
        task_id = request.GET.get("task_id", None)
        if task_id:
            task = AsyncResult(task_id)
            return JsonResponse({"task_status": task.status}, status=200)

    return JsonResponse({"error": "Incorrect request"}, status=404)


@never_cache
def sinan_upload_file(request: HttpRequest) -> HttpResponse:
    if not request.user.is_staff:  # type: ignore
        return JsonResponse(
            {'error': 'Unauthorized'}, status=403
        )

    if request.method == "POST" and request.FILES["file"]:
        file = request.FILES["file"]

        if not isinstance(file, UploadedFile):
            return JsonResponse(
                {'error': 'Incorrect file received'}, status=400
            )

        dest_dir = Path(os.path.join(settings.MEDIA_ROOT, "upload/sinan/"))

        dest_dir.mkdir(exist_ok=True, parents=True)

        file_path = dest_dir / str(file.name)
        with open(file_path, 'wb') as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        return JsonResponse({'file_path': str(file_path)})

    return JsonResponse(
        {'error': 'POST request with file required'}, status=400
    )


@never_cache
def sinan_chunk_uploaded_file(request: HttpRequest) -> HttpResponse:
    if not request.user.is_staff:  # type: ignore
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    if request.method == "POST":
        file_path = request.POST.get("file_path")

        if not isinstance(file_path, str):
            return JsonResponse(
                {'error': 'Incorrect file path received'}, status=400
            )

        file = Path(file_path)

        if not file.exists():
            return JsonResponse({'error': 'File not found'}, status=404)

        dest_dir = Path(os.path.splitext(str(file))[0])

        dest_dir.mkdir(exist_ok=True, parents=True)

        for csv_file in dest_dir.glob("*"):
            csv_file.unlink(missing_ok=True)

        result = sinan_split_by_uf_or_chunk.delay(
            file_path=str(file),
            dest_dir=str(dest_dir),
            by_uf=False
        )

        request.session['task_id'] = result.id

        return JsonResponse({'task_id': result.id}, status=200)

    if request.method == "GET":
        task_id = request.GET.get("task_id")

        if not task_id:
            return JsonResponse({'error': f'Unknown task ID'}, status=400)

        task = AsyncResult(task_id)

        if task.status == "SUCCESS":
            _, chunks_tasks = task.get()
            return JsonResponse(
                {'task_status': task.status, 'chunks_dir': chunks_tasks}
            )
        else:
            return JsonResponse({'task_status': task.status})

    return JsonResponse({'error': 'Request error'}, status=404)


@never_cache
def sinan_watch_for_uf_chunks(request: HttpRequest) -> HttpResponse:
    if not request.user.is_staff:  # type: ignore
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    if request.method == "GET":
        dest_dir_path = request.GET.get("dest_dir")

        if not isinstance(dest_dir_path, str):
            return JsonResponse(
                {'error': 'Incorrect dir path received'}, status=400
            )

        dest_dir = Path(dest_dir_path).absolute()

        if not dest_dir.exists() or not dest_dir.is_dir():
            return JsonResponse({'error': 'Incorrect `dest_dir`'}, status=404)

        regexp = re.compile(r"|".join(list(map(str, UFs))) + r"\.csv")
        uf_files: list[dict[str, str | int]] = [
            {
                "file": f.name,
                "uf": f.name[:2],
                "size": os.path.getsize(str(f))
            }
            for f in dest_dir.glob("*.csv")
            if regexp.match(f.name)
        ]

        return JsonResponse({"files": uf_files}, status=200)

    return JsonResponse({'error': 'Request error'}, status=404)


@never_cache
def sinan_object_router(request: HttpRequest) -> HttpResponse:
    if not request.user.is_staff:  # type: ignore
        return redirect('dados:main')

    if request.method == "GET":
        disease = request.GET.get("disease", None)
        notification_year = request.GET.get("notification_year", None)
        uf = request.GET.get("uf", None)
        dest_dir = request.GET.get("dest_dir", None)
        file_name = request.GET.get("file_name", None)

        if not all([disease, notification_year, uf, dest_dir, file_name]):
            return JsonResponse({'error': 'Bad request'}, status=400)

        dest_dir = Path(dest_dir)
        file = dest_dir / file_name

        if not file.exists():
            return JsonResponse({'error': 'File not found'}, status=404)

        try:
            sinan = SINAN.objects.get(
                filepath=str(file),
                disease=disease,
                notification_year=int(notification_year)
            )
        except SINAN.DoesNotExist:
            sinan = SINAN.create(
                filepath=str(file),
                disease=disease,
                notification_year=int(notification_year),
                uf=uf,
                uploaded_by=request.user,
                uploaded_at=datetime.now().date()
            )
            sinan.save()
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

        sinan = SINAN.objects.get(pk=sinan.id)

        return JsonResponse(
            {
                "id": sinan.id,
                "file_name": sinan.filename,
                "status": sinan.status,
                "status_error": sinan.status_error,
                "parse_error": sinan.parse_error,
                "misparsed_cols": sinan.misparsed_cols,
                "inserted_rows": sinan.inserted_rows,
            },
            status=200
        )
    return JsonResponse({'error': 'Request error'}, status=404)


@never_cache
def sinan_check_csv_columns(request: HttpRequest) -> HttpResponse:
    if not request.user.is_staff:  # type: ignore
        return redirect('dados:main')

    if request.method == "POST" and request.FILES["truncated-file"]:
        file = request.FILES["truncated-file"]

        if not isinstance(file, UploadedFile):
            return JsonResponse(
                {'error': 'Incorrect file path received'}, status=400
            )

        file_data = file.read()
        context = {}

        if (
            str(file.name).lower().endswith((".csv.gz", ".csv"))
            or file.content_type == "text/csv"
        ):
            try:
                sniffer = csv.Sniffer()
                sep = sniffer.sniff(file_data.decode('utf-8')).delimiter

                columns = pd.read_csv(
                    io.BytesIO(file_data),
                    nrows=10,
                    sep=sep
                ).columns.to_list()
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=400)

        # elif file.name.lower().endswith(".dbf"):
        #     columns = Dbf5(str(file), codec="iso-8859-1").columns
        # elif file.name.lower().endswith(".parquet"):
        #     columns = dd.read_parquet(  # pyright: ignore
        #         str(file), engine="fastparquet"
        #     ).columns  # pyright: ignore

        else:
            return JsonResponse(
                {'error': f'Could not extract {file.name} columns'}, status=400
            )

        if not all([c in columns for c in REQUIRED_FIELDS]):
            return JsonResponse({'error': (
                "Required field(s): "
                f"{list(set(REQUIRED_FIELDS).difference(set(columns)))} "
                "not found in data file"
            )}, status=400)

        if not all([c in columns for c in EXPECTED_FIELDS.values()]):
            context["warning"] = (
                "Expected field(s): "
                f"{list(set(EXPECTED_FIELDS.values()).difference(set(columns)))} "
                "not found in data file, and will be  filled with None"
            )

        context['file'] = str(file.name)

        context['columns'] = columns

        return JsonResponse(context, status=200)

    return JsonResponse(
        {'error': 'POST request with file required'},
        status=400
    )
