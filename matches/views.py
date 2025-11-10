"""
Match Views / API Endpoints

Provides REST endpoints for:
- Viewing matches in a tournament
- Starting tournament (generating bracket)
- Reporting match results
- Viewing bracket structure
- Managing match status and progression
"""
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.core.mail import send_mail
import logging

from .models import Match, MatchReport
from .serializers import MatchSerializer, ReportScoreSerializer, MatchReportSerializer, BracketSerializer
from tournaments.models import Tournament
from .bracket_generator import generate_single_elimination_bracket, generate_next_round

logger = logging.getLogger(__name__)

class MatchListView(generics.ListAPIView):
    """List matches for a tournament (public)."""
    serializer_class = MatchSerializer
    permission_classes = (permissions.AllowAny,)
    def get_queryset(self):
        t = get_object_or_404(Tournament, pk=self.kwargs['tournament_pk'])
        qs = Match.objects.filter(tournament=t).select_related('participant_a__user','participant_b__user','winner')
        round_q = self.request.query_params.get('round')
        status_q = self.request.query_params.get('status')
        if round_q:
            qs = qs.filter(round_number=round_q)
        if status_q:
            qs = qs.filter(status=status_q)
        return qs.order_by('round_number','id')

class MatchDetailView(generics.RetrieveAPIView):
    queryset = Match.objects.select_related('participant_a__user','participant_b__user','winner')
    serializer_class = MatchSerializer
    permission_classes = (permissions.AllowAny,)
    lookup_field = 'pk'

class StartTournamentView(APIView):
    """Organizer starts tournament and generates randomized bracket (Round 1)."""
    permission_classes = (permissions.IsAuthenticated,)
    def post(self, request, tournament_pk):
        t = get_object_or_404(Tournament, pk=tournament_pk)
        if t.organizer != request.user:
            return Response({"detail":"Only organizer can start the tournament."}, status=status.HTTP_403_FORBIDDEN)
        if t.status not in ['registration_open','draft']:
            return Response({"detail":f"Tournament status is '{t.status}'. Cannot start."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            matches = generate_single_elimination_bracket(t)
            t.status = 'in_progress'
            t.save()
            return Response({"detail":f"Generated {len(matches)} matches.","matches":MatchSerializer(matches,many=True).data}, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"detail":str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ReportScoreView(APIView):
    """
    Participant or organizer submits a MatchReport with optional evidence file.
    - if another report from a different user matches -> auto-complete match
    - if conflicting other reports -> mark disputed and notify organizer
    - otherwise record and wait for other player
    """
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
            return Response({"detail":"Not authorized to report score."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReportScoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        score_a = serializer.validated_data['score_a']
        score_b = serializer.validated_data['score_b']

        # Save MatchReport with optional evidence file
        report = MatchReport.objects.create(
            match=match,
            reporter=user,
            score_a=score_a,
            score_b=score_b,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT','')[:512],
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
            # attempt next-round generation
            try:
                current_round_matches = Match.objects.filter(tournament=m.tournament, round_number=m.round_number)
                if not current_round_matches.filter(status=Match.STATUS_PENDING).exists():
                    generate_next_round(m.tournament, m.round_number)
            except ValueError:
                pass
            return Response(MatchSerializer(m).data, status=status.HTTP_200_OK)

        if other_reports.exists() and not other_reports.filter(score_a=score_a, score_b=score_b).exists():
            match.status = Match.STATUS_DISPUTED
            match.save()
            # Notify organizer via email
            try:
                subject = f"Match {match.id} disputed in tournament '{match.tournament.name}'"
                message = (
                    f"Match {match.id} (Round {match.round_number}) has conflicting score reports.\n\n"
                    f"Tournament: {match.tournament.name}\n"
                    f"Participants: {match.participant_a.user.username} vs {match.participant_b.user.username if match.participant_b else 'BYE'}\n\n"
                    f"Reports:\n"
                )
                for r in MatchReport.objects.filter(match=match):
                    message += f"- {r.reporter.username}: {r.score_a}-{r.score_b} (at {r.created_at})\n"
                message += f"\nPlease resolve this dispute at: /api/matches/{match.id}/resolve/"
                
                send_mail(
                    subject,
                    message,
                    None,  # uses DEFAULT_FROM_EMAIL
                    [match.tournament.organizer.email],
                    fail_silently=False  # raise exception if email fails
                )
            except Exception as e:
                logger.error(f"Failed to send dispute notification email: {e}")
                # Don't fail the request; just log the error
            
            return Response({"detail":"Report recorded — conflict detected. Organizer will resolve."}, status=status.HTTP_202_ACCEPTED)

        return Response({"detail":"Report recorded. Waiting for the other player's report."}, status=status.HTTP_202_ACCEPTED)


class OrganizerResolveView(APIView):
    """
    Organizer resolves a disputed match. Provide accept_report_id or score_a & score_b.
    Resolution is recorded as a MatchReport for auditing.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, match_pk):
        match = get_object_or_404(Match, pk=match_pk)
        if match.tournament.organizer_id != request.user.id:
            return Response({"detail":"Only the organizer may resolve disputes."}, status=status.HTTP_403_FORBIDDEN)

        accept_report_id = request.data.get('accept_report_id')
        if accept_report_id:
            report = get_object_or_404(MatchReport, pk=accept_report_id, match=match)
            score_a, score_b = report.score_a, report.score_b
        else:
            score_a = request.data.get('score_a')
            score_b = request.data.get('score_b')
            if score_a is None or score_b is None:
                return Response({"detail":"Provide 'accept_report_id' or both 'score_a' and 'score_b'."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                score_a = int(score_a); score_b = int(score_b)
            except (ValueError, TypeError):
                return Response({"detail":"Scores must be integers."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            m = Match.objects.select_for_update().get(pk=match.pk)
            if m.status == Match.STATUS_COMPLETED:
                return Response({"detail":"Match already completed."}, status=status.HTTP_400_BAD_REQUEST)
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

        MatchReport.objects.create(
            match=m,
            reporter=request.user,
            score_a=score_a,
            score_b=score_b,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT','')[:512]
        )

        try:
            current_round_matches = Match.objects.filter(tournament=m.tournament, round_number=m.round_number)
            if not current_round_matches.filter(status=Match.STATUS_PENDING).exists():
                generate_next_round(m.tournament, m.round_number)
        except ValueError:
            pass

        return Response(MatchSerializer(m).data, status=status.HTTP_200_OK)


class BracketView(APIView):
    """Return bracket structure grouped by rounds (public)."""
    permission_classes = (permissions.AllowAny,)
    def get(self, request, tournament_pk):
        t = get_object_or_404(Tournament, pk=tournament_pk)
        matches = Match.objects.filter(tournament=t).select_related('participant_a__user','participant_b__user','winner').order_by('round_number','id')
        if not matches.exists():
            return Response({"tournament_id": t.id, "tournament_name": t.name, "rounds": []}, status=status.HTTP_200_OK)
        rounds = {}
        for m in matches:
            rounds.setdefault(m.round_number, []).append(m)
        data = {"tournament_id": t.id, "tournament_name": t.name, "rounds": []}
        for rn in sorted(rounds.keys()):
            data["rounds"].append({"round_number": rn, "matches": MatchSerializer(rounds[rn], many=True).data})
        return Response(data, status=status.HTTP_200_OK)
