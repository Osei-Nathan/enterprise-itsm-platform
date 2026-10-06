from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Department, User


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
	list_display = ('name', 'manager', 'created_at', 'updated_at')
	search_fields = ('name', 'description')
	list_filter = ('created_at', 'updated_at')


@admin.register(User)
class CustomUserAdmin(UserAdmin):
	list_display = (
		'username',
		'email',
		'first_name',
		'last_name',
		'role',
		'department',
		'is_active',
	)
	list_filter = ('role', 'department', 'is_active')
	search_fields = ('username', 'email', 'first_name', 'last_name')
	fieldsets = UserAdmin.fieldsets + (
		(
			'ITSM Information',
			{'fields': ('phone', 'role', 'department')},
		),
	)
	add_fieldsets = UserAdmin.add_fieldsets + (
		(
			'ITSM Information',
			{'fields': ('phone', 'role', 'department')},
		),
	)
