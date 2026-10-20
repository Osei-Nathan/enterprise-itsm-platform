from django.db import migrations


def backfill_sla_event_metrics(apps, schema_editor):
	ticket_event_model = apps.get_model('tickets', 'TicketEvent')
	database = schema_editor.connection.alias
	legacy_events = ticket_event_model.objects.using(database).filter(
		event_type='SLA_BREACHED',
		sla_metric='',
	)

	for event in legacy_events.iterator():
		if event.details.startswith('First response'):
			event.sla_metric = 'FIRST_RESPONSE'
		elif event.details.startswith('Resolution'):
			event.sla_metric = 'RESOLUTION'
		else:
			continue
		event.save(using=database, update_fields=('sla_metric',))


class Migration(migrations.Migration):
	dependencies = [
		('tickets', '0004_ticketevent_sla_metric_and_more'),
	]

	operations = [
		migrations.RunPython(
			backfill_sla_event_metrics,
			migrations.RunPython.noop,
		),
	]