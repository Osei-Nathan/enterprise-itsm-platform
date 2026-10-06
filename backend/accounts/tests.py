from django.test import TestCase
from rest_framework.test import APIRequestFactory, APITestCase

from .models import Department, User, UserRole
from .permissions import (
	IsAdmin,
	IsEmployee,
	IsITManager,
	IsITStaff,
	IsManagerOrAdmin,
	IsTechnician,
	IsTechnicianOrAbove,
)


class UserModelTests(TestCase):
	def test_new_user_defaults_to_employee_role(self):
		user = User.objects.create_user(username='employee', password='local-test-password')

		self.assertEqual(user.role, UserRole.EMPLOYEE)
		self.assertTrue(user.check_password('local-test-password'))

	def test_user_can_belong_to_a_department(self):
		department = Department.objects.create(name='IT')
		user = User.objects.create_user(
			username='technician',
			password='local-test-password',
			role=UserRole.TECHNICIAN,
			department=department,
		)

		self.assertEqual(user.role, UserRole.TECHNICIAN)
		self.assertEqual(user.department, department)

	def test_department_manager_uses_custom_user_relationship(self):
		user = User.objects.create_user(username='manager', password='local-test-password')
		department = Department.objects.create(name='Operations', manager=user)

		self.assertEqual(department.manager, user)
		self.assertIn(department, user.managed_departments.all())


class AuthenticationAPITests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='employee',
			password='local-test-password',
			email='employee@example.com',
		)

	def test_token_endpoint_returns_access_and_refresh_tokens(self):
		response = self.client.post('/api/auth/token/', {
			'username': 'employee',
			'password': 'local-test-password',
		}, format='json')

		self.assertEqual(response.status_code, 200)
		self.assertIn('access', response.data)
		self.assertIn('refresh', response.data)

	def test_invalid_credentials_are_rejected(self):
		response = self.client.post('/api/auth/token/', {
			'username': 'employee',
			'password': 'incorrect-password',
		}, format='json')

		self.assertEqual(response.status_code, 401)
		self.assertNotIn('access', response.data)
		self.assertNotIn('refresh', response.data)

	def test_current_user_endpoint_requires_jwt_and_returns_role(self):
		unauthenticated_response = self.client.get('/api/auth/me/')
		self.assertEqual(unauthenticated_response.status_code, 401)

		token_response = self.client.post('/api/auth/token/', {
			'username': 'employee',
			'password': 'local-test-password',
		}, format='json')
		self.client.credentials(
			HTTP_AUTHORIZATION=f"Bearer {token_response.data['access']}"
		)

		response = self.client.get('/api/auth/me/')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['role'], UserRole.EMPLOYEE)
		self.assertIsNone(response.data['department'])

	def test_current_user_includes_department_id_and_name(self):
		department = Department.objects.create(name='IT')
		self.user.department = department
		self.user.save(update_fields=['department'])
		token_response = self.client.post('/api/auth/token/', {
			'username': 'employee',
			'password': 'local-test-password',
		}, format='json')
		self.client.credentials(
			HTTP_AUTHORIZATION=f"Bearer {token_response.data['access']}"
		)

		response = self.client.get('/api/auth/me/')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['department'], {
			'id': department.id,
			'name': 'IT',
		})

	def test_refresh_endpoint_returns_new_access_token(self):
		token_response = self.client.post('/api/auth/token/', {
			'username': 'employee',
			'password': 'local-test-password',
		}, format='json')

		response = self.client.post('/api/auth/token/refresh/', {
			'refresh': token_response.data['refresh'],
		}, format='json')

		self.assertEqual(response.status_code, 200)
		self.assertIn('access', response.data)

	def test_only_managers_and_admins_can_create_departments(self):
		token_response = self.client.post('/api/auth/token/', {
			'username': 'employee',
			'password': 'local-test-password',
		}, format='json')
		self.client.credentials(
			HTTP_AUTHORIZATION=f"Bearer {token_response.data['access']}"
		)

		response = self.client.post('/api/departments/', {
			'name': 'Finance',
			'description': 'Finance department',
		}, format='json')

		self.assertEqual(response.status_code, 403)
		self.assertFalse(Department.objects.filter(name='Finance').exists())

	def test_manager_can_create_department(self):
		manager = User.objects.create_user(
			username='it-manager',
			password='local-test-password',
			role=UserRole.IT_MANAGER,
		)
		token_response = self.client.post('/api/auth/token/', {
			'username': manager.username,
			'password': 'local-test-password',
		}, format='json')
		self.client.credentials(
			HTTP_AUTHORIZATION=f"Bearer {token_response.data['access']}"
		)

		response = self.client.post('/api/departments/', {
			'name': 'Finance',
			'description': 'Finance department',
		}, format='json')

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['name'], 'Finance')
		self.assertEqual(Department.objects.get(name='Finance').manager, None)

	def test_admin_can_create_department(self):
		admin = User.objects.create_user(
			username='it-admin',
			password='local-test-password',
			role=UserRole.ADMIN,
		)
		token_response = self.client.post('/api/auth/token/', {
			'username': admin.username,
			'password': 'local-test-password',
		}, format='json')
		self.client.credentials(
			HTTP_AUTHORIZATION=f"Bearer {token_response.data['access']}"
		)

		response = self.client.post('/api/departments/', {
			'name': 'Administration',
			'description': 'IT administration department',
		}, format='json')

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['name'], 'Administration')
		self.assertTrue(Department.objects.filter(name='Administration').exists())


class RolePermissionTests(TestCase):
	def setUp(self):
		self.request_factory = APIRequestFactory()

	def has_permission(self, permission_class, role):
		request = self.request_factory.get('/')
		request.user = User(role=role)
		return permission_class().has_permission(request, None)

	def test_technician_permission_includes_technician_and_above(self):
		self.assertTrue(self.has_permission(IsTechnicianOrAbove, UserRole.TECHNICIAN))
		self.assertTrue(self.has_permission(IsTechnicianOrAbove, UserRole.IT_MANAGER))
		self.assertFalse(self.has_permission(IsTechnicianOrAbove, UserRole.EMPLOYEE))

	def test_individual_role_permissions_match_only_their_role(self):
		self.assertTrue(self.has_permission(IsEmployee, UserRole.EMPLOYEE))
		self.assertFalse(self.has_permission(IsEmployee, UserRole.TECHNICIAN))
		self.assertTrue(self.has_permission(IsTechnician, UserRole.TECHNICIAN))
		self.assertFalse(self.has_permission(IsTechnician, UserRole.IT_MANAGER))
		self.assertTrue(self.has_permission(IsITManager, UserRole.IT_MANAGER))
		self.assertFalse(self.has_permission(IsITManager, UserRole.ADMIN))

	def test_it_staff_includes_technicians_managers_and_admins(self):
		self.assertTrue(self.has_permission(IsITStaff, UserRole.TECHNICIAN))
		self.assertTrue(self.has_permission(IsITStaff, UserRole.IT_MANAGER))
		self.assertTrue(self.has_permission(IsITStaff, UserRole.ADMIN))
		self.assertFalse(self.has_permission(IsITStaff, UserRole.EMPLOYEE))

	def test_manager_permission_excludes_technicians(self):
		self.assertTrue(self.has_permission(IsManagerOrAdmin, UserRole.IT_MANAGER))
		self.assertTrue(self.has_permission(IsManagerOrAdmin, UserRole.ADMIN))
		self.assertFalse(self.has_permission(IsManagerOrAdmin, UserRole.TECHNICIAN))

	def test_admin_permission_is_limited_to_admin_role(self):
		self.assertTrue(self.has_permission(IsAdmin, UserRole.ADMIN))
		self.assertFalse(self.has_permission(IsAdmin, UserRole.IT_MANAGER))
