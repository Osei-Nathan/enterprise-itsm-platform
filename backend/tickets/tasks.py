from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import SlaMetric, Ticket, TicketEvent, TicketEventType


def _sla_candidates(warning_cutoff):
	response_due = Q(
		response_breached=False,
		first_response_due_at__isnull=False,
		first_response_due_at__lte=warning_cutoff,
	) & (
		Q(first_responded_at__isnull=True)
		| Q(first_responded_at__gt=F('first_response_due_at'))
	)
	resolution_due = Q(
		resolution_breached=False,
		resolution_due_at__isnull=False,
		resolution_due_at__lte=warning_cutoff,
	) & (
		Q(resolved_at__isnull=True)
		| Q(resolved_at__gt=F('resolution_due_at'))
	)
	return Ticket.objects.filter(response_due | resolution_due).order_by('pk')


def _record_sla_event(ticket, metric, event_type, details):
	_, created = TicketEvent.objects.get_or_create(
		ticket=ticket,
		event_type=event_type,
		sla_metric=metric,
		defaults={
			'from_status': ticket.status,
			'to_status': ticket.status,
			'details': details,
		},
	)
	return created


def _evaluate_metric(ticket, metric, due_at, completed_at, breach_field, now, warning_cutoff):
	if not due_at or getattr(ticket, breach_field):
		return 0, 0, False
	if completed_at and completed_at <= due_at:
		return 0, 0, False

	evaluation_time = completed_at or now
	if evaluation_time > due_at:
		event_type = TicketEventType.SLA_BREACHED
		details = f'{metric.label} target breached.'
		setattr(ticket, breach_field, True)
		breach_changed = True
		event_created_count = 'breach'
	elif due_at <= warning_cutoff:
		event_type = TicketEventType.SLA_WARNING
		details = f'{metric.label} target approaching.'
		breach_changed = False
		event_created_count = 'warning'
	else:
		return 0, 0, False

	event_created = _record_sla_event(ticket, metric, event_type, details)
	warning_count = int(event_created and event_created_count == 'warning')
	breach_count = int(event_created and event_created_count == 'breach')
	return warning_count, breach_count, breach_changed


@shared_task(name='tickets.tasks.check_sla_breaches')
def check_sla_breaches():
	now = timezone.now()
	warning_cutoff = now + timedelta(minutes=settings.SLA_WARNING_WINDOW_MINUTES)
	tickets_checked = 0
	warnings_created = 0
	breaches_created = 0

	with transaction.atomic():
		candidates = _sla_candidates(warning_cutoff).select_for_update(skip_locked=True)
		for ticket in candidates.iterator():
			tickets_checked += 1
			updates = []
			response_warnings, response_breaches, response_changed = _evaluate_metric(
				ticket,
				SlaMetric.FIRST_RESPONSE,
				ticket.first_response_due_at,
				ticket.first_responded_at,
				'response_breached',
				now,
				warning_cutoff,
			)
			resolution_warnings, resolution_breaches, resolution_changed = _evaluate_metric(
				ticket,
				SlaMetric.RESOLUTION,
				ticket.resolution_due_at,
				ticket.resolved_at,
				'resolution_breached',
				now,
				warning_cutoff,
			)
			warnings_created += response_warnings + resolution_warnings
			breaches_created += response_breaches + resolution_breaches
			if response_changed:
				updates.append('response_breached')
			if resolution_changed:
				updates.append('resolution_breached')
			if updates:
				ticket.save(update_fields=(*updates, 'updated_at'))

	return {
		'tickets_checked': tickets_checked,
		'warnings_created': warnings_created,
		'breaches_created': breaches_created,
	}