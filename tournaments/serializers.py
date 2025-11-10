from rest_framework import serializers
from .models import Tournament
from .enums import TournamentType, TournamentStatus
from django.utils import timezone

# Serializer for creating/updating tournaments (validates sensible fields)
class TournamentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = ('id','name','description','type','status','max_players','registration_deadline')

    def validate_max_players(self, value):
        if value < 2:
            raise serializers.ValidationError("max_players must be at least 2.")
        return value

    def validate_registration_deadline(self, value):
        if value and value <= timezone.now():
            raise serializers.ValidationError("registration_deadline must be in the future.")
        return value

# Read serializer for returning tournament data including organizer info
class TournamentSerializer(serializers.ModelSerializer):
    organizer = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = ('id','name','description','type','status','max_players','registration_deadline','organizer','created_at','updated_at')

    def get_organizer(self, obj):
        user = obj.organizer
        return {'id': user.id, 'username': getattr(user, 'username', None), 'email': getattr(user, 'email', None)}