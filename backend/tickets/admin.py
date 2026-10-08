from django.contrib import admin

from .models import SlaPolicy


@admin.register(SlaPolicy)
class SlaPolicyAdmin(admin.ModelAdmin):
	list_display = ('priority', 'response_target', 'resolution_target', 'is_active')
	list_filter = ('priority', 'is_active')
	ordering = ('priority',)
