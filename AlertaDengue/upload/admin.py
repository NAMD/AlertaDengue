from django.contrib import admin

from .models import OwnCloudUser, SINAN

admin.site.register([OwnCloudUser, SINAN])
