from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import Tournament
from .serializers import TournamentSerializer, TournamentCreateSerializer
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