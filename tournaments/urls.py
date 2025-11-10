from django.urls import path
from .views import TournamentListCreateView, TournamentRetrieveUpdateDestroyView
from .views import ParticipantListView, ParticipantJoinView, ParticipantLeaveView

urlpatterns = [
    # List all tournaments or create a new one
    path('', TournamentListCreateView.as_view(), name='tournament-list-create'),
    # Retrieve, update, delete a specific tournament by id
    path('<int:pk>/', TournamentRetrieveUpdateDestroyView.as_view(), name='tournament-detail'),

    # Participant endpoints
    path('<int:pk>/participants/', ParticipantListView.as_view(), name='tournament-participants'),
    path('<int:pk>/participants/join/', ParticipantJoinView.as_view(), name='tournament-join'),
    path('<int:pk>/participants/leave/', ParticipantLeaveView.as_view(), name='tournament-leave'),
]