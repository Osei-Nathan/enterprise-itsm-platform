from rest_framework.permissions import BasePermission

from accounts.models import UserRole


class CanCreateTicket(BasePermission):
	message = 'A recognized ITSM role is required to create tickets.'

	def has_permission(self, request, view):
		user = request.user
		return bool(
			user
			and user.is_authenticated
			and user.role in UserRole.values
		)