import uuid

from django.conf import settings
from django.db import models


def generate_ticket_number():
	return f'ITSM-{uuid.uuid4().hex[:12].upper()}'


class TicketCategory(models.Model):
	name = models.CharField(max_length=100, unique=True)
	description = models.TextField(blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name


class TicketPriority(models.TextChoices):
	CRITICAL = 'CRITICAL', 'Critical'
	HIGH = 'HIGH', 'High'
	MEDIUM = 'MEDIUM', 'Medium'
	LOW = 'LOW', 'Low'


class TicketStatus(models.TextChoices):
	OPEN = 'OPEN', 'Open'
	ASSIGNED = 'ASSIGNED', 'Assigned'
	IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
	PENDING = 'PENDING', 'Pending'
	RESOLVED = 'RESOLVED', 'Resolved'
	CLOSED = 'CLOSED', 'Closed'


class TicketEventType(models.TextChoices):
	ASSIGNED = 'ASSIGNED', 'Assigned'
	STARTED = 'STARTED', 'Started'
	PENDED = 'PENDED', 'Set Pending'
	RESUMED = 'RESUMED', 'Resumed'
	RESOLVED = 'RESOLVED', 'Resolved'
	CLOSED = 'CLOSED', 'Closed'
	REOPENED = 'REOPENED', 'Reopened'


class Ticket(models.Model):
	ticket_number = models.CharField(
		max_length=17,
		unique=True,
		default=generate_ticket_number,
		editable=False,
	)
	title = models.CharField(max_length=255)
	description = models.TextField()
	category = models.ForeignKey(
		TicketCategory,
		on_delete=models.SET_NULL,
		related_name='tickets',
		null=True,
		blank=True,
	)
	priority = models.CharField(
		max_length=20,
		choices=TicketPriority.choices,
		default=TicketPriority.MEDIUM,
	)
	status = models.CharField(
		max_length=20,
		choices=TicketStatus.choices,
		default=TicketStatus.OPEN,
	)
	requester = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.PROTECT,
		related_name='requested_tickets',
	)
	assignee = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		related_name='assigned_tickets',
		null=True,
		blank=True,
	)
	department = models.ForeignKey(
		'accounts.Department',
		on_delete=models.SET_NULL,
		related_name='tickets',
		null=True,
		blank=True,
	)
	pending_reason = models.TextField(blank=True)
	resolution_summary = models.TextField(blank=True)
	assigned_at = models.DateTimeField(null=True, blank=True)
	started_at = models.DateTimeField(null=True, blank=True)
	pending_at = models.DateTimeField(null=True, blank=True)
	resolved_at = models.DateTimeField(null=True, blank=True)
	closed_at = models.DateTimeField(null=True, blank=True)
	reopened_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('-created_at',)

	def __str__(self):
		return f'{self.ticket_number} - {self.title}'


class TicketEvent(models.Model):
	ticket = models.ForeignKey(
		Ticket,
		on_delete=models.CASCADE,
		related_name='events',
	)
	actor = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		related_name='ticket_events',
		null=True,
		blank=True,
	)
	assignee = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		related_name='ticket_assignment_events',
		null=True,
		blank=True,
	)
	event_type = models.CharField(max_length=20, choices=TicketEventType.choices)
	from_status = models.CharField(
		max_length=20,
		choices=TicketStatus.choices,
		blank=True,
	)
	to_status = models.CharField(
		max_length=20,
		choices=TicketStatus.choices,
		blank=True,
	)
	details = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('created_at', 'id')

	def __str__(self):
		return f'{self.ticket.ticket_number}: {self.get_event_type_display()}'
