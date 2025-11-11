"""
Match Models

Defines the Match model which represents a single fixture/game in a tournament.
Tracks participants, scores, status, and winner determination.
Supports single-elimination tournament progression and league standings.
"""

from django.db import models
from django.conf import settings
from tournaments.models import Tournament, Participant


class Match(models.Model):
    """Match model: links two Participants in a Tournament and stores round, scores, status, winner."""
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

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='matches')
    participant_a = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='matches_as_a')
    participant_b = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='matches_as_b', null=True, blank=True)
    round_number = models.PositiveIntegerField(default=1)
    scheduled_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    score_a = models.PositiveIntegerField(null=True, blank=True)
    score_b = models.PositiveIntegerField(null=True, blank=True)
    winner = models.ForeignKey(Participant, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches_won')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['round_number', 'id']
        constraints = [
            models.CheckConstraint(check=~models.Q(participant_a=models.F('participant_b')), name='no_self_match')
        ]

    def __str__(self):
        return f"Match {self.pk} - {self.tournament.name} (R{self.round_number})"

    def is_bye(self):
        return self.participant_b is None

    def can_report_result(self):
        return self.status in [self.STATUS_PENDING, self.STATUS_IN_PROGRESS, self.STATUS_DISPUTED]

    def auto_advance_bye_winner(self):
        """Complete bye matches automatically where participant_b is None."""
        if self.is_bye() and self.status != self.STATUS_COMPLETED:
            self.status = self.STATUS_COMPLETED
            self.winner = self.participant_a
            self.score_a = 1
            self.score_b = 0
            self.save()


class MatchReport(models.Model):
    """Immutable record of a single user's score report for a match."""
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


class LeagueStanding(models.Model):
    """
    Tracks league standings for league-type tournaments.
    Auto-updated when league matches are completed.
    """
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='league_standings')
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='league_standings')

    played = models.PositiveIntegerField(default=0)
    won = models.PositiveIntegerField(default=0)
    drew = models.PositiveIntegerField(default=0)
    lost = models.PositiveIntegerField(default=0)
    goals_for = models.PositiveIntegerField(default=0)
    goals_against = models.PositiveIntegerField(default=0)
    points = models.PositiveIntegerField(default=0)
    goal_difference = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tournament', 'participant')
        ordering = ['-points', '-goal_difference', '-goals_for']

    def __str__(self):
        return f"{self.participant.user.username} in {self.tournament.name} - {self.points}pts"

    def update_from_match(self, match):
        """
        Update standing based on a completed match.
        match: Match instance with score_a, score_b, and winner set.
        """
        if match.score_a is None or match.score_b is None:
            return

        self.played += 1

        # Assign goals based on whether participant is A or B
        if match.participant_a == self.participant:
            self.goals_for += match.score_a
            self.goals_against += match.score_b
        elif match.participant_b == self.participant:
            self.goals_for += match.score_b
            self.goals_against += match.score_a
        else:
            # Participant not involved in this match
            return

        # Update win/draw/loss and points
        if match.winner == self.participant:
            self.won += 1
            self.points += 3
        elif match.score_a == match.score_b:
            self.drew += 1
            self.points += 1
        else:
            self.lost += 1

        self.goal_difference = self.goals_for - self.goals_against
        self.save()

