from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import UserRole

from .models import TicketEvent, TicketEventType, TicketStatus
from .serializers import (
	AssignTicketSerializer,
	PendingTicketSerializer,
	ResolveTicketSerializer,
)


def can_manage_ticket(user, ticket):
	if user.is_superuser or user.role == UserRole.ADMIN:
		return True
	if user.role != UserRole.IT_MANAGER or not ticket.department_id:
		return False
	return (
		ticket.department.manager_id == user.id
		or user.department_id == ticket.department_id
	)


def _require_work_access(user, ticket, allow_requester=False):
	if (
		user == ticket.assignee
		or can_manage_ticket(user, ticket)
		or (allow_requester and user == ticket.requester)
	):
		return
	raise PermissionDenied('You are not authorized to perform this ticket action.')


def _record_event(ticket, actor, event_type, from_status, details='', assignee=None):
	return TicketEvent.objects.create(
		ticket=ticket,
		actor=actor,
		assignee=assignee,
		event_type=event_type,
		from_status=from_status,
		to_status=ticket.status,
		details=details,
	)


@transaction.atomic
def perform_ticket_action(action, ticket, actor, data):
	if action == 'assign':
		if not (actor.is_superuser or actor.role in (UserRole.IT_MANAGER, UserRole.ADMIN)):
			raise PermissionDenied('Only IT Managers and Admins can assign tickets.')
		if not can_manage_ticket(actor, ticket):
			raise PermissionDenied('You cannot assign tickets outside your department.')
		if ticket.status != TicketStatus.OPEN:
			raise ValidationError({'status': 'Only open tickets can be assigned.'})

		serializer = AssignTicketSerializer(
			data=data,
			context={'ticket': ticket},
		)
		serializer.is_valid(raise_exception=True)
		previous_status = ticket.status
		technician = serializer.validated_data['assignee']
		ticket.assignee = technician
		ticket.status = TicketStatus.ASSIGNED
		ticket.assigned_at = timezone.now()
		ticket.save(update_fields=('assignee', 'status', 'assigned_at', 'updated_at'))
		_record_event(
			ticket,
			actor,
			TicketEventType.ASSIGNED,
			previous_status,
			assignee=technician,
		)
		return ticket

	if action in ('start', 'pending', 'resolve', 'close', 'reopen'):
		_require_work_access(actor, ticket, allow_requester=action == 'reopen')

	previous_status = ticket.status
	new_status = None
	event_type = None
	details = ''
	now = timezone.now()

	if action == 'start':
		if previous_status == TicketStatus.ASSIGNED:
			new_status = TicketStatus.IN_PROGRESS
			event_type = TicketEventType.STARTED
		elif previous_status == TicketStatus.PENDING:
			new_status = TicketStatus.IN_PROGRESS
			event_type = TicketEventType.RESUMED
			ticket.pending_reason = ''
		else:
			raise ValidationError({'status': 'Only assigned or pending tickets can be started.'})
		ticket.started_at = now
	elif action == 'pending':
		if previous_status != TicketStatus.IN_PROGRESS:
			raise ValidationError({'status': 'Only in-progress tickets can be set pending.'})
		serializer = PendingTicketSerializer(data=data)
		serializer.is_valid(raise_exception=True)
		details = serializer.validated_data['reason']
		ticket.pending_reason = details
		ticket.pending_at = now
		new_status = TicketStatus.PENDING
		event_type = TicketEventType.PENDED
	elif action == 'resolve':
		if previous_status != TicketStatus.IN_PROGRESS:
			raise ValidationError({'status': 'Only in-progress tickets can be resolved.'})
		serializer = ResolveTicketSerializer(data=data)
		serializer.is_valid(raise_exception=True)
		details = serializer.validated_data['resolution_summary']
		ticket.resolution_summary = details
		ticket.resolved_at = now
		new_status = TicketStatus.RESOLVED
		event_type = TicketEventType.RESOLVED
	elif action == 'close':
		if previous_status != TicketStatus.RESOLVED:
			raise ValidationError({'status': 'Only resolved tickets can be closed.'})
		if not ticket.resolution_summary.strip():
			raise ValidationError({'resolution_summary': 'A resolution is required before closing.'})
		new_status = TicketStatus.CLOSED
		event_type = TicketEventType.CLOSED
		ticket.closed_at = now
		details = ticket.resolution_summary
	elif action == 'reopen':
		if previous_status != TicketStatus.RESOLVED:
			raise ValidationError({'status': 'Only resolved tickets can be reopened.'})
		new_status = TicketStatus.IN_PROGRESS
		event_type = TicketEventType.REOPENED
		details = ticket.resolution_summary
		ticket.resolution_summary = ''
		ticket.resolved_at = None
		ticket.reopened_at = now
	else:
		raise ValidationError({'action': 'Unknown ticket action.'})

	ticket.status = new_status
	ticket.save()
	_record_event(ticket, actor, event_type, previous_status, details=details)
	return ticket