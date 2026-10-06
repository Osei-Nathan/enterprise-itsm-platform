from rest_framework.permissions import BasePermission

from .models import UserRole


class RolePermission(BasePermission):
    allowed_roles = ()

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role in self.allowed_roles
        )


class IsEmployee(RolePermission):
    allowed_roles = (UserRole.EMPLOYEE,)


class IsTechnician(RolePermission):
    allowed_roles = (UserRole.TECHNICIAN,)


class IsITManager(RolePermission):
    allowed_roles = (UserRole.IT_MANAGER,)


class IsAdmin(RolePermission):
    allowed_roles = (UserRole.ADMIN,)


class IsITStaff(RolePermission):
    allowed_roles = (UserRole.TECHNICIAN, UserRole.IT_MANAGER, UserRole.ADMIN)


class IsTechnicianOrAbove(RolePermission):
    allowed_roles = (
        UserRole.TECHNICIAN,
        UserRole.IT_MANAGER,
        UserRole.ADMIN,
    )


class IsManagerOrAdmin(RolePermission):
    allowed_roles = (UserRole.IT_MANAGER, UserRole.ADMIN)
