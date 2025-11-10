from rest_framework import serializers
from .models import Tournament
from django.contrib.auth import get_user_model

User = get_user_model()

class TournamentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = ('id','name','description','type','status','max_players','registration_deadline')

class TournamentSerializer(serializers.ModelSerializer):
    organizer = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = ('id','name','description','type','status','max_players','registration_deadline','organizer','created_at','updated_at')

    def get_organizer(self, obj):
        user = obj.organizer
        return {'id': user.id, 'username': getattr(user, 'username', None), 'email': getattr(user, 'email', None)}

# New participant serializers
from .models import Participant

class ParticipantSerializer(serializers.ModelSerializer):
    """Read-only representation of a tournament participant with basic user info."""
    user = serializers.SerializerMethodField()

    class Meta:
        model = Participant
        fields = ('id', 'user', 'joined_at')

    def get_user(self, obj):
        u = obj.user
        return {'id': u.id, 'username': getattr(u, 'username', None), 'email': getattr(u, 'email', None)}

class ParticipantCreateSerializer(serializers.Serializer):
    """Serializer for join requests (no extra fields required)."""
    # no fields — joining uses authenticated user
    def validate(self, attrs):
        # context must include 'tournament'
        tournament = self.context.get('tournament')
        if tournament is None:
            raise serializers.ValidationError("Tournament context required.")
        if not tournament.is_registration_open():
            raise serializers.ValidationError("Tournament registration is closed.")
        # capacity check
        current_count = tournament.participants.count()
        if current_count >= tournament.max_players:
            raise serializers.ValidationError("Tournament is full.")
        return attrs