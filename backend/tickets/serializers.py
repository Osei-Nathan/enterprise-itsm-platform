from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.models import UserRole

from .models import Ticket
from .sla import create_ticket, update_ticket

User = get_user_model()


class TicketSerializer(serializers.ModelSerializer):
	requester = serializers.HiddenField(default=serializers.CurrentUserDefault())

	class Meta:
		model = Ticket
		fields = (
			'id',
			'ticket_number',
			'title',
			'description',
			'category',
			'priority',
			'sla_policy',
			'status',
			'requester',
			'assignee',
			'department',
			'pending_reason',
			'resolution_summary',
			'assigned_at',
			'started_at',
			'pending_at',
			'resolved_at',
			'closed_at',
			'reopened_at',
			'first_response_due_at',
			'resolution_due_at',
			'first_responded_at',
			'response_breached',
			'resolution_breached',
			'created_at',
			'updated_at',
		)
		read_only_fields = (
			'id',
			'ticket_number',
			'sla_policy',
			'status',
			'assignee',
			'department',
			'pending_reason',
			'resolution_summary',
			'assigned_at',
			'started_at',
			'pending_at',
			'resolved_at',
			'closed_at',
			'reopened_at',
			'first_response_due_at',
			'resolution_due_at',
			'first_responded_at',
			'response_breached',
			'resolution_breached',
			'created_at',
			'updated_at',
		)

	def create(self, validated_data):
		return create_ticket(validated_data)

	def update(self, instance, validated_data):
		return update_ticket(instance, validated_data)


class AssignTicketSerializer(serializers.Serializer):
	assignee_id = serializers.PrimaryKeyRelatedField(
		source='assignee',
		queryset=User.objects.filter(role=UserRole.TECHNICIAN),
	)

	def validate_assignee_id(self, technician):
		ticket = self.context['ticket']
		if ticket.department_id and technician.department_id != ticket.department_id:
			raise serializers.ValidationError(
				'Technician must belong to the ticket department.'
			)
		return technician


class PendingTicketSerializer(serializers.Serializer):
	reason = serializers.CharField(trim_whitespace=True)

	def validate_reason(self, value):
		if not value:
			raise serializers.ValidationError('A pending reason is required.')
		return value


class ResolveTicketSerializer(serializers.Serializer):
	resolution_summary = serializers.CharField(trim_whitespace=True)

	def validate_resolution_summary(self, value):
		if not value:
			raise serializers.ValidationError('A resolution summary is required.')
		return value
