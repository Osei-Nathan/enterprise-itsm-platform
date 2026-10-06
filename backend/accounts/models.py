from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models


class Department(models.Model):
	name = models.CharField(max_length=100, unique=True)
	description = models.TextField(blank=True)
	manager = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='managed_departments',
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name


class UserRole(models.TextChoices):
	EMPLOYEE = 'EMPLOYEE', 'Employee'
	TECHNICIAN = 'TECHNICIAN', 'Technician'
	IT_MANAGER = 'IT_MANAGER', 'IT Manager'
	ADMIN = 'ADMIN', 'Admin'


class User(AbstractUser):
	phone = models.CharField(max_length=20, blank=True)
	role = models.CharField(
		max_length=20,
		choices=UserRole.choices,
		default=UserRole.EMPLOYEE,
	)
	department = models.ForeignKey(
		Department,
		on_delete=models.SET_NULL,
		related_name='users',
		null=True,
		blank=True,
	)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.get_full_name() or self.username
