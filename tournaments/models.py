from django.db import models
from django.conf import settings
from django.utils import timezone
from .enums import TournamentType, TournamentStatus

# Tournament model storing core tournament info and organizer relation
class Tournament(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=32, choices=TournamentType.CHOICES, default=TournamentType.SINGLE_ELIMINATION)
    status = models.CharField(max_length=32, choices=TournamentStatus.CHOICES, default=TournamentStatus.DRAFT)
    max_players = models.PositiveIntegerField(default=16)
    registration_deadline = models.DateTimeField(null=True, blank=True)
    organizer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='organized_tournaments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

    def is_registration_open(self):
        """Return True if the tournament is accepting registrations."""
        if self.status != TournamentStatus.REGISTRATION_OPEN:
            return False
        if self.registration_deadline and timezone.now() > self.registration_deadline:
            return False
        return True