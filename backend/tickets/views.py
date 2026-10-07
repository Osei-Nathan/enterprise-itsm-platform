from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserRole
from accounts.permissions import IsITStaff

from .models import Ticket
from .permissions import CanCreateTicket
from .serializers import TicketSerializer
from .workflow import perform_ticket_action


def tickets_visible_to(user):
	queryset = Ticket.objects.select_related(
		'assignee',
		'category',
		'department',
		'requester',
	)

	if not user.is_authenticated:
		return queryset.none()
	if user.is_superuser or user.role == UserRole.ADMIN:
		return queryset
	if user.role == UserRole.EMPLOYEE:
		return queryset.filter(requester=user)
	if user.role == UserRole.TECHNICIAN:
		return queryset.filter(assignee=user)
	if user.role == UserRole.IT_MANAGER:
		department_scope = Q(department__manager=user)
		if user.department_id:
			department_scope |= Q(department_id=user.department_id)
		return queryset.filter(department_scope).distinct()

	return queryset.none()


class TicketListCreateView(ListCreateAPIView):
	serializer_class = TicketSerializer

	def get_queryset(self):
		return tickets_visible_to(self.request.user)

	def get_permissions(self):
		if self.request.method == 'POST':
			return [CanCreateTicket()]
		return [IsAuthenticated()]


class TicketDetailView(RetrieveUpdateAPIView):
	serializer_class = TicketSerializer
	http_method_names = ('get', 'patch', 'head', 'options')

	def get_queryset(self):
		return tickets_visible_to(self.request.user)

	def get_permissions(self):
		if self.request.method == 'PATCH':
			return [IsITStaff()]
		return [IsAuthenticated()]


class TicketActionView(APIView):
	permission_classes = [IsAuthenticated]
	action = None

	def post(self, request, pk):
		ticket = get_object_or_404(tickets_visible_to(request.user), pk=pk)
		ticket = perform_ticket_action(self.action, ticket, request.user, request.data)
		return Response(TicketSerializer(ticket).data)