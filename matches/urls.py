"""
URL Configuration for Matches App

Routes for:
- Viewing matches in a tournament
- Starting/generating bracket
- Reporting match results
- Viewing bracket structure
"""
from django.urls import path
from .views import (
    MatchListView,
    MatchDetailView,
    StartTournamentView,
    ReportScoreView,
    OrganizerResolveView,
    BracketView,
    LeagueStandingsView,
)

urlpatterns = [
    # Match endpoints
    path('tournaments/<int:tournament_pk>/matches/', MatchListView.as_view(), name='match-list'),
    path('matches/<int:pk>/', MatchDetailView.as_view(), name='match-detail'),
    
    # Tournament control (organizer)
    path('tournaments/<int:tournament_pk>/start/', StartTournamentView.as_view(), name='tournament-start'),
    
    # Score reporting (participants/organizer)
    path('matches/<int:match_pk>/report-score/', ReportScoreView.as_view(), name='match-report-score'),
    
    # Organizer resolve match
    path('matches/<int:match_pk>/resolve/', OrganizerResolveView.as_view(), name='match-resolve'),
    
    # Bracket visualization
    path('tournaments/<int:tournament_pk>/bracket/', BracketView.as_view(), name='tournament-bracket'),
    
    # League standings
    path('tournaments/<int:tournament_pk>/standings/', LeagueStandingsView.as_view(), name='tournament-standings'),
]