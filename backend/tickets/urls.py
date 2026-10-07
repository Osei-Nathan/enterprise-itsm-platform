from django.urls import path

from .views import TicketActionView, TicketDetailView, TicketListCreateView


app_name = 'tickets'

urlpatterns = [
	path('', TicketListCreateView.as_view(), name='ticket-list'),
	path('<int:pk>/', TicketDetailView.as_view(), name='ticket-detail'),
	path('<int:pk>/assign/', TicketActionView.as_view(action='assign'), name='ticket-assign'),
	path('<int:pk>/start/', TicketActionView.as_view(action='start'), name='ticket-start'),
	path('<int:pk>/pending/', TicketActionView.as_view(action='pending'), name='ticket-pending'),
	path('<int:pk>/resolve/', TicketActionView.as_view(action='resolve'), name='ticket-resolve'),
	path('<int:pk>/close/', TicketActionView.as_view(action='close'), name='ticket-close'),
	path('<int:pk>/reopen/', TicketActionView.as_view(action='reopen'), name='ticket-reopen'),
]