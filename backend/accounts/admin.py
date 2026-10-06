from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Department, User


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
	list_display = ('name',)
	search_fields = ('name',)


@admin.register(User)
class AccountUserAdmin(UserAdmin):
	fieldsets = UserAdmin.fieldsets + (
		('ITSM profile', {'fields': ('role', 'department')}),
	)
	list_display = ('username', 'email', 'role', 'department', 'is_staff', 'is_active')
	list_filter = ('role', 'department', 'is_staff', 'is_active')
