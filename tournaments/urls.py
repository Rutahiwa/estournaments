from django.urls import path
from .views import TournamentListCreateView, TournamentRetrieveUpdateDestroyView

urlpatterns = [
    # List all tournaments or create a new one
    path('', TournamentListCreateView.as_view(), name='tournament-list-create'),
    # Retrieve, update, delete a specific tournament by id
    path('<int:pk>/', TournamentRetrieveUpdateDestroyView.as_view(), name='tournament-detail'),
]