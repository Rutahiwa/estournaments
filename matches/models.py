"""
Match Models

Defines the Match model which represents a single fixture/game in a tournament.
Tracks participants, scores, status, and winner determination.
Supports single-elimination tournament progression.
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
from tournaments.models import Tournament, Participant

class Match(models.Model):
    """
    Match model represents a single game/fixture in a tournament.
    
    A match links two participants (players) from the same tournament,
    stores their scores, and tracks the match status and winner.
    
    Supports round-based progression (single-elimination).
    """
    
    # Match status constants
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_DISPUTED = 'disputed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_DISPUTED, 'Disputed'),
    ]

    # Foreign keys linking match to tournament and participants
    tournament = models.ForeignKey(
        Tournament,
        on_delete=models.CASCADE,
        related_name='matches',
        help_text="The tournament this match belongs to."
    )
    participant_a = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='matches_as_a',
        help_text="First participant (player) in the match."
    )
    participant_b = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='matches_as_b',
        null=True,
        blank=True,
        help_text="Second participant (player) in the match. Can be null for byes."
    )

    # Match metadata
    round_number = models.PositiveIntegerField(
        default=1,
        help_text="Round number in the tournament bracket (1=first round, 2=semifinals, etc.)."
    )
    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional scheduled time for the match."
    )

    # Match status and scoring
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text="Current status of the match."
    )
    score_a = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Goals/score for participant_a. Set when match is completed."
    )
    score_b = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Goals/score for participant_b. Set when match is completed."
    )
    winner = models.ForeignKey(
        Participant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='matches_won',
        help_text="The winning participant. Auto-determined when scores are reported."
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['round_number', 'id']
        constraints = [
            # Prevent a participant from playing against themselves
            models.CheckConstraint(
                check=~models.Q(participant_a=models.F('participant_b')),
                name='no_self_match'
            )
        ]

    def __str__(self):
        return f"Match {self.pk} - {self.tournament.name} (R{self.round_number})"

    def is_bye(self):
        """Check if this is a bye match (participant_b is None)."""
        return self.participant_b is None

    def can_report_result(self):
        """Check if the match is in a state where results can be reported."""
        return self.status in [self.STATUS_PENDING, self.STATUS_IN_PROGRESS, self.STATUS_DISPUTED]

    def auto_advance_bye_winner(self):
        """
        If this is a bye match (only participant_a), auto-complete it.
        participant_a advances automatically.
        """
        if self.is_bye() and self.status != self.STATUS_COMPLETED:
            self.status = self.STATUS_COMPLETED
            self.winner = self.participant_a
            self.score_a = 1
            self.score_b = 0
            self.save()


class MatchReport(models.Model):
    """
    Immutable record of a single user's score report for a match.
    Used to implement dual-report verification.
    """
    match = models.ForeignKey('matches.Match', on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    score_a = models.PositiveIntegerField()
    score_b = models.PositiveIntegerField()
    evidence = models.FileField(upload_to='match_evidence/', null=True, blank=True)
    ip_address = models.CharField(max_length=45, null=True, blank=True)
    user_agent = models.CharField(max_length=512, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['match', 'reporter', 'score_a', 'score_b'], name='unique_report_per_user_same_scores')
        ]

    def __str__(self):
        return f"Report {self.pk} for Match {self.match_id} by {self.reporter_id}"
