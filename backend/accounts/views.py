from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListCreateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Department
from .permissions import IsManagerOrAdmin
from .serializers import DepartmentSerializer


class CurrentUserView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		user = request.user
		department = user.department
		return Response({
			'id': user.id,
			'username': user.username,
			'email': user.email,
			'first_name': user.first_name,
			'last_name': user.last_name,
			'phone': user.phone,
			'role': user.role,
			'department': {
				'id': department.id,
				'name': department.name,
			} if department else None,
		})


class DepartmentListCreateView(ListCreateAPIView):
	queryset = Department.objects.order_by('name')
	serializer_class = DepartmentSerializer

	def get_permissions(self):
		if self.request.method == 'POST':
			return [IsManagerOrAdmin()]
		return [IsAuthenticated()]
