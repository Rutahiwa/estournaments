"""
Match Serializers

Handles serialization of Match objects for API responses.
Includes read-only serializers for viewing matches and input serializers for result reporting.
"""
from rest_framework import serializers
from .models import Match, MatchReport, LeagueStanding
from tournaments.models import Participant

class ParticipantBriefSerializer(serializers.Serializer):
    """
    Brief serializer for participants (used in match responses).
    Returns minimal user info to avoid deep nesting.
    """
    id = serializers.IntegerField()
    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        """Extract user info from participant."""
        u = obj.user
        return {
            'id': u.id,
            'username': getattr(u, 'username', None),
            'email': getattr(u, 'email', None)
        }


class MatchSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for Match objects.
    Includes nested participant and winner information.
    Used for GET endpoints.
    """
    participant_a = serializers.SerializerMethodField()
    participant_b = serializers.SerializerMethodField()
    winner = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = (
            'id', 'tournament', 'round_number', 'participant_a', 'participant_b',
            'scheduled_at', 'status', 'score_a', 'score_b', 'winner',
            'created_at', 'updated_at'
        )
        read_only_fields = fields

    def get_participant_a(self, obj):
        """Serialize participant_a with user info."""
        return ParticipantBriefSerializer(obj.participant_a).data if obj.participant_a else None

    def get_participant_b(self, obj):
        """Serialize participant_b with user info (can be None for byes)."""
        return ParticipantBriefSerializer(obj.participant_b).data if obj.participant_b else None

    def get_winner(self, obj):
        """Serialize winner with user info."""
        return ParticipantBriefSerializer(obj.winner).data if obj.winner else None


class ReportScoreSerializer(serializers.Serializer):
    """
    Input serializer for score reporting endpoint.
    Validates score inputs before processing.
    """
    score_a = serializers.IntegerField(
        min_value=0,
        help_text="Score for participant_a."
    )
    score_b = serializers.IntegerField(
        min_value=0,
        help_text="Score for participant_b."
    )


class MatchReportSerializer(serializers.ModelSerializer):
    """
    Serializer for MatchReport objects.
    Used for reporting match results and viewing report details.
    """
    reporter = serializers.SerializerMethodField()

    class Meta:
        model = MatchReport
        fields = (
            'id', 'match', 'reporter', 'score_a', 'score_b',
            'evidence', 'ip_address', 'user_agent', 'created_at'
        )
        read_only_fields = ('id', 'reporter', 'ip_address', 'user_agent', 'created_at')

    def get_reporter(self, obj):
        """Serialize reporter information."""
        u = obj.reporter
        return {
            'id': u.id,
            'username': getattr(u, 'username', None),
            'email': getattr(u, 'email', None)
        }


class BracketRoundSerializer(serializers.Serializer):
    """Serializer for a single round in bracket view."""
    round_number = serializers.IntegerField()
    round_name = serializers.CharField()
    matches = MatchSerializer(many=True)


class BracketSerializer(serializers.Serializer):
    """
    Serializer for tournament bracket structure.
    Returns all rounds and matches grouped for frontend visualization.
    """
    tournament_id = serializers.IntegerField()
    tournament_name = serializers.CharField()
    tournament_type = serializers.CharField()
    rounds = BracketRoundSerializer(many=True)


class LeagueStandingSerializer(serializers.ModelSerializer):
    """
    Serializer for individual league standings.
    Calculates and returns participant standings in the league.
    """
    position = serializers.SerializerMethodField()
    participant = serializers.SerializerMethodField()
    points = serializers.SerializerMethodField()
    goal_difference = serializers.SerializerMethodField()
    
    class Meta:
        model = LeagueStanding
        fields = ('position', 'participant', 'played', 'won', 'drew', 'lost', 'goals_for', 'goals_against', 'goal_difference', 'points')
        read_only_fields = fields
    
    def get_position(self, obj):
        """Get position by ordering by points desc, then goal_difference desc."""
        standings = LeagueStanding.objects.filter(tournament=obj.tournament).order_by('-points', '-goal_difference', '-goals_for')
        return list(standings.values_list('id', flat=True)).index(obj.id) + 1
    
    def get_participant(self, obj):
        """Serialize participant information."""
        return ParticipantBriefSerializer(obj.participant).data
    
    def get_points(self, obj):
        """Return the points of the league standing."""
        return obj.points
    
    def get_goal_difference(self, obj):
        """Return the goal difference of the league standing."""
        return obj.goal_difference


class LeagueStandingsSerializer(serializers.Serializer):
    """
    Serializer for tournament league standings.
    Returns all standings for a tournament, including final status flags.
    """
    tournament_id = serializers.IntegerField()
    tournament_name = serializers.CharField()
    tournament_type = serializers.CharField()
    standings = LeagueStandingSerializer(many=True)
    all_matches_completed = serializers.BooleanField()
    final_standings = serializers.BooleanField()