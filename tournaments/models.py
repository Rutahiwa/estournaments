from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class Tournament(models.Model):
    """Tournament model with support for Cup (elimination) and League (round-robin) formats."""

    # Tournament types
    TOURNAMENT_TYPE_CUP = 'cup'
    TOURNAMENT_TYPE_LEAGUE = 'league'
    TOURNAMENT_TYPE_CHOICES = [
        (TOURNAMENT_TYPE_CUP, 'Cup (Single Elimination)'),
        (TOURNAMENT_TYPE_LEAGUE, 'League (Round-Robin)'),
    ]

    # Tournament status
    STATUS_DRAFT = 'draft'
    STATUS_REGISTRATION_OPEN = 'registration_open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_REGISTRATION_OPEN, 'Registration Open'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    # Fields
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    organizer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organized_tournaments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    tournament_type = models.CharField(
        max_length=10,
        choices=TOURNAMENT_TYPE_CHOICES,
        default=TOURNAMENT_TYPE_CUP,
        help_text="Cup: Single Elimination | League: Round-Robin"
    )
    max_players = models.PositiveIntegerField(default=2)  # Default to avoid NOT NULL errors
    registration_deadline = models.DateTimeField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_tournament_type_display()})"

    # --- New helper ---
    def is_registration_open(self):
        """Check if participants can still register."""
        now = timezone.now()
        return self.status == self.STATUS_REGISTRATION_OPEN and now <= self.registration_deadline and self.participants.count() < self.max_players


class Participant(models.Model):
    """Participant in a tournament."""
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tournament', 'user')
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.user.username} -> {self.tournament.name} ({self.tournament.get_tournament_type_display()})"
