from rest_framework import serializers

from .models import Department


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ('id', 'name', 'description', 'manager', 'created_at', 'updated_at')
        read_only_fields = ('created_at', 'updated_at')
