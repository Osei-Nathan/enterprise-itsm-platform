from datetime import timedelta

from django.test import TestCase
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework.test import APIRequestFactory, APITestCase

from accounts.models import Department, User, UserRole

from .models import (
	Ticket,
	TicketCategory,
	TicketEventType,
	TicketPriority,
	SlaPolicy,
	TicketStatus,
)
from .serializers import TicketSerializer
from .sla import (
	calculate_sla_deadlines,
	create_ticket,
	evaluate_sla_breaches,
	record_first_response,
)


class TicketModelTests(TestCase):
	def setUp(self):
		self.requester = User.objects.create_user(
			username='requester',
			password='local-test-password',
			role=UserRole.EMPLOYEE,
		)
		self.assignee = User.objects.create_user(
			username='technician',
			password='local-test-password',
			role=UserRole.TECHNICIAN,
		)
		self.department = Department.objects.create(name='IT')
		self.category = TicketCategory.objects.create(name='Hardware')

	def test_ticket_generates_number_and_defaults_to_open_medium(self):
		ticket = Ticket.objects.create(
			title='Laptop issue',
			description='Laptop will not start.',
			requester=self.requester,
		)
		another_ticket = Ticket.objects.create(
			title='Monitor issue',
			description='Monitor is blank.',
			requester=self.requester,
		)

		self.assertTrue(ticket.ticket_number.startswith('ITSM-'))
		self.assertNotEqual(ticket.ticket_number, another_ticket.ticket_number)
		self.assertEqual(ticket.status, TicketStatus.OPEN)
		self.assertEqual(ticket.priority, TicketPriority.MEDIUM)
		self.assertIsNotNone(ticket.created_at)
		self.assertIsNotNone(ticket.updated_at)

	def test_ticket_stores_its_domain_relationships(self):
		ticket = Ticket.objects.create(
			title='Laptop issue',
			description='Laptop will not start.',
			requester=self.requester,
			assignee=self.assignee,
			department=self.department,
			category=self.category,
			priority=TicketPriority.HIGH,
			status=TicketStatus.ASSIGNED,
		)

		self.assertEqual(ticket.requester, self.requester)
		self.assertEqual(ticket.assignee, self.assignee)
		self.assertEqual(ticket.department, self.department)
		self.assertEqual(ticket.category, self.category)
		self.assertEqual(ticket.priority, TicketPriority.HIGH)
		self.assertEqual(ticket.status, TicketStatus.ASSIGNED)
		self.assertIn(ticket.ticket_number, str(ticket))

	def test_optional_relationships_are_cleared_when_related_records_are_deleted(self):
		ticket = Ticket.objects.create(
			title='Laptop issue',
			description='Laptop will not start.',
			requester=self.requester,
			assignee=self.assignee,
			department=self.department,
			category=self.category,
		)

		self.assignee.delete()
		self.department.delete()
		self.category.delete()
		ticket.refresh_from_db()

		self.assertIsNone(ticket.assignee)
		self.assertIsNone(ticket.department)
		self.assertIsNone(ticket.category)

	def test_requester_cannot_be_deleted_while_ticket_exists(self):
		Ticket.objects.create(
			title='Laptop issue',
			description='Laptop will not start.',
			requester=self.requester,
		)

		with self.assertRaises(ProtectedError):
			self.requester.delete()


class TicketSerializerTests(TestCase):
	def setUp(self):
		self.department = Department.objects.create(name='Finance')
		self.requester = User.objects.create_user(
			username='employee',
			password='local-test-password',
			role=UserRole.EMPLOYEE,
			department=self.department,
		)
		self.other_user = User.objects.create_user(
			username='other-user',
			password='local-test-password',
			role=UserRole.TECHNICIAN,
		)
		self.other_department = Department.objects.create(name='IT')
		self.category = TicketCategory.objects.create(name='Hardware')
		self.request = APIRequestFactory().post('/api/tickets/')
		self.request.user = self.requester

	def test_employee_can_submit_only_ticket_content_fields(self):
		serializer = TicketSerializer(
			data={
				'title': 'Laptop issue',
				'description': 'Laptop will not start.',
				'category': self.category.id,
				'priority': TicketPriority.HIGH,
			},
			context={'request': self.request},
		)

		self.assertTrue(serializer.is_valid(), serializer.errors)
		ticket = serializer.save()

		self.assertEqual(ticket.title, 'Laptop issue')
		self.assertEqual(ticket.description, 'Laptop will not start.')
		self.assertEqual(ticket.category, self.category)
		self.assertEqual(ticket.priority, TicketPriority.HIGH)
		self.assertEqual(ticket.requester, self.requester)
		self.assertEqual(ticket.department, self.department)

	def test_client_cannot_override_backend_controlled_fields(self):
		serializer = TicketSerializer(
			data={
				'title': 'Laptop issue',
				'description': 'Laptop will not start.',
				'category': self.category.id,
				'priority': TicketPriority.HIGH,
				'ticket_number': 'CLIENT-CONTROLLED',
				'status': TicketStatus.CLOSED,
				'requester': self.other_user.id,
				'assignee': self.other_user.id,
				'department': self.other_department.id,
				'created_at': '2000-01-01T00:00:00Z',
				'updated_at': '2000-01-01T00:00:00Z',
			},
			context={'request': self.request},
		)

		self.assertTrue(serializer.is_valid(), serializer.errors)
		ticket = serializer.save()

		self.assertNotEqual(ticket.ticket_number, 'CLIENT-CONTROLLED')
		self.assertEqual(ticket.status, TicketStatus.OPEN)
		self.assertEqual(ticket.requester, self.requester)
		self.assertIsNone(ticket.assignee)
		self.assertEqual(ticket.department, self.department)


class SlaServiceTests(TestCase):
	def setUp(self):
		self.department = Department.objects.create(name='Service Desk')
		self.requester = User.objects.create_user(
			username='sla-requester',
			password='local-test-password',
			role=UserRole.EMPLOYEE,
			department=self.department,
		)
		self.technician = User.objects.create_user(
			username='sla-technician',
			password='local-test-password',
			role=UserRole.TECHNICIAN,
			department=self.department,
		)

	def make_ticket(self, priority=TicketPriority.MEDIUM):
		return create_ticket({
			'requester': self.requester,
			'title': f'{priority} SLA test',
			'description': 'SLA test ticket.',
			'priority': priority,
		})

	def test_seeded_policy_targets_match_project_defaults(self):
		expected = {
			TicketPriority.CRITICAL: (timedelta(minutes=15), timedelta(hours=4)),
			TicketPriority.HIGH: (timedelta(minutes=30), timedelta(hours=8)),
			TicketPriority.MEDIUM: (timedelta(hours=2), timedelta(hours=24)),
			TicketPriority.LOW: (timedelta(hours=4), timedelta(hours=72)),
		}

		for priority, targets in expected.items():
			with self.subTest(priority=priority):
				policy = SlaPolicy.objects.get(priority=priority, is_active=True)
				self.assertEqual((policy.response_target, policy.resolution_target), targets)

	def test_deadline_calculation_uses_elapsed_duration_targets(self):
		policy = SlaPolicy.objects.get(priority=TicketPriority.CRITICAL)
		started_at = timezone.now()

		response_due_at, resolution_due_at = calculate_sla_deadlines(started_at, policy)

		self.assertEqual(response_due_at, started_at + timedelta(minutes=15))
		self.assertEqual(resolution_due_at, started_at + timedelta(hours=4))

	def test_created_ticket_gets_priority_policy_and_deadlines(self):
		ticket = self.make_ticket(TicketPriority.HIGH)

		self.assertEqual(ticket.sla_policy.priority, TicketPriority.HIGH)
		self.assertEqual(
			ticket.first_response_due_at,
			ticket.created_at + timedelta(minutes=30),
		)
		self.assertEqual(
			ticket.resolution_due_at,
			ticket.created_at + timedelta(hours=8),
		)
		self.assertFalse(ticket.response_breached)
		self.assertFalse(ticket.resolution_breached)
		self.assertTrue(ticket.events.filter(event_type=TicketEventType.TICKET_CREATED).exists())

	def test_priority_change_recalculates_deadlines_from_original_creation(self):
		ticket = self.make_ticket(TicketPriority.LOW)
		priority_changed_at = ticket.created_at + timedelta(hours=1)
		serializer = TicketSerializer(
			ticket,
			data={'priority': TicketPriority.CRITICAL},
			partial=True,
		)
		self.assertTrue(serializer.is_valid(), serializer.errors)
		ticket = serializer.save()

		self.assertEqual(ticket.sla_policy.priority, TicketPriority.CRITICAL)
		self.assertEqual(
			ticket.first_response_due_at,
			ticket.created_at + timedelta(minutes=15),
		)
		self.assertNotEqual(ticket.first_response_due_at, priority_changed_at)

	def test_first_response_records_time_and_one_time_breach_event(self):
		ticket = self.make_ticket(TicketPriority.CRITICAL)
		responded_at = ticket.first_response_due_at + timedelta(seconds=1)

		record_first_response(ticket, self.technician, responded_at=responded_at)
		ticket.refresh_from_db()

		self.assertEqual(ticket.first_responded_at, responded_at)
		self.assertTrue(ticket.response_breached)
		self.assertEqual(
			ticket.events.filter(event_type=TicketEventType.FIRST_RESPONSE).count(),
			1,
		)
		self.assertEqual(
			ticket.events.filter(event_type=TicketEventType.SLA_BREACHED).count(),
			1,
		)
		self.assertEqual(evaluate_sla_breaches(ticket, at=responded_at), [])

	def test_resolution_breach_uses_existing_resolved_at_and_records_once(self):
		ticket = self.make_ticket(TicketPriority.CRITICAL)
		ticket.first_responded_at = ticket.first_response_due_at - timedelta(seconds=1)
		ticket.resolved_at = ticket.resolution_due_at + timedelta(seconds=1)
		ticket.status = TicketStatus.RESOLVED
		ticket.save()

		new_breaches = evaluate_sla_breaches(
			ticket,
			at=ticket.resolved_at,
			actor=self.technician,
		)
		ticket.refresh_from_db()

		self.assertEqual(new_breaches, ['Resolution'])
		self.assertFalse(ticket.response_breached)
		self.assertTrue(ticket.resolution_breached)
		event = ticket.events.get(event_type=TicketEventType.SLA_BREACHED)
		self.assertEqual(event.actor, self.technician)
		self.assertEqual(event.details, 'Resolution target breached.')



class TicketAPITests(APITestCase):
	def setUp(self):
		self.finance = Department.objects.create(name='Finance')
		self.it = Department.objects.create(name='IT')
		self.operations = Department.objects.create(name='Operations')

		self.employee = User.objects.create_user(
			username='employee',
			password='local-test-password',
			role=UserRole.EMPLOYEE,
			department=self.finance,
		)
		self.other_employee = User.objects.create_user(
			username='other-employee',
			password='local-test-password',
			role=UserRole.EMPLOYEE,
			department=self.finance,
		)
		self.technician = User.objects.create_user(
			username='technician',
			password='local-test-password',
			role=UserRole.TECHNICIAN,
			department=self.it,
		)
		self.other_technician = User.objects.create_user(
			username='other-technician',
			password='local-test-password',
			role=UserRole.TECHNICIAN,
		)
		self.manager = User.objects.create_user(
			username='manager',
			password='local-test-password',
			role=UserRole.IT_MANAGER,
			department=self.it,
		)
		self.it.manager = self.manager
		self.it.save(update_fields=['manager'])
		self.admin = User.objects.create_user(
			username='admin',
			password='local-test-password',
			role=UserRole.ADMIN,
		)
		self.category = TicketCategory.objects.create(name='Hardware')

		self.employee_ticket = self.make_ticket(
			requester=self.employee,
			department=self.finance,
		)
		self.colleague_ticket = self.make_ticket(
			requester=self.other_employee,
			department=self.finance,
		)
		self.assigned_ticket = self.make_ticket(
			requester=self.other_employee,
			assignee=self.technician,
			department=self.it,
			status=TicketStatus.ASSIGNED,
		)
		self.unassigned_it_ticket = self.make_ticket(
			requester=self.other_employee,
			department=self.it,
		)
		self.operations_ticket = self.make_ticket(
			requester=self.other_employee,
			department=self.operations,
		)

	def make_ticket(self, requester, **fields):
		return Ticket.objects.create(
			title='Existing ticket',
			description='Ticket created for API permission tests.',
			requester=requester,
			**fields,
		)

	def test_all_roles_can_create_tickets_with_backend_owned_fields(self):
		for user in (self.employee, self.technician, self.manager, self.admin):
			with self.subTest(role=user.role):
				self.client.force_authenticate(user=user)
				response = self.client.post('/api/tickets/', {
					'title': f'{user.username} request',
					'description': 'New ticket request.',
					'category': self.category.id,
					'priority': TicketPriority.HIGH,
					'status': TicketStatus.CLOSED,
					'assignee': self.other_technician.id,
				}, format='json')

				self.assertEqual(response.status_code, 201, response.data)
				created = Ticket.objects.get(ticket_number=response.data['ticket_number'])
				self.assertEqual(created.requester, user)
				self.assertEqual(created.department, user.department)
				self.assertEqual(created.priority, TicketPriority.HIGH)
				self.assertEqual(created.sla_policy.priority, TicketPriority.HIGH)
				self.assertIsNotNone(created.first_response_due_at)
				self.assertIsNotNone(created.resolution_due_at)
				self.assertEqual(created.status, TicketStatus.OPEN)
				self.assertIsNone(created.assignee)

	def test_employee_can_only_list_and_retrieve_own_tickets(self):
		self.client.force_authenticate(user=self.employee)

		response = self.client.get('/api/tickets/')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			{ticket['id'] for ticket in response.data},
			{self.employee_ticket.id},
		)
		self.assertEqual(
			self.client.get(f'/api/tickets/{self.employee_ticket.id}/').status_code,
			200,
		)
		self.assertEqual(
			self.client.get(f'/api/tickets/{self.colleague_ticket.id}/').status_code,
			404,
		)

	def test_technician_can_only_list_and_retrieve_assigned_tickets(self):
		self.client.force_authenticate(user=self.technician)

		response = self.client.get('/api/tickets/')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			{ticket['id'] for ticket in response.data},
			{self.assigned_ticket.id},
		)
		self.assertEqual(
			self.client.get(f'/api/tickets/{self.assigned_ticket.id}/').status_code,
			200,
		)
		self.assertEqual(
			self.client.get(f'/api/tickets/{self.unassigned_it_ticket.id}/').status_code,
			404,
		)

	def test_manager_can_only_list_tickets_in_managed_department(self):
		self.client.force_authenticate(user=self.manager)

		response = self.client.get('/api/tickets/')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			{ticket['id'] for ticket in response.data},
			{self.assigned_ticket.id, self.unassigned_it_ticket.id},
		)

	def test_admin_can_list_tickets_across_departments(self):
		self.client.force_authenticate(user=self.admin)

		response = self.client.get('/api/tickets/')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.data), 5)

	def test_employee_and_technician_cannot_patch_tickets(self):
		self.client.force_authenticate(user=self.employee)
		employee_response = self.client.patch(
			f'/api/tickets/{self.employee_ticket.id}/',
			{'priority': TicketPriority.CRITICAL},
			format='json',
		)
		self.assertEqual(employee_response.status_code, 403)

		self.client.force_authenticate(user=self.technician)
		unassigned_response = self.client.patch(
			f'/api/tickets/{self.unassigned_it_ticket.id}/',
			{'priority': TicketPriority.CRITICAL},
			format='json',
		)
		self.assertEqual(unassigned_response.status_code, 404)

	def test_employee_cannot_start_own_ticket(self):
		self.client.force_authenticate(user=self.employee)

		response = self.client.post(
			f'/api/tickets/{self.employee_ticket.id}/start/',
			{},
			format='json',
		)

		self.assertEqual(response.status_code, 403)

	def test_assigned_technician_can_adjust_priority(self):
		self.client.force_authenticate(user=self.technician)

		response = self.client.patch(
			f'/api/tickets/{self.assigned_ticket.id}/',
			{'priority': TicketPriority.CRITICAL},
			format='json',
		)

		self.assertEqual(response.status_code, 200, response.data)
		self.assigned_ticket.refresh_from_db()
		self.assertEqual(self.assigned_ticket.priority, TicketPriority.CRITICAL)
		self.assertEqual(self.assigned_ticket.status, TicketStatus.ASSIGNED)
		self.assertEqual(self.assigned_ticket.assignee, self.technician)

	def test_closing_requires_resolution_summary(self):
		self.assigned_ticket.status = TicketStatus.RESOLVED
		self.assigned_ticket.save()
		self.client.force_authenticate(user=self.technician)

		response = self.client.post(
			f'/api/tickets/{self.assigned_ticket.id}/close/',
			{},
			format='json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertFalse(
			self.assigned_ticket.events.filter(event_type=TicketEventType.CLOSED).exists()
		)

	def test_manager_can_patch_department_ticket_but_not_status_or_assignee(self):
		self.client.force_authenticate(user=self.manager)

		response = self.client.patch(
			f'/api/tickets/{self.assigned_ticket.id}/',
			{
				'title': 'Updated by manager',
				'priority': TicketPriority.HIGH,
				'status': TicketStatus.CLOSED,
				'assignee': self.other_technician.id,
			},
			format='json',
		)

		self.assertEqual(response.status_code, 200, response.data)
		self.assigned_ticket.refresh_from_db()
		self.assertEqual(self.assigned_ticket.title, 'Updated by manager')
		self.assertEqual(self.assigned_ticket.priority, TicketPriority.HIGH)
		self.assertEqual(self.assigned_ticket.sla_policy.priority, TicketPriority.HIGH)
		self.assertEqual(
			self.assigned_ticket.resolution_due_at,
			self.assigned_ticket.created_at + timedelta(hours=8),
		)
		self.assertEqual(self.assigned_ticket.status, TicketStatus.ASSIGNED)
		self.assertEqual(self.assigned_ticket.assignee, self.technician)

	def test_admin_can_patch_ticket_outside_their_department(self):
		self.client.force_authenticate(user=self.admin)

		response = self.client.patch(
			f'/api/tickets/{self.operations_ticket.id}/',
			{'title': 'Updated by admin'},
			format='json',
		)

		self.assertEqual(response.status_code, 200, response.data)
		self.operations_ticket.refresh_from_db()
		self.assertEqual(self.operations_ticket.title, 'Updated by admin')

	def test_manager_assignment_requires_technician_in_ticket_department(self):
		self.client.force_authenticate(user=self.employee)
		denied = self.client.post(
			f'/api/tickets/{self.employee_ticket.id}/assign/',
			{'assignee_id': self.technician.id},
			format='json',
		)
		self.assertEqual(denied.status_code, 403)

		self.client.force_authenticate(user=self.manager)
		wrong_role = self.client.post(
			f'/api/tickets/{self.unassigned_it_ticket.id}/assign/',
			{'assignee_id': self.employee.id},
			format='json',
		)
		wrong_department = self.client.post(
			f'/api/tickets/{self.unassigned_it_ticket.id}/assign/',
			{'assignee_id': self.other_technician.id},
			format='json',
		)

		self.assertEqual(wrong_role.status_code, 400)
		self.assertEqual(wrong_department.status_code, 400)

		assigned = self.client.post(
			f'/api/tickets/{self.unassigned_it_ticket.id}/assign/',
			{'assignee_id': self.technician.id},
			format='json',
		)

		self.assertEqual(assigned.status_code, 200, assigned.data)
		self.unassigned_it_ticket.refresh_from_db()
		self.assertEqual(self.unassigned_it_ticket.status, TicketStatus.ASSIGNED)
		self.assertEqual(self.unassigned_it_ticket.assignee, self.technician)
		self.assertIsNotNone(self.unassigned_it_ticket.assigned_at)
		event = self.unassigned_it_ticket.events.get()
		self.assertEqual(event.event_type, TicketEventType.ASSIGNED)
		self.assertEqual(event.actor, self.manager)
		self.assertEqual(event.assignee, self.technician)

	def test_assigned_ticket_cannot_be_reassigned_yet(self):
		self.client.force_authenticate(user=self.manager)

		response = self.client.post(
			f'/api/tickets/{self.assigned_ticket.id}/assign/',
			{'assignee_id': self.other_technician.id},
			format='json',
		)

		self.assertEqual(response.status_code, 400)
		self.assigned_ticket.refresh_from_db()
		self.assertEqual(self.assigned_ticket.assignee, self.technician)

	def test_assigned_ticket_can_follow_valid_workflow_and_be_audited(self):
		ticket = self.unassigned_it_ticket
		self.client.force_authenticate(user=self.manager)
		assigned = self.client.post(
			f'/api/tickets/{ticket.id}/assign/',
			{'assignee_id': self.technician.id},
			format='json',
		)
		self.assertEqual(assigned.status_code, 200, assigned.data)
		self.client.force_authenticate(user=self.technician)

		start = self.client.post(f'/api/tickets/{ticket.id}/start/', {}, format='json')
		self.assertEqual(start.status_code, 200, start.data)
		pending = self.client.post(
			f'/api/tickets/{ticket.id}/pending/',
			{'reason': 'Waiting for requester information.'},
			format='json',
		)
		self.assertEqual(pending.status_code, 200, pending.data)
		self.assertEqual(pending.data['pending_reason'], 'Waiting for requester information.')

		resumed = self.client.post(f'/api/tickets/{ticket.id}/start/', {}, format='json')
		self.assertEqual(resumed.status_code, 200, resumed.data)
		self.assertEqual(resumed.data['pending_reason'], '')
		resolved = self.client.post(
			f'/api/tickets/{ticket.id}/resolve/',
			{'resolution_summary': 'Replaced the faulty power adapter.'},
			format='json',
		)
		self.assertEqual(resolved.status_code, 200, resolved.data)
		closed = self.client.post(f'/api/tickets/{ticket.id}/close/', {}, format='json')
		self.assertEqual(closed.status_code, 200, closed.data)

		ticket.refresh_from_db()
		self.assertEqual(ticket.status, TicketStatus.CLOSED)
		self.assertEqual(ticket.resolution_summary, 'Replaced the faulty power adapter.')
		self.assertIsNotNone(ticket.assigned_at)
		self.assertIsNotNone(ticket.started_at)
		self.assertIsNotNone(ticket.first_responded_at)
		self.assertIsNotNone(ticket.pending_at)
		self.assertIsNotNone(ticket.resolved_at)
		self.assertIsNotNone(ticket.closed_at)
		self.assertEqual(
			list(ticket.events.values_list('event_type', flat=True)),
			[
				TicketEventType.ASSIGNED,
				TicketEventType.STARTED,
				TicketEventType.FIRST_RESPONSE,
				TicketEventType.PENDED,
				TicketEventType.RESUMED,
				TicketEventType.RESOLVED,
				TicketEventType.CLOSED,
			],
		)

	def test_transition_requires_reason_and_resolution_summary(self):
		self.client.force_authenticate(user=self.technician)
		pending = self.client.post(
			f'/api/tickets/{self.assigned_ticket.id}/pending/',
			{'reason': '   '},
			format='json',
		)
		self.assertEqual(pending.status_code, 400)

		self.client.post(f'/api/tickets/{self.assigned_ticket.id}/start/', {}, format='json')
		self.client.post(
			f'/api/tickets/{self.assigned_ticket.id}/pending/',
			{'reason': 'Waiting for approval.'},
			format='json',
		)
		self.client.post(f'/api/tickets/{self.assigned_ticket.id}/start/', {}, format='json')
		resolve = self.client.post(
			f'/api/tickets/{self.assigned_ticket.id}/resolve/',
			{'resolution_summary': '   '},
			format='json',
		)
		self.assertEqual(resolve.status_code, 400)

	def test_invalid_transition_is_rejected_and_closed_ticket_is_final(self):
		ticket = self.assigned_ticket
		ticket.status = TicketStatus.CLOSED
		ticket.save()
		self.client.force_authenticate(user=self.technician)
		invalid_start = self.client.post(
			f'/api/tickets/{ticket.id}/start/',
			{},
			format='json',
		)
		self.assertEqual(invalid_start.status_code, 400)

	def test_requester_can_reopen_resolved_ticket(self):
		ticket = self.employee_ticket
		ticket.status = TicketStatus.RESOLVED
		ticket.resolution_summary = 'Original resolution.'
		ticket.resolved_at = timezone.now()
		ticket.save()
		self.client.force_authenticate(user=self.employee)

		response = self.client.post(f'/api/tickets/{ticket.id}/reopen/', {}, format='json')

		self.assertEqual(response.status_code, 200, response.data)
		ticket.refresh_from_db()
		self.assertEqual(ticket.status, TicketStatus.IN_PROGRESS)
		self.assertEqual(ticket.resolution_summary, '')
		self.assertIsNone(ticket.resolved_at)
		self.assertIsNotNone(ticket.reopened_at)
		event = ticket.events.get()
		self.assertEqual(event.event_type, TicketEventType.REOPENED)
		self.assertEqual(event.details, 'Original resolution.')
