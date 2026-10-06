from django.test import TestCase

from .models import Department, User, UserRole


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
