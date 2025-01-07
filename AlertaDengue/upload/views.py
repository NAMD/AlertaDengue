from pathlib import Path

import humanize

from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import JsonResponse, QueryDict
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import File
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import FormView, View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.shortcuts import render
from chunked_upload.views import ChunkedUploadView, ChunkedUploadCompleteView

from . import models, forms


User = get_user_model()


class SINANDashboard(LoginRequiredMixin, View):
    template_name = "sinan/index.html"

    @never_cache
    def get(self, request, *args, **kwargs):
        context = {}
        return render(request, self.template_name, context)


class SINANStatus(LoginRequiredMixin, View):
    template_name = "sinan/status.html"

    @never_cache
    def get(self, request, *args, **kwargs):
        sinan_upload_id = kwargs.get('sinan_upload_id')
        context = {}

        try:
            sinan = models.SINANUpload.objects.get(
                pk=sinan_upload_id,
                upload__user=request.user
            )
        except models.SINANUpload.DoesNotExist:
            return JsonResponse({"error": "Upload not found"}, safe=True)

        context["id"] = sinan.pk
        context["filename"] = sinan.upload.filename
        context["status"] = sinan.status.status
        context["uploaded_at"] = sinan.uploaded_at

        if sinan.status.status == 1:
            context["inserts"] = self.humanizer(sinan.status.inserts)
            context["updates"] = self.humanizer(sinan.status.updates)

            hours, remainder = divmod(sinan.status.time_spend, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours > 0:
                time_spend = f"{int(hours)}:{int(minutes)}:{int(seconds)}"
            elif minutes > 0:
                time_spend = f"{int(minutes)}:{int(seconds)}"
            else:
                time_spend = f"{int(seconds)}s"

            context["time_spend"] = time_spend

        if sinan.status.status == 2:
            error_message = (
                sinan.status.read_logs(level="ERROR")[0].split(" - ")[1]
            )
            context["error"] = error_message

        return render(request, self.template_name, context)

    def humanizer(self, integer) -> str:
        word = humanize.intword(integer)

        suffixes = {
            "thousand": "k",
            "million": "M",
            "billion": "B"
        }

        for suffix in suffixes:
            if suffix in word:
                word = word.replace(f" {suffix}", suffixes[suffix])

        return word


class SINANUpload(LoginRequiredMixin, FormView):
    form_class = forms.SINANForm
    template_name = "sinan/card.html"
    success_url = reverse_lazy("upload:sinan")

    def post(self, request, *args, **kwargs):
        post = request.POST.copy()
        post["uploaded_by"] = request.user.id
        self.request.POST = post
        return super().post(self.request, *args, **kwargs)

    def form_valid(self, form):
        upload = models.SINANChunkedUpload.objects.get(
            upload_id=form.cleaned_data["upload_id"], user=self.request.user
        )
        sinan_file = models.SINANUpload.objects.create(
            cid10=form.cleaned_data["cid10"],
            uf=form.cleaned_data["uf"],
            year=form.cleaned_data["notification_year"],
            upload=upload,
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        disease = {
            "DENG": "A90",
            "CHIK": "A92.0",
            "ZIKA": "A928",
        }

        context = super().get_context_data(**kwargs)

        if self.request.method == "POST":
            return context

        filename = self.request.GET.get("filename", "")

        for uf in models.UF_CODES:
            if uf in str(Path(filename).with_suffix("")).upper():
                context["form"] = self.get_form(self.get_form_class())
                context["form"].fields["uf"].initial = uf

        for dis in disease:
            if dis in str(Path(filename).with_suffix("")).upper():
                context["form"] = self.get_form(self.get_form_class())
                context["form"].fields["cid10"].initial = disease[dis]

        context["filename"] = filename
        return context


class SINANChunkedUploadView(ChunkedUploadView):
    model = models.SINANChunkedUpload

    def delete(self, request, *args, **kwargs):
        upload_id = kwargs.get('upload_id')
        try:
            upload = self.model.objects.get(upload_id=upload_id)
            if upload.user != request.user:
                raise PermissionDenied("Forbidden")
            upload.file.delete()
            upload.delete()
            return JsonResponse(
                {"success": True, "message": f"{upload.file.name}"},
                status=200
            )
        except self.model.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Unknown upload"},
                status=404
            )


class SINANChunkedUploadCompleteView(ChunkedUploadCompleteView):
    model = models.SINANChunkedUpload

    def get_response_data(self, chunked_upload, request):
        return {
            "id": chunked_upload.id,
            "filename": chunked_upload.filename,
        }


@never_cache
@csrf_protect
def get_user_uploads(request):
    context = {}
    uploads = models.SINANUpload.objects.filter(upload__user=request.user)
    context["uploads"] = list(
        uploads.order_by("-uploaded_at").values_list("id", flat=True)
    )
    print(context)
    return JsonResponse(context)
