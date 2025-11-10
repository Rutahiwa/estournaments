from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import Tournament, Participant
from .serializers import TournamentSerializer, TournamentCreateSerializer, ParticipantSerializer, ParticipantCreateSerializer
from .permissions import IsOrganizerOrReadOnly

# List and create tournaments. Creation requires authentication.
class TournamentListCreateView(generics.ListCreateAPIView):
    """
    GET: list tournaments (public)
    POST: create a new tournament (authenticated user becomes organizer)
    """
    queryset = Tournament.objects.all()
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
    def get_serializer_class(self):
        return TournamentCreateSerializer if self.request.method == 'POST' else TournamentSerializer

    def perform_create(self, serializer):
        # Set the authenticated user as organizer on creation
        serializer.save(organizer=self.request.user)

# Retrieve, update, delete a tournament. Updates/deletes restricted to organizer.
class TournamentRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: retrieve tournament details
    PUT/PATCH: update tournament (only organizer)
    DELETE: remove tournament (only organizer)
    """
    queryset = Tournament.objects.all()
    permission_classes = (IsOrganizerOrReadOnly,)
    def get_serializer_class(self):
        # Use create/update serializer for write operations for validation
        if self.request.method in ('PUT', 'PATCH'):
            return TournamentCreateSerializer
        return TournamentSerializer

# New participant endpoints
class ParticipantListView(generics.ListAPIView):
    """List participants for a tournament (public read)."""
    serializer_class = ParticipantSerializer
    permission_classes = (permissions.AllowAny,)

    def get_queryset(self):
        tournament = get_object_or_404(Tournament, pk=self.kwargs['pk'])
        return tournament.participants.select_related('user').all()

class ParticipantJoinView(APIView):
    """Authenticated user can join a tournament if registration rules allow. Uses DB transaction to avoid race conditions."""
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk):
        # Validate basic rules first (deadline/status)
        tournament = get_object_or_404(Tournament, pk=pk)
        serializer = ParticipantCreateSerializer(data=request.data, context={'tournament': tournament})
        serializer.is_valid(raise_exception=True)

        # Use a DB transaction and lock the tournament row to safely check capacity
        with transaction.atomic():
            # lock this tournament row
            tournament = Tournament.objects.select_for_update().get(pk=tournament.pk)
            # re-check capacity
            current_count = tournament.participants.count()
            if current_count >= tournament.max_players:
                return Response({"detail": "Tournament is full."}, status=status.HTTP_400_BAD_REQUEST)
            # Prevent duplicate registration
            if Participant.objects.filter(tournament=tournament, user=request.user).exists():
                return Response({"detail": "User already registered for this tournament."}, status=status.HTTP_400_BAD_REQUEST)
            participant = Participant.objects.create(tournament=tournament, user=request.user)

        return Response(ParticipantSerializer(participant).data, status=status.HTTP_201_CREATED)

class ParticipantLeaveView(APIView):
    """Authenticated user can leave (unregister) a tournament they joined."""
    permission_classes = (permissions.IsAuthenticated,)

    def delete(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        participant = Participant.objects.filter(tournament=tournament, user=request.user).first()
        if not participant:
            return Response({"detail": "Not registered for this tournament."}, status=status.HTTP_404_NOT_FOUND)
        participant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)