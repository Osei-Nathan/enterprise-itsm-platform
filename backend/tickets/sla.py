from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import SlaPolicy, Ticket, TicketEvent, TicketEventType


def calculate_sla_deadlines(started_at, policy):
	return (
		started_at + policy.response_target,
		started_at + policy.resolution_target,
	)


def _active_policy_for(priority):
	try:
		return SlaPolicy.objects.get(priority=priority, is_active=True)
	except SlaPolicy.DoesNotExist as error:
		raise ValidationError({
			'priority': f'No active SLA policy exists for {priority} priority.'
		}) from error


def _record_breach(ticket, actor, metric):
	TicketEvent.objects.create(
		ticket=ticket,
		actor=actor,
		event_type=TicketEventType.SLA_BREACHED,
		from_status=ticket.status,
		to_status=ticket.status,
		details=f'{metric} target breached.',
	)


@transaction.atomic
def evaluate_sla_breaches(ticket, at=None, actor=None):
	at = at or timezone.now()
	new_breaches = []
	updates = []

	if ticket.first_response_due_at and not ticket.response_breached:
		response_time = ticket.first_responded_at or at
		if response_time > ticket.first_response_due_at:
			ticket.response_breached = True
			updates.append('response_breached')
			new_breaches.append('First response')

	if ticket.resolution_due_at and not ticket.resolution_breached:
		resolution_time = ticket.resolved_at or at
		if resolution_time > ticket.resolution_due_at:
			ticket.resolution_breached = True
			updates.append('resolution_breached')
			new_breaches.append('Resolution')

	if updates:
		ticket.save(update_fields=(*updates, 'updated_at'))
		for metric in new_breaches:
			_record_breach(ticket, actor, metric)
	return new_breaches


@transaction.atomic
def apply_sla_policy(ticket, policy=None, at=None):
	policy = policy or _active_policy_for(ticket.priority)
	started_at = at or ticket.created_at or timezone.now()
	first_response_due_at, resolution_due_at = calculate_sla_deadlines(
		started_at,
		policy,
	)
	ticket.sla_policy = policy
	ticket.first_response_due_at = first_response_due_at
	ticket.resolution_due_at = resolution_due_at
	ticket.save(update_fields=(
		'sla_policy',
		'first_response_due_at',
		'resolution_due_at',
		'updated_at',
	))
	evaluate_sla_breaches(ticket)
	return ticket


@transaction.atomic
def create_ticket(validated_data):
	requester = validated_data['requester']
	ticket = Ticket.objects.create(
		**validated_data,
		department=requester.department,
	)
	apply_sla_policy(ticket, at=ticket.created_at)
	TicketEvent.objects.create(
		ticket=ticket,
		actor=requester,
		event_type=TicketEventType.TICKET_CREATED,
		from_status='',
		to_status=ticket.status,
	)
	return ticket


@transaction.atomic
def update_ticket(ticket, validated_data):
	priority_changed = (
		'priority' in validated_data
		and validated_data['priority'] != ticket.priority
	)
	for field, value in validated_data.items():
		setattr(ticket, field, value)
	ticket.save()
	if priority_changed:
		apply_sla_policy(ticket, at=ticket.created_at)
	return ticket


@transaction.atomic
def record_first_response(ticket, actor, responded_at=None):
	if ticket.first_responded_at:
		raise ValidationError({'first_responded_at': 'First response is already recorded.'})
	if not ticket.first_response_due_at:
		apply_sla_policy(ticket)

	ticket.first_responded_at = responded_at or timezone.now()
	ticket.save(update_fields=('first_responded_at', 'updated_at'))
	TicketEvent.objects.create(
		ticket=ticket,
		actor=actor,
		event_type=TicketEventType.FIRST_RESPONSE,
		from_status=ticket.status,
		to_status=ticket.status,
	)
	evaluate_sla_breaches(ticket, at=ticket.first_responded_at, actor=actor)
	return ticket