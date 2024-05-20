from django.urls import path

from . import views

urlpatterns = [
    path("sinan/", views.UploadSINAN.as_view(), name="upload_sinan"),
    path(
        "sinan/csv-preview/",
        views.sinan_check_csv_columns,
        name="sinan_csv_preview"
    ),
    path(
        "sinan/upload-file/",
        views.sinan_upload_file,
        name="sinan_upload_file"
    ),
    path(
        "sinan/process-file/",
        views.ProcessSINAN.as_view(),
        name="sinan_process_file"
    ),
    path(
        "sinan/chunk-upload-file/",
        views.sinan_chunk_uploaded_file,
        name="sinan_chunk_uploaded_file"
    ),
    path(
        "sinan/watch-uf-chunks/",
        views.sinan_watch_for_uf_chunks,
        name="sinan_watch_for_uf_chunks"
    ),
    path(
        "sinan/object-router/",
        views.sinan_object_router,
        name="sinan_object_router"
    ),
    path(
        "sinan/owncloud/list-files/",
        views.owncloud_list_files,
        name="owncloud_list_files"
    ),
    path(
        "sinan/owncloud/get-file/",
        views.owncloud_download_file_view,
        name="owncloud_get_file"
    )
]
