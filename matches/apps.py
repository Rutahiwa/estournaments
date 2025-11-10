from django.apps import AppConfig


class MatchesConfig(AppConfig):
    """App config for matches (fixtures, results, progression)."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'matches'
