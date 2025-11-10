# Short enums for tournament types and status choices
from django.utils.translation import gettext_lazy as _

class TournamentType:
    SINGLE_ELIMINATION = 'single_elimination'
    DOUBLE_ELIMINATION = 'double_elimination'
    ROUND_ROBIN = 'round_robin'

    CHOICES = [
        (SINGLE_ELIMINATION, _('Single Elimination')),
        (DOUBLE_ELIMINATION, _('Double Elimination')),
        (ROUND_ROBIN, _('Round Robin')),
    ]

class TournamentStatus:
    DRAFT = 'draft'
    REGISTRATION_OPEN = 'registration_open'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'

    CHOICES = [
        (DRAFT, _('Draft')),
        (REGISTRATION_OPEN, _('Registration Open')),
        (IN_PROGRESS, _('In Progress')),
        (COMPLETED, _('Completed')),
    ]