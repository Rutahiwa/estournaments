"""
Match Views / API Endpoints

Provides REST endpoints for:
- Viewing matches in a tournament
- Starting tournament (generating bracket)
- Reporting match results
- Viewing bracket structure
- Managing match status and progression
"""
from django.shortcuts import get_object_or_404
from django.db import transaction, models
from django.db.models import F
from django.core.mail import send_mail
import logging

from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Match, MatchReport, LeagueStanding
from .serializers import (
    MatchSerializer, ReportScoreSerializer, MatchReportSerializer,
    BracketSerializer, LeagueStandingsSerializer
)
from tournaments.models import Tournament
from .bracket_generator import (
    generate_single_elimination_bracket, generate_league_matches, generate_next_round,
    get_round_name
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
#  Match listing and details
# ------------------------------------------------------------
class MatchListView(generics.ListAPIView):
    serializer_class = MatchSerializer
    permission_classes = (permissions.AllowAny,)

    def get_queryset(self):
        t = get_object_or_404(Tournament, pk=self.kwargs['tournament_pk'])
        qs = Match.objects.filter(tournament=t).select_related(
            'participant_a__user', 'participant_b__user', 'winner'
        )
        round_q = self.request.query_params.get('round')
        status_q = self.request.query_params.get('status')
        if round_q:
            qs = qs.filter(round_number=round_q)
        if status_q:
            qs = qs.filter(status=status_q)
        return qs.order_by('round_number', 'id')


class MatchDetailView(generics.RetrieveAPIView):
    queryset = Match.objects.select_related('participant_a__user', 'participant_b__user', 'winner')
    serializer_class = MatchSerializer
    permission_classes = (permissions.AllowAny,)
    lookup_field = 'pk'


# ------------------------------------------------------------
#  Starting tournament (cup or league)
# ------------------------------------------------------------
class StartTournamentView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, tournament_pk):
        t = get_object_or_404(Tournament, pk=tournament_pk)
        if t.organizer != request.user:
            return Response({"detail": "Only organizer can start the tournament."},
                            status=status.HTTP_403_FORBIDDEN)
        if t.status not in ['registration_open', 'draft']:
            return Response({"detail": f"Tournament status is '{t.status}'. Cannot start."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            if t.tournament_type == Tournament.TOURNAMENT_TYPE_CUP:
                matches = generate_single_elimination_bracket(t)
            else:
                matches = generate_league_matches(t)
            t.status = 'in_progress'
            t.save()
            return Response({
                "detail": f"Generated {len(matches)} matches.",
                "tournament_type": t.tournament_type,
                "matches": MatchSerializer(matches, many=True).data
            }, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ------------------------------------------------------------
#  Reporting scores
# ------------------------------------------------------------
class ReportScoreView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, match_pk):
        match = get_object_or_404(Match, pk=match_pk)
        user = request.user
        participant_user_ids = {match.participant_a.user_id}
        if match.participant_b:
            participant_user_ids.add(match.participant_b.user_id)

        is_organizer = match.tournament.organizer_id == user.id
        is_participant = user.id in participant_user_ids
        if not (is_organizer or is_participant):
            return Response({"detail": "Not authorized to report score."},
                            status=status.HTTP_403_FORBIDDEN)

        serializer = ReportScoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        score_a = serializer.validated_data['score_a']
        score_b = serializer.validated_data['score_b']

        MatchReport.objects.create(
            match=match,
            reporter=user,
            score_a=score_a,
            score_b=score_b,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:512],
            evidence=request.FILES.get('evidence') if 'evidence' in request.FILES else None
        )

        other_reports = MatchReport.objects.filter(match=match).exclude(reporter=user)
        matching_exists = other_reports.filter(score_a=score_a, score_b=score_b).exists()

        if matching_exists:
            with transaction.atomic():
                m = Match.objects.select_for_update().get(pk=match.pk)
                if m.status == Match.STATUS_COMPLETED:
                    return Response(MatchSerializer(m).data, status=status.HTTP_200_OK)

                m.score_a = score_a
                m.score_b = score_b
                if score_a > score_b:
                    m.winner = m.participant_a
                elif score_b > score_a:
                    m.winner = m.participant_b
                else:
                    m.winner = None
                m.status = Match.STATUS_COMPLETED
                m.save()

                # Update league standings
                if m.tournament.tournament_type == Tournament.TOURNAMENT_TYPE_LEAGUE:
                    standing_a = LeagueStanding.objects.get(
                        tournament=m.tournament, participant=m.participant_a)
                    standing_a.update_from_match(m)
                    if m.participant_b:
                        standing_b = LeagueStanding.objects.get(
                            tournament=m.tournament, participant=m.participant_b)
                        standing_b.update_from_match(m)

            # Generate next round for cups
            if match.tournament.tournament_type == Tournament.TOURNAMENT_TYPE_CUP:
                try:
                    current_round_matches = Match.objects.filter(
                        tournament=m.tournament, round_number=m.round_number)
                    if not current_round_matches.filter(status=Match.STATUS_PENDING).exists():
                        generate_next_round(m.tournament, m.round_number)
                except ValueError:
                    pass

            return Response(MatchSerializer(m).data, status=status.HTTP_200_OK)

        # Conflict handling
        if other_reports.exists():
            match.status = Match.STATUS_DISPUTED
            match.save()
            try:
                subject = f"Match {match.id} disputed in '{match.tournament.name}'"
                message = (
                    f"Conflict detected for Match {match.id}.\n\n"
                    f"Tournament: {match.tournament.name}\n"
                    f"Participants: {match.participant_a.user.username} vs "
                    f"{match.participant_b.user.username if match.participant_b else 'BYE'}\n"
                )
                for r in MatchReport.objects.filter(match=match):
                    message += f"- {r.reporter.username}: {r.score_a}-{r.score_b}\n"
                send_mail(subject, message, None,
                          [match.tournament.organizer.email], fail_silently=False)
            except Exception as e:
                logger.error(f"Failed to send dispute email: {e}")
            return Response({"detail": "Conflict detected — organizer notified."},
                            status=status.HTTP_202_ACCEPTED)

        return Response({"detail": "Report recorded. Waiting for other player's report."},
                        status=status.HTTP_202_ACCEPTED)


# ------------------------------------------------------------
#  Organizer dispute resolution
# ------------------------------------------------------------
class OrganizerResolveView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, match_pk):
        match = get_object_or_404(Match, pk=match_pk)
        if match.tournament.organizer_id != request.user.id:
            return Response({"detail": "Only organizer may resolve."},
                            status=status.HTTP_403_FORBIDDEN)

        score_a = request.data.get('score_a')
        score_b = request.data.get('score_b')
        if score_a is None or score_b is None:
            return Response({"detail": "Provide score_a and score_b."},
                            status=status.HTTP_400_BAD_REQUEST)
        score_a, score_b = int(score_a), int(score_b)

        with transaction.atomic():
            m = Match.objects.select_for_update().get(pk=match.pk)
            m.score_a = score_a
            m.score_b = score_b
            m.status = Match.STATUS_COMPLETED
            m.winner = None
            if score_a > score_b:
                m.winner = m.participant_a
            elif score_b > score_a:
                m.winner = m.participant_b
            m.save()

            if m.tournament.tournament_type == Tournament.TOURNAMENT_TYPE_LEAGUE:
                a = LeagueStanding.objects.get(tournament=m.tournament, participant=m.participant_a)
                a.update_from_match(m)
                if m.participant_b:
                    b = LeagueStanding.objects.get(tournament=m.tournament, participant=m.participant_b)
                    b.update_from_match(m)

        return Response(MatchSerializer(m).data, status=status.HTTP_200_OK)


# ------------------------------------------------------------
#  Bracket view (for cups)
# ------------------------------------------------------------
class BracketView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, tournament_pk):
        t = get_object_or_404(Tournament, pk=tournament_pk)
        if t.tournament_type != Tournament.TOURNAMENT_TYPE_CUP:
            return Response({"detail": "Bracket view is only for cup tournaments."},
                            status=status.HTTP_400_BAD_REQUEST)

        matches = Match.objects.filter(tournament=t).select_related(
            'participant_a__user', 'participant_b__user', 'winner'
        ).order_by('round_number', 'id')

        if not matches.exists():
            return Response({
                "tournament_id": t.id,
                "tournament_name": t.name,
                "tournament_type": t.tournament_type,
                "rounds": []
            }, status=status.HTTP_200_OK)

        rounds = {}
        max_round = matches.aggregate(models.Max('round_number'))['round_number__max'] or 1
        for m in matches:
            rounds.setdefault(m.round_number, []).append(m)

        data = {
            "tournament_id": t.id,
            "tournament_name": t.name,
            "tournament_type": t.tournament_type,
            "rounds": []
        }
        for rn in sorted(rounds.keys()):
            data["rounds"].append({
                "round_number": rn,
                "round_name": get_round_name(rn, max_round),
                "matches": MatchSerializer(rounds[rn], many=True).data
            })
        return Response(data, status=status.HTTP_200_OK)


# ------------------------------------------------------------
#  League standings (for leagues)
# ------------------------------------------------------------
class LeagueStandingsView(APIView):
    """Return league standings (LEAGUE ONLY)."""
    permission_classes = (permissions.AllowAny,)

    def get(self, request, tournament_pk):
        t = get_object_or_404(Tournament, pk=tournament_pk)
        if t.tournament_type != Tournament.TOURNAMENT_TYPE_LEAGUE:
            return Response({"detail": "Standings view is only for league tournaments."},
                            status=status.HTTP_400_BAD_REQUEST)

        standings = LeagueStanding.objects.filter(tournament=t).order_by(
            '-points', '-goal_difference', '-goals_for'
        )

        all_matches = Match.objects.filter(tournament=t)
        total_matches = all_matches.count()
        completed_matches = all_matches.filter(status=Match.STATUS_COMPLETED).count()
        all_completed = total_matches > 0 and completed_matches == total_matches

        data = {
            "tournament_id": t.id,
            "tournament_name": t.name,
            "tournament_type": t.tournament_type,
            "standings": [],
            "all_matches_completed": all_completed,
            "final_standings": all_completed
        }

        for position, standing in enumerate(standings, start=1):
            data["standings"].append({
                "position": position,
                "participant": {
                    "id": standing.participant.id,
                    "name": standing.participant.user.username,
                    "user_id": standing.participant.user_id
                },
                "played": standing.played,
                "won": standing.won,
                "drew": standing.drew,
                "lost": standing.lost,
                "goals_for": standing.goals_for,
                "goals_against": standing.goals_against,
                "goal_difference": standing.goal_difference,
                "points": standing.points
            })

        return Response(data, status=status.HTTP_200_OK)
